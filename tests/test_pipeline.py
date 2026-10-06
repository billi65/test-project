import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reelbot.config import ROOT, load_config
from reelbot.ideas import filter_used
from reelbot.publish import build_description
from reelbot.render import _ass_time, build_ass, scene_timings
from reelbot.script import full_narration, validate_script, word_count

CFG = load_config()
SAMPLE = json.loads((ROOT / "reelbot" / "sample_script.json").read_text(encoding="utf-8"))


def _words(n, step=0.4):
    return [{"text": f"w{i}", "start": i * step, "end": i * step + 0.3} for i in range(n)]


def test_sample_script_validates_and_fits_a_minute():
    script = validate_script(json.loads(json.dumps(SAMPLE)), CFG)
    assert 130 <= word_count(script) <= 155
    assert full_narration(script).startswith("Nobody is watching")


def test_validate_rejects_wrong_scene_count_and_blank_fields():
    with pytest.raises(ValueError, match="scenes"):
        validate_script({"scenes": SAMPLE["scenes"][:2], "hashtags": []}, CFG)
    bad = json.loads(json.dumps(SAMPLE))
    bad["scenes"][3]["image_prompt"] = " "
    with pytest.raises(ValueError, match="Scene 4"):
        validate_script(bad, CFG)


def test_validate_normalizes_hashtags():
    s = json.loads(json.dumps(SAMPLE))
    s["hashtags"] = ["psychology", "#mind set"]
    assert validate_script(s, CFG)["hashtags"] == ["#psychology", "#mindset"]


def test_scene_timings_are_contiguous_and_cover_audio():
    words = _words(100)
    t = scene_timings([20, 30, 50], words, audio_len=40.0)
    assert t[0][0] == 0.0
    assert t[1][0] == words[20]["start"] and t[2][0] == words[50]["start"]
    assert all(a[1] == b[0] for a, b in zip(t, t[1:]))
    assert t[-1][1] >= 40.0


def test_scene_timings_tolerate_event_count_mismatch():
    t = scene_timings([10, 10], _words(18), audio_len=8.0)
    assert len(t) == 2 and t[0][1] > 0 and t[1][1] > t[1][0]


def test_ass_captions_chunk_and_highlight():
    ass = build_ass(_words(7), CFG)
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue")]
    assert len(dialogue) == 7
    assert "{\\c&H00E6FF&}W0{\\c&HFFFFFF&} W1 W2" in dialogue[0]
    assert _ass_time(61.234) == "0:01:01.23"


def test_filter_used_ignores_case_and_punctuation():
    ideas = [{"topic": "The Spotlight Effect!"}, {"topic": "Zeigarnik effect"}]
    assert filter_used(ideas, ["the spotlight effect"]) == [ideas[1]]


def test_description_includes_caption_tags_and_disclosure():
    d = build_description(SAMPLE, CFG)
    assert SAMPLE["caption"] in d and "#psychology" in d and CFG["publish"]["ai_disclosure"] in d


def test_generate_json_uses_structured_output_and_fallbacks():
    from reelbot import llm

    resp = MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text='{"ok": true}')])
    with patch.object(llm.anthropic, "Anthropic") as client_cls:
        client_cls.return_value.beta.messages.create.return_value = resp
        assert llm.generate_json(CFG, "sys", "prompt", {"type": "object"}) == {"ok": True}
        kwargs = client_cls.return_value.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == CFG["llm"]["model"]
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["fallbacks"] == "default"


def test_publish_flow_calls_start_upload_finish(tmp_path, monkeypatch):
    from reelbot import publish

    monkeypatch.setenv("FB_PAGE_ID", "123")
    monkeypatch.setenv("FB_PAGE_TOKEN", "tok")
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"x" * 10)

    def ok(payload):
        r = MagicMock(status_code=200, content=b"1")
        r.json.return_value = payload
        return r

    posts = [ok({"video_id": "v1"}), ok({"success": True}), ok({"success": True})]
    with patch.object(publish.requests, "post", side_effect=posts) as post, \
         patch.object(publish.requests, "get", return_value=ok({"status": {"video_status": "ready"}})):
        assert publish.publish_reel(CFG, video, "desc") == "v1"
    phases = [c.kwargs.get("data", {}) for c in post.call_args_list]
    assert phases[0]["upload_phase"] == "start"
    assert "rupload.facebook.com" in post.call_args_list[1].args[0]
    assert phases[2]["upload_phase"] == "finish" and phases[2]["video_state"] == "PUBLISHED"
