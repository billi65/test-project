"""Thin wrapper around the Claude API that returns schema-validated JSON."""
import json

import anthropic


def generate_json(cfg: dict, system: str, prompt: str, schema: dict, max_tokens: int = 8000) -> dict:
    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=cfg["llm"]["model"],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "effort": cfg["llm"].get("effort", "low"),
            "format": {"type": "json_schema", "schema": schema},
        },
        # On a safety-classifier decline, the API retries on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude hit max_tokens before finishing the JSON; raise max_tokens.")
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text)
