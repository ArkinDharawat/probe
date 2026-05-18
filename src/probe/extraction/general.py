from __future__ import annotations

from pathlib import Path

from probe.llm import structured_call

PROMPT_VERSION = "general-v1"

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "extract_general.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "main_topic": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "entities_mentioned": {"type": "array", "items": {"type": "string"}},
        "author_stance": {"type": "string"},
    },
    "required": [
        "main_topic",
        "key_points",
        "entities_mentioned",
        "author_stance",
    ],
}


def run(content: str) -> dict:
    system = PROMPT_PATH.read_text()
    return structured_call(prompt=content, output_schema=SCHEMA, system=system)
