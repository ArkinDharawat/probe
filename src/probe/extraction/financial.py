from __future__ import annotations

from pathlib import Path

from probe.llm import structured_call

PROMPT_VERSION = "financial-v1"

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "extract_financial.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "core_claim": {"type": "string"},
        "evidence_chain": {"type": "array", "items": {"type": "string"}},
        "implied_positions": {"type": "array", "items": {"type": "string"}},
        "risks_acknowledged": {"type": "array", "items": {"type": "string"}},
        "risks_ignored": {"type": "array", "items": {"type": "string"}},
        "key_metrics": {"type": "object"},
    },
    "required": [
        "core_claim",
        "evidence_chain",
        "implied_positions",
        "risks_acknowledged",
        "risks_ignored",
        "key_metrics",
    ],
}


def run(content: str) -> dict:
    system = PROMPT_PATH.read_text()
    return structured_call(prompt=content, output_schema=SCHEMA, system=system)
