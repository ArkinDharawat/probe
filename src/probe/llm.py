from __future__ import annotations

from anthropic import Anthropic

from probe.config import load


def structured_call(
    prompt: str,
    output_schema: dict,
    *,
    system: str | None = None,
    model: str | None = None,
) -> dict:
    """Call Anthropic and force a structured response via tool_use.

    Registers `output_schema` as a single tool, forces tool_choice on it,
    and unwraps the model's tool_use block input into a dict.
    """
    cfg = load()
    if cfg.anthropic_api_key is None:
        raise RuntimeError(
            "Anthropic API key is missing. Set anthropic_api_key in ~/.probe/config.yaml "
            "or ANTHROPIC_API_KEY in the environment."
        )

    resolved_model = model if model is not None else cfg.extraction_model

    client = Anthropic(api_key=cfg.anthropic_api_key)

    kwargs: dict = {
        "model": resolved_model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [
            {
                "name": "structured_output",
                "description": "Return the structured output for this request.",
                "input_schema": output_schema,
            }
        ],
        # Pin tool_choice so the model must emit our schema rather than free-form text.
        "tool_choice": {"type": "tool", "name": "structured_output"},
    }
    if system is not None:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "structured_output":
            return block.input

    raise RuntimeError("Anthropic response did not contain a structured_output tool_use block.")
