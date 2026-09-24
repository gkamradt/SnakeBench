"""Snake prompt sections and provider-specific cache boundaries."""


class SnakePrompt(str):
    """Keep the legacy string interface while retaining an explicit split.

    Injected/offline providers can still consume this as ordinary text. Real
    adapters use the two sections without searching for delimiters in model data.
    """

    def __new__(cls, instructions: str, turn_state: str):
        prompt = super().__new__(cls, instructions + turn_state)
        prompt.instructions = instructions
        prompt.turn_state = turn_state
        return prompt


def prompt_request(prompt: str, *, api: str, model: str, cache_supported=True):
    """Build one user message; never upgrade game data into a system message.

    New OpenAI fields travel through extra_body for compatibility with the
    installed SDK. Unknown models/compatible servers keep ordinary text.
    Anthropic Responses markers are translated by OpenRouter, not by OpenAI.
    """
    content = str(prompt)
    extra_body = {}
    openai_explicit = model.startswith(("gpt-6-", "gpt-5.6-", "openai/gpt-6-", "openai/gpt-5.6-"))
    anthropic = model.startswith("anthropic/")
    if isinstance(prompt, SnakePrompt) and cache_supported and (openai_explicit or anthropic):
        block_type = "input_text" if api == "responses" else "text"
        stable = {"type": block_type, "text": prompt.instructions}
        if anthropic and api != "responses":
            stable["cache_control"] = {"type": "ephemeral"}
        else:
            stable["prompt_cache_breakpoint"] = {"mode": "explicit"}
        if openai_explicit:
            # Do not pay to cache each changing board and previous rationale.
            extra_body["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
        content = [stable, {"type": block_type, "text": prompt.turn_state}]

    if api == "responses":
        payload = {"input": [{"role": "user", "content": content}]} if isinstance(content, list) else {"input": content}
    else:
        payload = {"messages": [{"role": "user", "content": content}]}
    if extra_body:
        payload["extra_body"] = extra_body
    return payload


def usage_details(usage, *, api: str):
    """Retain reported cache/reasoning/cost fields; absent means unknown."""
    def get(value, key):
        return value.get(key) if isinstance(value, dict) else getattr(value, key, None)

    input_details = get(usage, "input_tokens_details" if api == "responses" else "prompt_tokens_details")
    output_details = get(usage, "output_tokens_details" if api == "responses" else "completion_tokens_details")
    values = {
        "cached_tokens": get(input_details, "cached_tokens"),
        "cache_write_tokens": get(input_details, "cache_write_tokens"),
        "reasoning_tokens": get(output_details, "reasoning_tokens"),
        "provider_cost": get(usage, "cost"),
    }
    return {key: value for key, value in values.items() if value is not None}
