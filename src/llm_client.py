# src/llm_client.py
from typing import Any
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage
from src.config import settings, GROQ_MODEL
import structlog

logger = structlog.get_logger()


def _is_rate_limit_error(err_str: str) -> bool:
    err_lower = err_str.lower()
    precise_markers = [
        "429",
        "413",
        "rate_limit_exceeded",
        "rate limit exceeded",
        "too many requests",
        "resource_exhausted",
        "quota exceeded",
        "quota_exceeded",
        "tokens per minute",
    ]
    return any(marker in err_lower for marker in precise_markers)


def _get_base_model(model: Any) -> Any:
    """Extrait le modèle sous-jacent si le modèle est déjà un RunnableBinding."""
    while hasattr(model, "bound"):
        model = model.bound
    return model


def _invoke_underlying_model(model: Any, messages) -> ChatResult:
    response = model.invoke(messages)
    if isinstance(response, ChatResult):
        return response
    if not isinstance(response, AIMessage):
        response = AIMessage(content=str(response))
    return ChatResult(generations=[ChatGeneration(message=response)])


async def _ainvoke_underlying_model(model: Any, messages) -> ChatResult:
    response = await model.ainvoke(messages)
    if isinstance(response, ChatResult):
        return response
    if not isinstance(response, AIMessage):
        response = AIMessage(content=str(response))
    return ChatResult(generations=[ChatGeneration(message=response)])


class FallbackChatModel(BaseChatModel):
    """Wrapper de routage : Primary -> Fallback 1 -> Fallback 2, avec bascule
    automatique uniquement en cas de rate limit / quota épuisé."""
    primary_llm: Any
    fallback_llm: Any
    last_fallback_llm: Any = None

    def __init__(self, primary_llm: Any, fallback_llm: Any, last_fallback_llm: Any = None, **kwargs):
        super().__init__(primary_llm=primary_llm, fallback_llm=fallback_llm, last_fallback_llm=last_fallback_llm, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "chain_fallback_chat_model"

    def bind_tools(self, tools, **kwargs):
        base_primary = _get_base_model(self.primary_llm)
        bound_primary = base_primary.bind_tools(tools, **kwargs) if hasattr(base_primary, "bind_tools") else base_primary

        base_fallback = _get_base_model(self.fallback_llm) if self.fallback_llm else None
        bound_fallback = base_fallback
        if base_fallback and hasattr(base_fallback, "bind_tools"):
            try:
                bound_fallback = base_fallback.bind_tools(tools, **kwargs)
            except Exception as e:
                logger.warning("Échec du bind_tools sur fallback_llm", error=str(e))

        base_last = _get_base_model(self.last_fallback_llm) if self.last_fallback_llm else None
        bound_last = base_last
        if base_last and hasattr(base_last, "bind_tools"):
            try:
                bound_last = base_last.bind_tools(tools, **kwargs)
            except Exception as e:
                logger.warning("Échec du bind_tools sur last_fallback_llm", error=str(e))

        return FallbackChatModel(
            primary_llm=bound_primary,
            fallback_llm=bound_fallback,
            last_fallback_llm=bound_last
        )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            return _invoke_underlying_model(self.primary_llm, messages)
        except Exception as e:
            err_str = str(e)
            if _is_rate_limit_error(err_str):
                logger.warning("🚨 Quota épuisé sur le modèle principal. Basculement sur Gemini...", error=err_str)
                try:
                    return _invoke_underlying_model(self.fallback_llm, messages)
                except Exception as e2:
                    if self.last_fallback_llm:
                        logger.warning("🚨 Échec de Gemini. Dernier recours : basculement sur Ollama local...", error=str(e2))
                        return _invoke_underlying_model(self.last_fallback_llm, messages)
                    raise e2
            raise e

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            return await _ainvoke_underlying_model(self.primary_llm, messages)
        except Exception as e:
            err_str = str(e)
            if _is_rate_limit_error(err_str):
                logger.warning("🚨 Quota épuisé sur le modèle principal. Basculement asynchrone sur Gemini...", error=err_str)
                try:
                    return await _ainvoke_underlying_model(self.fallback_llm, messages)
                except Exception as e2:
                    if self.last_fallback_llm:
                        logger.warning("🚨 Échec de Gemini. Dernier recours : basculement sur Ollama local...", error=str(e2))
                        return await _ainvoke_underlying_model(self.last_fallback_llm, messages)
                    raise e2
            raise e


def get_llm(temperature: float = 0):
    ollama_base = settings.ollama_base_url.rstrip("/")
    if not ollama_base.endswith("/v1"):
        ollama_base = f"{ollama_base}/v1"

    ollama_llm = ChatOpenAI(
        base_url=ollama_base,
        model="llama3.2",
        api_key="ollama",
        temperature=temperature,
        timeout=120.0
    )

    forced_provider = getattr(settings, "forced_llm_provider", "").lower()
    if forced_provider == "ollama":
        logger.info("⚙️ Fournisseur LLM forcé manuellement : Ollama")
        return ollama_llm

    gemini_llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=temperature
    )

    if forced_provider == "gemini":
        logger.info("⚙️ Fournisseur LLM forcé manuellement : Gemini")
        return gemini_llm

    groq_llm = None
    try:
        if settings.groq_api_key:
            groq_llm = ChatGroq(temperature=temperature, model_name=GROQ_MODEL, api_key=settings.groq_api_key)
    except Exception as e:
        logger.warning("Impossible d'initialiser Groq initialement", error=str(e))

    if groq_llm:
        return FallbackChatModel(
            primary_llm=groq_llm,
            fallback_llm=gemini_llm,
            last_fallback_llm=ollama_llm
        )

    return gemini_llm


llm = get_llm(temperature=0)