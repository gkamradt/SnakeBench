import os
import json
import uuid
from json.decoder import JSONDecodeError
from openai import OpenAI
from typing import Dict, Any, Optional
from prompting import SnakePrompt, prompt_request, usage_details

class LLMProviderInterface:
    """
    A common interface for LLM calls.
    Model name is stored during initialization.
    """
    def get_response(self, prompt: str) -> Dict[str, Any]: # Returns dict with response and usage
        raise NotImplementedError("Subclasses should implement this method.")

    def health_check(self) -> bool:
        """
        Check if the model is available and accessible.
        Returns True if model is available, False otherwise.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    @staticmethod
    def extract_api_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts fields not part of the standard internal configuration
        into a dictionary suitable for passing as kwargs to the underlying API call.
        """
        api_kwargs = {}
        # Fields used internally for setup, not passed to the API directly
        # Includes both legacy YAML fields and database fields from Supabase
        known_fields = {
            'name', 'provider', 'pricing', 'kwargs', 'model_name', 'api_type',
            # Database fields from Supabase models table
            'id', 'model_slug', 'is_active', 'test_status', 'elo_rating', 'rating',
            'wins', 'losses', 'ties', 'apples_eaten', 'games_played',
            'pricing_input', 'pricing_output', 'max_completion_tokens',
            'last_played_at', 'discovered_at'
        }

        # Start with any explicitly defined 'kwargs' from the config
        api_kwargs.update(config.get('kwargs', {}))

        # Add any other top-level fields that aren't known internal fields
        for field_name, value in config.items():
            # Filter out rating/metadata fields that shouldn't reach the API
            if field_name in known_fields or field_name.startswith("trueskill_"):
                continue
            api_kwargs[field_name] = value

        return api_kwargs

class OpenRouterProvider(LLMProviderInterface):
    def __init__(self, api_key: str, config: Dict[str, Any]):
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = config['model_name']
        self.api_type = config.get('api_type', 'completions')
        self.api_kwargs = self.extract_api_kwargs(config)
        # One provider instance lives for one player/game. Changing turn text
        # must not change OpenRouter's conversation routing key.
        self.session_id = uuid.uuid4().hex

        explicit_headers = self.api_kwargs.pop('extra_headers', None)
        env_headers = {}
        referer = os.getenv("OPENROUTER_SITE_URL", "https://snakebench.com")
        title = os.getenv("OPENROUTER_SITE_NAME", "SnakeBench")
        if referer:
            env_headers["HTTP-Referer"] = referer
        if title:
            env_headers["X-Title"] = title
        if explicit_headers:
            env_headers.update(explicit_headers)
        self.extra_headers = env_headers or None

    def get_response(self, prompt: str) -> Dict[str, Any]:
        request_kwargs = dict(self.api_kwargs)
        if self.extra_headers:
            request_kwargs['extra_headers'] = self.extra_headers

        payload = prompt_request(prompt, api=self.api_type, model=self.model_name)
        cache_body = payload.pop('extra_body', {})
        if isinstance(prompt, SnakePrompt):
            cache_body['session_id'] = self.session_id
        if cache_body:
            request_kwargs['extra_body'] = {**cache_body, **request_kwargs.get('extra_body', {})}
        request_kwargs.update(payload)

        if self.api_type == 'responses':
            response = self.client.responses.create(
                model=self.model_name,
                **request_kwargs,
            )
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except json.JSONDecodeError:
                    preview = response[:200].replace('\n', ' ')
                    raise ValueError(f"OpenRouter returned unexpected text payload: {preview}...")

            output = getattr(response, "output", None)
            if output is None and isinstance(response, dict):
                output = response.get("output")
            if not output:
                raise ValueError(f"OpenRouter response missing output field: {response}")

            # Reasoning items can precede the assistant message.
            texts = []
            for message in output:
                content = message.get('content', []) if isinstance(message, dict) else getattr(message, 'content', [])
                for block in content or []:
                    block_text = block.get('text') if isinstance(block, dict) else getattr(block, 'text', None)
                    if block_text:
                        texts.append(block_text)
            text = '\n'.join(texts)
            if not text:
                raise ValueError("OpenRouter response missing output text")

            # Extract usage information
            usage = getattr(response, "usage", None)
            if usage is None and isinstance(response, dict):
                usage = response.get("usage", {})

            result = {
                "text": str(text or "").strip(),
                "input_tokens": usage.get("input_tokens", 0) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0) if isinstance(usage, dict) else getattr(usage, "output_tokens", 0)
            }
        else:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    **request_kwargs,
                )
            except JSONDecodeError as exc:
                raise ValueError(
                    "OpenRouter chat completion returned a non-JSON payload. "
                    "This usually means the model slug is invalid or the request was redirected to an HTML error page."
                ) from exc

            # Extract usage information
            usage = response.usage if hasattr(response, 'usage') else None

            result = {
                "text": response.choices[0].message.content.strip(),
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0
            }

        details = usage_details(usage, api=self.api_type)
        if details:
            result["usage_details"] = details
        return result

    def health_check(self) -> bool:
        """
        Check if the model is available on OpenRouter.
        Makes a minimal API call to verify the model exists and is accessible.
        Returns True if model is available, False if it returns a 404 or other error.
        """
        try:
            request_kwargs = dict(self.api_kwargs)
            if self.extra_headers:
                request_kwargs['extra_headers'] = self.extra_headers

            # Override max_tokens to 1 for minimal cost
            request_kwargs['max_tokens'] = 1

            # Make a minimal test request
            if self.api_type == 'responses':
                response = self.client.responses.create(
                    model=self.model_name,
                    input="test",
                    **request_kwargs,
                )
            else:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": "test"}],
                    **request_kwargs,
                )

            # If we got here without exception, the model is available
            return True

        except Exception as e:
            error_str = str(e).lower()
            # Check for 404 or "model not found" errors
            if '404' in error_str or 'model not found' in error_str or 'not found' in error_str:
                return False
            # For other errors, we'll assume the model might be temporarily unavailable
            # but not necessarily non-existent, so return True to allow retry
            print(f"Warning: Health check failed with non-404 error: {e}")
            return True


def create_llm_provider(player_config: Dict[str, Any]) -> LLMProviderInterface:
    """
    Factory function for creating an LLM provider instance.
    All models now route through OpenRouter.
    """
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is not set in the environment variables.")

    return OpenRouterProvider(api_key=os.getenv("OPENROUTER_API_KEY"), config=player_config)
