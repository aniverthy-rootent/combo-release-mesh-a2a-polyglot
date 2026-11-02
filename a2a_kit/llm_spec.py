"""One LLM_SPEC ("<provider>:<model>") translated into each framework's own model identifier.

providers: openai | anthropic | gemini | groq | mistral | ollama
"""
from __future__ import annotations

import os

LANGCHAIN_PROVIDER = {"openai": "openai", "anthropic": "anthropic", "gemini": "google_genai", "groq": "groq",
                      "mistral": "mistralai", "ollama": "ollama"}
PYDANTIC_PREFIX = {"openai": "openai", "anthropic": "anthropic", "gemini": "google-gla", "groq": "groq",
                   "mistral": "mistral", "ollama": "ollama"}


def parts() -> tuple[str, str]:
    provider, _, model = os.environ.get("LLM_SPEC", "openai:gpt-4o-mini").partition(":")
    return provider, model


def litellm_id() -> str:                      # smolagents (LiteLLMModel), OpenAI Agents SDK fallback, ADK fallback
    provider, model = parts()
    return f"{provider}/{model}"


def pydantic_ai_id() -> str:                  # Pydantic AI
    provider, model = parts()
    return f"{PYDANTIC_PREFIX[provider]}:{model}"


def langchain_model(temperature: float = 0.1):  # LangGraph agent
    from langchain.chat_models import init_chat_model

    provider, model = parts()
    return init_chat_model(model, model_provider=LANGCHAIN_PROVIDER[provider], temperature=temperature)


def openai_agents_model():                    # OpenAI Agents SDK
    provider, model = parts()
    if provider == "openai":
        return model
    from agents.extensions.models.litellm_model import LitellmModel  # pip install 'openai-agents[litellm]'

    return LitellmModel(model=litellm_id())


def adk_model():                              # Google ADK
    provider, model = parts()
    if provider == "gemini":
        return model
    from google.adk.models.lite_llm import LiteLlm  # pip install 'google-adk[extensions]'

    return LiteLlm(model=litellm_id())
