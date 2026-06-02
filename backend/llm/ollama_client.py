import json
from typing import Tuple

from backend.core.logger import get_logger

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

llm = None
if ChatOllama is not None:
    try:
        llm = ChatOllama(model="qwen3:8b", temperature=0)
    except Exception as exc:
        logger.warning(
            "Ollama client initialization failed",
            extra={"error": str(exc)},
        )
        llm = None


def invoke_llm(prompt: str) -> str:
    if not prompt:
        return ""

    if llm is None:
        logger.warning(
            "Ollama invocation skipped because the client is unavailable",
            extra={"prompt": prompt[:200]},
        )
        return ""

    try:
        if HumanMessage is not None:
            response = llm.generate([[HumanMessage(content=prompt)]])
            if response and getattr(response, "generations", None):
                text = response.generations[0][0].text
                return text or ""
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
    if llm is None:
        return False, "Ollama client unavailable"

    try:
        response = invoke_llm("Please respond with the single word pong.")
        if response and "pong" in response.lower():
            return True, "Ollama model qwen3:8b is available"
        if response:
            return True, "Ollama responded successfully"
        return False, "Ollama returned an empty response"
    except Exception as exc:
        logger.warning(
            "Ollama availability check failed",
            extra={"error": str(exc)},
        )
        return False, str(exc)
