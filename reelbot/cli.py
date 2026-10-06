"""Command line: `python -m reelbot make|run|post|rerender`."""
import json
import re
from datetime import date, datetime
from pathlib import Path

import typer

from reelbot import images as images_mod
from reelbot import render as render_mod
from reelbot.config import ROOT, load_config, load_history, save_history
from reelbot.voice import audio_duration, make_voiceover

app = typer.Typer(add_completion=False, help="Facebook Reels automation: idea -> script -> voice -> images -> video -> post.")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "reel"


def _load(out_dir: Path) -> tuple[dict, dict]:
    script = json.loads((out_dir / "script.json").read_text(encoding="utf-8"))
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    return script, meta


def _save_meta(out_dir: Path, meta: dict) -> None:
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _render(cfg: dict, out_dir: Path, script: dict) -> Path:
    words = json.loads((out_dir / "words.json").read_text(encoding="utf-8"))
    voice = out_dir / "voice.mp3"
    counts = [len(s["narration"].split()) for s in script["scenes"]]
    timings = render_mod.scene_timings(counts, words, audio_duration(voice))
    imgs = [out_dir / f"scene_{i + 1:02d}.jpg" for i in range(len(script["scenes"]))]
    return render_mod.render_reel(cfg, out_dir, imgs, timings, words, voice)


def _pick_idea(cfg: dict, history: dict, topic: str | None, choose: bool) -> dict:
    if topic:
        return {"topic": topic, "hook": "", "why_it_works": "user supplied"}
    from reelbot.ideas import generate_ideas

    typer.echo("💡 Generating ideas...")
    ideas = generate_ideas(cfg, [t["topic"] for t in history["topics"]])
    if not ideas:
        raise SystemExit("No new ideas came back; try again or pass --topic.")
    if not choose:
        return ideas[0]
    for n, idea in enumerate(ideas, 1):
        typer.echo(f"  {n}. {idea['topic']} — “{idea['hook']}”")
    pick = typer.prompt("Pick an idea", default=1, type=int)
    return ideas[max(1, min(pick, len(ideas))) - 1]


def make_reel(topic: str | None = None, choose: bool = False, dry_run: bool = False,
              offline: bool = False, provider: str | None = None) -> Path:
    cfg = load_config()
    history = load_history()
    from reelbot.script import full_narration, validate_script, word_count, write_script

    if dry_run or offline:
        script = validate_script(json.loads((ROOT / "reelbot" / "sample_script.json").read_text(encoding="utf-8")), cfg)
        idea = {"topic": script["title"], "hook": script["scenes"][0]["narration"], "why_it_works": "sample"}
    else:
        idea = _pick_idea(cfg, history, topic, choose)
        typer.echo(f"✍️  Writing script: {idea['topic']}")
        script = write_script(cfg, idea)

    out_dir = ROOT / "output" / f"{date.today().isoformat()}-{_slug(script['title'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    _save_meta(out_dir, {"idea": idea, "status": "generated", "created": datetime.now().isoformat(timespec="seconds")})
    typer.echo(f"   {len(script['scenes'])} scenes, {word_count(script)} words")

    typer.echo("🎙️  Voiceover...")
    make_voiceover(cfg, full_narration(script), out_dir, offline=offline)

    typer.echo("🖼️  Images...")
    images_mod.generate_images(cfg, [s["image_prompt"] for s in script["scenes"]], out_dir,
                               provider="placeholder" if offline else provider)

    typer.echo("🎬 Rendering...")
    reel = _render(cfg, out_dir, script)
    typer.echo(f"✅ {reel.relative_to(ROOT)} ({audio_duration(reel):.1f}s)")
    return out_dir


def post_reel(out_dir: Path) -> str:
    from reelbot.publish import build_description, publish_reel

    cfg = load_config()
    script, meta = _load(out_dir)
    if meta.get("status") == "posted":
        raise SystemExit(f"Already posted as video {meta.get('video_id')}.")
    typer.echo("📤 Uploading to Facebook...")
    video_id = publish_reel(cfg, out_dir / "reel.mp4", build_description(script, cfg))
    meta.update(status="posted", video_id=video_id, posted=datetime.now().isoformat(timespec="seconds"))
    _save_meta(out_dir, meta)
    history = load_history()
    history["topics"].append({"topic": meta["idea"]["topic"], "video_id": video_id, "date": date.today().isoformat()})
    save_history(history)
    typer.echo(f"🎉 Posted! Video id {video_id}")
    return video_id


@app.command()
def make(
    topic: str = typer.Option(None, help="Skip idea generation and use this topic."),
    choose: bool = typer.Option(False, help="Show the generated ideas and pick one."),
    dry_run: bool = typer.Option(False, help="Use the bundled sample script (no Claude call)."),
    offline: bool = typer.Option(False, help="Sample script + placeholder images + silent voice; no network."),
    provider: str = typer.Option(None, help="Image provider override: fal | pollinations."),
):
    """Generate a Reel into output/<date>-<slug>/ without posting."""
    make_reel(topic, choose, dry_run, offline, provider)


@app.command()
def run(
    topic: str = typer.Option(None, help="Skip idea generation and use this topic."),
    choose: bool = typer.Option(False, help="Show the generated ideas and pick one."),
    provider: str = typer.Option(None, help="Image provider override: fal | pollinations."),
):
    """Generate a Reel, let you review it, then post it."""
    out_dir = make_reel(topic, choose, provider=provider)
    review(out_dir)


@app.command()
def review(out_dir: Path = typer.Argument(..., help="An output/<date>-<slug> folder.")):
    """Review a generated Reel: post it, regenerate scene images, or stop."""
    cfg = load_config()
    out_dir = out_dir.resolve()
    while True:
        script, _ = _load(out_dir)
        typer.echo(f"\nVideo:   {out_dir / 'reel.mp4'}\nPreview: {out_dir / 'preview.jpg'}\n")
        for n, s in enumerate(script["scenes"], 1):
            typer.echo(f"  [{n}] {s['on_screen_text']}")
        typer.echo(f"\nCaption:\n{script['caption']}\n{' '.join(script['hashtags'])}\n")
        choice = typer.prompt("Post it? [y]es / [n]o / [r N] regenerate scene N image", default="n").strip().lower()
        if choice in {"y", "yes"}:
            post_reel(out_dir)
            return
        if choice.startswith("r"):
            nums = [int(x) - 1 for x in re.findall(r"\d+", choice) if 0 < int(x) <= len(script["scenes"])]
            if not nums:
                typer.echo("Give scene numbers, e.g. `r 2 5`.")
                continue
            images_mod.generate_images(cfg, [s["image_prompt"] for s in script["scenes"]], out_dir, only=nums)
            _render(cfg, out_dir, script)
            continue
        typer.echo(f"Not posted. Later: python -m reelbot post {out_dir}")
        return


@app.command()
def post(out_dir: Path = typer.Argument(..., help="An output/<date>-<slug> folder.")):
    """Post an already-generated Reel."""
    post_reel(out_dir.resolve())


@app.command()
def rerender(out_dir: Path = typer.Argument(..., help="An output/<date>-<slug> folder.")):
    """Re-render reel.mp4 after editing images, captions settings, or music."""
    cfg = load_config()
    script, _ = _load(out_dir.resolve())
    _render(cfg, out_dir.resolve(), script)
