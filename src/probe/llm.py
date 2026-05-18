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

    # `max_tokens` (or other non-terminal stops) can leave a tool_use block
    # present but with a truncated `input` dict. Surface that explicitly rather
    # than letting downstream code KeyError on a missing field.
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason not in (None, "tool_use", "end_turn"):
        raise RuntimeError(
            f"Anthropic returned stop_reason={stop_reason!r}; structured output may be incomplete."
        )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "structured_output":
            payload = block.input
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"Anthropic structured_output block had non-dict input: {type(payload).__name__}"
                )
            required = output_schema.get("required") if isinstance(output_schema, dict) else None
            if required:
                missing = [k for k in required if k not in payload]
                if missing:
                    raise RuntimeError(
                        f"Anthropic structured_output missing required fields: {missing}"
                    )
            return payload

    raise RuntimeError("Anthropic response did not contain a structured_output tool_use block.")
