"""Step 5: Ken Burns clips per scene + crossfades + word captions + music -> reel.mp4."""
import random
import subprocess
from pathlib import Path


def scene_timings(scene_word_counts: list[int], words: list[dict], audio_len: float) -> list[tuple[float, float]]:
    """Map each scene to (start, end) seconds using the TTS word timings.

    TTS word events don't always match str.split() counts (numbers, contractions), so scene
    boundaries are placed proportionally on the event list.
    """
    total = sum(scene_word_counts)
    n_events = len(words)
    starts, cum = [], 0
    for count in scene_word_counts:
        idx = min(n_events - 1, round(cum / total * n_events))
        starts.append(0.0 if not starts else words[idx]["start"])
        cum += count
    end = max(audio_len, words[-1]["end"]) + 0.6
    return [(s, starts[i + 1] if i + 1 < len(starts) else end) for i, s in enumerate(starts)]


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(words: list[dict], cfg: dict) -> str:
    """Bold centered captions in 2-3 word chunks; the word being spoken is highlighted."""
    cc, vc = cfg["captions"], cfg["video"]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {vc['width']}
PlayResY: {vc['height']}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cc['font']},{cc['size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,{cc['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    n = cc["words_per_chunk"]
    chunks = [words[i:i + n] for i in range(0, len(words), n)]
    lines = []
    for ci, chunk in enumerate(chunks):
        chunk_end = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else chunk[-1]["end"] + 0.4
        for wi, word in enumerate(chunk):
            start = word["start"]
            end = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else chunk_end
            parts = []
            for k, w in enumerate(chunk):
                txt = w["text"].upper().replace("{", "").replace("}", "")
                parts.append(r"{\c&H00E6FF&}" + txt + r"{\c&HFFFFFF&}" if k == wi else txt)
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"


def _zoompan(kind: int, frames: int, w: int, h: int, fps: int) -> str:
    n = max(frames - 1, 1)
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    motions = [
        f"z='1+0.15*on/{n}':{center}",                          # slow push in
        f"z='1.15-0.15*on/{n}':{center}",                       # pull out
        f"z='1.15':x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'",  # pan left -> right
        f"z='1.15':x='(iw-iw/zoom)*(1-on/{n})':y='ih/2-(ih/zoom/2)'",  # pan right -> left
    ]
    # Upscale first so sub-pixel zoom steps don't jitter.
    return f"scale={w * 2}:{h * 2},zoompan={motions[kind % 4]}:d={frames}:s={w}x{h}:fps={fps},setsar=1"


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)}\n{proc.stderr[-2000:]}")


def render_reel(cfg: dict, out_dir: Path, images: list[Path], timings: list[tuple[float, float]],
                words: list[dict], voice_path: Path) -> Path:
    vc = cfg["video"]
    w, h, fps, cf = vc["width"], vc["height"], vc["fps"], vc["crossfade"]
    n = len(images)

    # 1) one clip per scene; all but the last are extended by the crossfade overlap
    lengths = [(end - start) + (cf if i < n - 1 else 0) for i, (start, end) in enumerate(timings)]
    clips = []
    for i, (img, length) in enumerate(zip(images, lengths)):
        clip = out_dir / f"clip_{i + 1:02d}.mp4"
        frames = int(round(length * fps))
        _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(fps), "-i", img.name,
              "-vf", _zoompan(i, frames, w, h, fps), "-frames:v", str(frames),
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", clip.name], out_dir)
        clips.append(clip)

    # 2) captions
    (out_dir / "captions.ass").write_text(build_ass(words, cfg), encoding="utf-8")

    # 3) chain crossfades, burn captions, mix voice (+ optional music)
    inputs, filters = [], []
    for clip in clips:
        inputs += ["-i", clip.name]
    prev, offset = "[0:v]", 0.0
    for i in range(1, n):
        offset += lengths[i - 1] - cf
        filters.append(f"{prev}[{i}:v]xfade=transition=fade:duration={cf}:offset={offset:.3f}[v{i}]")
        prev = f"[v{i}]"
    filters.append(f"{prev}ass=captions.ass,format=yuv420p[vout]")
    total = sum(lengths) - cf * (n - 1)

    inputs += ["-i", str(voice_path.resolve())]
    voice_idx = n
    music = _pick_music(cfg)
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        mv = cfg["music"]["volume_db"]
        filters.append(f"[{n + 1}:a]volume={mv}dB,afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[bg]")
        filters.append(f"[{voice_idx}:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        filters.append(f"[{voice_idx}:a]anull[aout]")
    filters.append(f"[aout]apad=whole_dur={total:.3f}[afinal]")

    reel = out_dir / "reel.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
          "-map", "[vout]", "-map", "[afinal]", "-t", f"{total:.3f}", "-r", str(fps),
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", reel.name], out_dir)

    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.5", "-i", reel.name, "-frames:v", "1", "preview.jpg"], out_dir)
    for clip in clips:
        clip.unlink(missing_ok=True)
    return reel


def _pick_music(cfg: dict) -> Path | None:
    from reelbot.config import ROOT

    music_dir = ROOT / cfg["music"]["dir"]
    tracks = [p for p in music_dir.glob("*") if p.suffix.lower() in {".mp3", ".m4a", ".wav", ".ogg"}]
    return random.choice(tracks) if tracks else None
