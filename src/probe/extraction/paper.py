from __future__ import annotations

from pathlib import Path

from probe.llm import structured_call

PROMPT_VERSION = "paper-v1"

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "extract_paper.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "claimed_contribution": {"type": "string"},
        "method": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "baselines": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "builds_on": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "claimed_contribution",
        "method",
        "key_findings",
        "baselines",
        "limitations",
        "builds_on",
    ],
}


def run(content: str) -> dict:
    system = PROMPT_PATH.read_text()
    return structured_call(prompt=content, output_schema=SCHEMA, system=system)
