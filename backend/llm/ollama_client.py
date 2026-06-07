import json
from typing import Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.config import settings
from backend.core.logger import get_logger
from backend.startup.ollama_validator import get_ollama_status

logger = get_logger(__name__)

try:
    from langchain_core.messages import HumanMessage
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


def _extract_text_from_response(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if content:
                        return str(content)
                text = choice.get("text")
                if text:
                    return str(text)
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if content:
                        return str(content)

    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and "content" in item:
                return str(item["content"])

    return ""


def _invoke_http_llm(prompt: str) -> str:
    if not prompt:
        return ""

    completion_paths = ["/v1/completions", "/v1/chat/completions", "/api/chat/completions"]
    for completion_path in completion_paths:
        if completion_path == "/v1/completions":
            body = json.dumps({
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "temperature": 0,
                "max_tokens": 1024,
            }).encode("utf-8")
        else:
            body = json.dumps({
                "model": settings.OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 1024,
            }).encode("utf-8")

        request = Request(
            urljoin(settings.OLLAMA_SERVER_URL, completion_path),
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
                text = _extract_text_from_response(payload)
                if text:
                    return text
        except (HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "Ollama HTTP client failed for %s",
                completion_path,
                extra={"error": str(exc), "model": settings.OLLAMA_MODEL},
            )

    return ""


def invoke_llm(prompt: str) -> str:
    if not prompt:
        return ""

    llm = _build_llm_client()
    if llm is None:
        logger.info(
            "Ollama HTTP fallback invocation",
            extra={"model": settings.OLLAMA_MODEL, "prompt_preview": prompt[:120]},
        )
        return _invoke_http_llm(prompt)

    try:
        logger.info("Invoking Ollama client", extra={"model": settings.OLLAMA_MODEL, "prompt_preview": prompt[:120]})
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
        result = llm.predict(prompt) or ""
        if result:
            return result
    except Exception as exc:
        logger.warning(
            "Ollama predict call failed, trying HTTP fallback",
            extra={"error": str(exc)},
        )

    return _invoke_http_llm(prompt)


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
