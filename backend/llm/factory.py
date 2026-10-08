from backend.config import settings
from backend.llm.base import LLMProvider
from backend.llm.http_providers import AnthropicProvider, OpenAIProvider
from backend.llm.wrappers import FallbackProvider, RetryingProvider


class LLMNotConfigured(Exception):
    pass


def build_llm_provider() -> LLMProvider:
    """Anthropic first, OpenAI as fallback, each retried; raises if no key is configured."""
    providers: list[LLMProvider] = []
    if settings.anthropic_api_key.get_secret_value():
        providers.append(RetryingProvider(AnthropicProvider()))
    if settings.openai_api_key.get_secret_value():
        providers.append(RetryingProvider(OpenAIProvider()))
    if not providers:
        raise LLMNotConfigured("No LLM provider is configured")
    return FallbackProvider(providers)
