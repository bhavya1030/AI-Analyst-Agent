import json
from typing import Tuple

from backend.config import settings
from backend.core.logger import get_logger
from backend.startup.ollama_validator import get_ollama_status

logger = get_logger(__name__)

try:
    from langchain.schema import HumanMessage
    from langchain_community.chat_models import ChatOllama
except Exception as exc:
    HumanMessage = None
    ChatOllama = None
    logger.warning(
        "Ollama import failed",
        extra={"error": str(exc)},
    )

_llm_client = None


def _build_llm_client():
    global _llm_client
    if _llm_client is not None:
        return _llm_client

    if ChatOllama is None:
        return None

    try:
        _llm_client = ChatOllama(model=settings.OLLAMA_MODEL, temperature=0)
        return _llm_client
    except Exception as exc:
        logger.warning(
            "Ollama client initialization failed",
            extra={"error": str(exc)},
        )
        _llm_client = None
        return None


def invoke_llm(prompt: str) -> str:
    if not prompt:
        return ""

    llm = _build_llm_client()
    if llm is None:
        logger.warning(
            "Ollama invocation skipped because the client is unavailable",
            extra={"prompt": prompt[:200]},
        )
        return ""

    try:
        if HumanMessage is not None:
            response = llm.generate([[HumanMessage(content=prompt)]])
            generations = getattr(response, "generations", None)
            if generations and isinstance(generations, list) and generations[0]:
                text = getattr(generations[0][0], "text", None)
                if text:
                    return str(text)
    except Exception as exc:
        logger.warning(
            "Ollama generate call failed, trying predict fallback",
            extra={"error": str(exc)},
        )

    try:
        return llm.predict(prompt) or ""
    except Exception as exc:
        logger.warning(
            "Ollama predict call failed",
            extra={"error": str(exc)},
        )
        return ""


def check_ollama_availability() -> Tuple[bool, str]:
    status = get_ollama_status()
    if status["ollama_installed"] and status["ollama_running"] and status["model_available"]:
        return True, f"Ollama model {status['model_name']} is available"

    if not status["ollama_installed"]:
        return False, "Ollama executable unavailable"

    if not status["ollama_running"]:
        return False, "Ollama server unavailable"

    if not status["model_available"]:
        return False, f"Model {status['model_name']} unavailable"

    return False, "Ollama check failed"
