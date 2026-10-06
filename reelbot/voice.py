"""Step 3: voiceover with Edge TTS plus word-level timings for captions and scene cuts."""
import asyncio
import json
import subprocess
from pathlib import Path

TICKS_PER_SECOND = 10_000_000  # edge-tts reports offsets in 100 ns units


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


async def _edge_tts(text: str, voice: str, rate: str, mp3_path: Path) -> list[dict]:
    import edge_tts

    words = []
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / TICKS_PER_SECOND,
                    "end": (chunk["offset"] + chunk["duration"]) / TICKS_PER_SECOND,
                })
    return words


def _offline_tts(text: str, mp3_path: Path) -> list[dict]:
    """Silent track with estimated timings, for previewing layout without network access."""
    words, t = [], 0.3
    for w in text.split():
        d = 0.12 + 0.04 * len(w)  # roughly 2.8 words/s, like real TTS at +8%
        words.append({"text": w.strip(".,!?;:\"'"), "start": t, "end": t + d})
        t += d + 0.05
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", f"{t + 0.3:.2f}", "-c:a", "libmp3lame", str(mp3_path)],
        check=True,
    )
    return words


def _bump_rate(rate: str, step: int = 7) -> str:
    return f"{int(rate.rstrip('%')) + step:+d}%"


def make_voiceover(cfg: dict, text: str, out_dir: Path, offline: bool = False) -> tuple[Path, list[dict]]:
    mp3_path = out_dir / "voice.mp3"
    vc = cfg["voice"]
    max_s = cfg["script"]["max_seconds"]
    if offline:
        words = _offline_tts(text, mp3_path)
    else:
        rate = vc["rate"]
        words = asyncio.run(_edge_tts(text, vc["name"], rate, mp3_path))
        if audio_duration(mp3_path) > max_s:
            rate = _bump_rate(rate)
            words = asyncio.run(_edge_tts(text, vc["name"], rate, mp3_path))
    duration = audio_duration(mp3_path)
    if duration > max_s:
        raise SystemExit(f"Voiceover is {duration:.1f}s (> {max_s}s). Shorten the script and retry.")
    if not words:
        raise SystemExit("TTS returned no word timings; captions cannot be built.")
    (out_dir / "words.json").write_text(json.dumps(words, indent=1), encoding="utf-8")
    return mp3_path, words
