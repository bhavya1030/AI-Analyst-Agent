import json
import shutil
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60


def _read_json_response(url: str, request: Request) -> Any:
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        payload = response.read().decode("utf-8", errors="ignore")
        return json.loads(payload)


def _check_server_root() -> bool:
    try:
        request = Request(settings.OLLAMA_SERVER_URL, headers={"Accept": "text/plain"}, method="GET")
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS):
            return True
    except (HTTPError, URLError, ValueError):
        return False


def _fetch_model_list() -> list[str]:
    request = Request(
        urljoin(settings.OLLAMA_SERVER_URL, "/api/tags"),
        headers={"Accept": "application/json"},
        method="GET",
    )
    payload = _read_json_response(settings.OLLAMA_SERVER_URL, request)

    models_payload = []
    if isinstance(payload, dict):
        models_payload = payload.get("models", [])
    elif isinstance(payload, list):
        models_payload = payload

    models: list[str] = []
    if isinstance(models_payload, list):
        for item in models_payload:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                models.append(item.get("name") or item.get("id") or item.get("model") or "")
    return [model for model in models if isinstance(model, str) and model]


def _extract_text_from_completion(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    text_parts: list[str] = []
    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    text_parts.append(str(message.get("content", "")))
                text_parts.append(str(choice.get("text", "")))
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    text_parts.append(str(delta.get("content", "")))

    if not text_parts and isinstance(payload.get("output"), list):
        for item in payload["output"]:
            if isinstance(item, dict) and "content" in item:
                text_parts.append(str(item["content"]))

    return " ".join(part for part in text_parts if part)


def _test_model_response(model_name: str) -> tuple[bool, str, str]:
    prompt = "Respond with pong"
    completion_paths = [
        "/v1/completions",
        "/v1/chat/completions",
        "/api/chat/completions",
    ]

    for completion_path in completion_paths:
        if completion_path == "/v1/completions":
            body = json.dumps({
                "model": model_name,
                "prompt": prompt,
                "temperature": 0,
                "max_tokens": 10,
            }).encode("utf-8")
        else:
            body = json.dumps({
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 10,
            }).encode("utf-8")

        request = Request(
            urljoin(settings.OLLAMA_SERVER_URL, completion_path),
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            payload = _read_json_response(settings.OLLAMA_SERVER_URL, request)
            text = _extract_text_from_completion(payload)
            if "pong" in text.lower():
                return True, completion_path, text
            return False, completion_path, text
        except (HTTPError, URLError, ValueError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            logger.warning(
                "Ollama inference test failed for endpoint %s",
                completion_path,
                extra={"model": model_name, "error": str(exc)},
            )

    return False, "", ""


def validate_model_inference() -> dict[str, Any]:
    model_name = settings.OLLAMA_MODEL
    try:
        success, endpoint, response_text = _test_model_response(model_name)
        if success:
            logger.info("Inference successful", extra={"model": model_name, "endpoint": endpoint})
            return {
                "inference_successful": True,
                "endpoint": endpoint,
                "response_text": response_text,
            }

        failure_reason = "Model inference did not return pong"
        logger.warning(
            "Inference failed",
            extra={"model": model_name, "endpoint": endpoint, "response_text": response_text},
        )
        return {
            "inference_successful": False,
            "endpoint": endpoint,
            "response_text": response_text,
            "failure_reason": failure_reason,
        }
    except TimeoutError as exc:
        logger.warning("Ollama inference timed out", extra={"model": model_name, "error": str(exc)})
        return {
            "inference_successful": False,
            "endpoint": "",
            "response_text": "",
            "failure_reason": "timeout",
        }
    except Exception as exc:
        logger.warning("Ollama inference failed", extra={"model": model_name, "error": str(exc)})
        return {
            "inference_successful": False,
            "endpoint": "",
            "response_text": "",
            "failure_reason": str(exc),
        }


def get_ollama_status() -> dict[str, Any]:
    model_name = settings.OLLAMA_MODEL
    status = {
        "ollama_installed": False,
        "ollama_running": False,
        "model_available": False,
        "model_name": model_name,
        "configured_model": model_name,
        "installed_models": [],
        "failure_reason": None,
    }

    logger.info("Configured Ollama model: %s", model_name)

    if shutil.which("ollama") is None:
        status["failure_reason"] = "Ollama executable not found"
        return status

    status["ollama_installed"] = True

    if not _check_server_root():
        status["failure_reason"] = f"Ollama server not reachable at {settings.OLLAMA_SERVER_URL}"
        return status

    logger.info("Ollama reachable")
    status["ollama_running"] = True

    try:
        available_models = _fetch_model_list()
    except (HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Failed to fetch Ollama models", extra={"error": str(exc)})
        status["failure_reason"] = "Failed to query Ollama model tags"
        return status

    status["installed_models"] = available_models
    normalized = model_name.strip().lower()
    available_names = [name.strip().lower() for name in available_models if isinstance(name, str)]
    if normalized not in available_names:
        status["failure_reason"] = f"Configured model {model_name} not found among installed models"
        return status

    status["model_available"] = True
    logger.info("Model found: %s", model_name)
    return status
