"""Step 1: generate fresh Reel ideas for the niche and drop ones already used."""
import re

from reelbot.llm import generate_json

IDEAS_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "hook": {"type": "string"},
                    "why_it_works": {"type": "string"},
                },
                "required": ["topic", "hook", "why_it_works"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}


def normalize(topic: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", topic.lower()).strip()


def filter_used(ideas: list[dict], used_topics: list[str]) -> list[dict]:
    used = {normalize(t) for t in used_topics}
    return [i for i in ideas if normalize(i["topic"]) not in used]


def generate_ideas(cfg: dict, used_topics: list[str], count: int = 10) -> list[dict]:
    system = (
        f"You are a content strategist for a faceless Facebook Reels page about {cfg['niche']}. "
        f"Audience: {cfg['audience']}. You pick topics that are surprising, relatable, and "
        "grounded in well-established research — never fringe claims or invented studies."
    )
    recent = "\n".join(f"- {t}" for t in used_topics[-100:]) or "(none yet)"
    prompt = (
        f"Suggest {count} distinct 1-minute Reel ideas. Each needs a specific topic (one effect, "
        "bias, or behavior), a scroll-stopping hook line under 12 words, and one sentence on why "
        f"it will hold attention. Order them best first.\n\nAlready covered, do not repeat:\n{recent}"
    )
    ideas = generate_json(cfg, system, prompt, IDEAS_SCHEMA, max_tokens=4000)["ideas"]
    return filter_used(ideas, used_topics)
