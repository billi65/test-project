"""Step 2: turn an idea into a scene-by-scene script with image and video prompts."""
from reelbot.llm import generate_json

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "narration": {"type": "string"},
        "on_screen_text": {"type": "string"},
        "image_prompt": {"type": "string"},
        "video_prompt": {"type": "string"},
    },
    "required": ["narration", "on_screen_text", "image_prompt", "video_prompt"],
    "additionalProperties": False,
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "scenes": {"type": "array", "items": SCENE_SCHEMA},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "scenes", "caption", "hashtags"],
    "additionalProperties": False,
}


def validate_script(script: dict, cfg: dict) -> dict:
    scenes = script.get("scenes") or []
    lo, hi = cfg["script"]["min_scenes"], cfg["script"]["max_scenes"]
    if not lo <= len(scenes) <= hi:
        raise ValueError(f"Script has {len(scenes)} scenes; expected {lo}-{hi}.")
    for n, scene in enumerate(scenes, 1):
        for key in SCENE_SCHEMA["required"]:
            if not str(scene.get(key, "")).strip():
                raise ValueError(f"Scene {n} is missing '{key}'.")
    script["hashtags"] = ["#" + h.lstrip("#").replace(" ", "") for h in script.get("hashtags", [])]
    return script


def word_count(script: dict) -> int:
    return sum(len(s["narration"].split()) for s in script["scenes"])


def full_narration(script: dict) -> str:
    return " ".join(s["narration"].strip() for s in script["scenes"])


def write_script(cfg: dict, idea: dict) -> dict:
    sc = cfg["script"]
    system = (
        f"You write voiceover scripts for viral faceless Facebook Reels about {cfg['niche']}. "
        f"Tone: {cfg['tone']}. Language: {cfg['language']}. Accuracy matters: only state "
        "well-established findings, use hedges like 'research suggests' where appropriate, and "
        "never invent researcher names, dates, percentages, or study details you are unsure of."
    )
    prompt = f"""Write a ~{sc['target_words']}-word Reel script (it must be read aloud in under {sc['max_seconds']} seconds).

Topic: {idea['topic']}
Hook idea: {idea['hook']}

Structure it as {sc['min_scenes']}-{sc['max_scenes']} scenes:
- Scene 1 is the hook: a pattern interrupt that makes people stop scrolling (first 3 seconds).
- Middle scenes explain the effect with one vivid everyday example and why it happens.
- The second-to-last scene gives a practical takeaway.
- The last scene is a short call to action to follow for more psychology facts.

For every scene give:
- narration: the exact words to speak (short, punchy sentences, no stage directions).
- on_screen_text: 2-5 word overlay summarizing the scene.
- image_prompt: a detailed text-to-image prompt (subject, setting, emotion, camera angle, lighting) for a vertical 9:16 frame. No text or letters in the image. Keep the main character consistent across scenes if one appears.
- video_prompt: a 5-second image-to-video prompt describing camera motion and subject movement for that image.

Also give a title, a Facebook caption (2-3 lines, ends with a question to drive comments), and 5-8 hashtags.
Total narration must be {sc['target_words'] - 15}-{sc['target_words'] + 5} words."""
    script = generate_json(cfg, system, prompt, SCRIPT_SCHEMA)
    return validate_script(script, cfg)
