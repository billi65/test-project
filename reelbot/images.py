"""Step 4: one vertical image per scene, from a pluggable provider."""
import io
import random
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageOps


def _fit(data: bytes, width: int, height: int) -> Image.Image:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return ImageOps.fit(img, (width, height), Image.LANCZOS)


def _fal(prompt: str, cfg: dict) -> bytes:
    import fal_client

    result = fal_client.subscribe(
        cfg["images"]["fal_model"],
        arguments={
            "prompt": prompt,
            "image_size": {"width": 1088, "height": 1920},
            "num_images": 1,
            "enable_safety_checker": True,
        },
    )
    return requests.get(result["images"][0]["url"], timeout=120).content


def _pollinations(prompt: str, cfg: dict) -> bytes:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
    params = {"width": 1080, "height": 1920, "nologo": "true", "seed": random.randint(1, 10**6)}
    resp = requests.get(url, params=params, timeout=180)
    resp.raise_for_status()
    return resp.content


def _placeholder(prompt: str, cfg: dict, index: int = 0) -> bytes:
    """Offline gradient frame with the prompt printed on it, for layout previews."""
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    hue = (index * 47) % 255
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        draw.line([(0, y), (w, y)], fill=(hue // 2, 40 + y * 120 // h, 120 + (255 - hue) // 3))
    for i in range(0, 12):
        draw.ellipse([(i * 97) % w, (i * 331) % h, (i * 97) % w + 220, (i * 331) % h + 220], outline=(255, 255, 255))
    draw.multiline_text((60, 160), "\n".join(prompt[k:k + 40] for k in range(0, min(len(prompt), 280), 40)), fill="white")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


PROVIDERS = {"fal": _fal, "pollinations": _pollinations}


def _generate_one(index: int, prompt: str, cfg: dict, out_dir: Path, provider: str) -> Path:
    path = out_dir / f"scene_{index + 1:02d}.jpg"
    full_prompt = f"{prompt}. {cfg['images']['style']}"
    for attempt in range(3):
        try:
            if provider == "placeholder":
                data = _placeholder(prompt, cfg, index)
            else:
                data = PROVIDERS[provider](full_prompt, cfg)
            _fit(data, cfg["video"]["width"], cfg["video"]["height"]).save(path, "JPEG", quality=95)
            return path
        except Exception as exc:  # noqa: BLE001 - retry any provider failure
            if attempt == 2:
                raise RuntimeError(f"Image for scene {index + 1} failed: {exc}") from exc
            time.sleep(2 * (attempt + 1))
    return path


def generate_images(cfg: dict, prompts: list[str], out_dir: Path, provider: str | None = None,
                    only: list[int] | None = None) -> list[Path]:
    """Generate all scene images (or only the 0-based indexes in `only`)."""
    provider = provider or cfg["images"]["provider"]
    indexes = only if only is not None else list(range(len(prompts)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: _generate_one(i, prompts[i], cfg, out_dir, provider), indexes))
    return [out_dir / f"scene_{i + 1:02d}.jpg" for i in range(len(prompts))]
