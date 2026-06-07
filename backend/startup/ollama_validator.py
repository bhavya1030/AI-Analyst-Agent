import json
import shutil
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.config import settings

DEFAULT_TIMEOUT_SECONDS = 6


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
        urljoin(settings.OLLAMA_SERVER_URL, "/v1/models"),
        headers={"Accept": "application/json"},
        method="GET",
    )
    payload = _read_json_response(settings.OLLAMA_SERVER_URL, request)

    if isinstance(payload, dict) and "models" in payload:
        payload = payload["models"]

    models: list[str] = []
    if isinstance(payload, list):
        for item in payload:
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


def _test_model_response(model_name: str) -> bool:
    prompt = "Please respond with the single word pong."
    body = json.dumps({
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 10,
    }).encode("utf-8")
    request = Request(
        urljoin(settings.OLLAMA_SERVER_URL, "/v1/chat/completions"),
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        payload = _read_json_response(settings.OLLAMA_SERVER_URL, request)
        text = _extract_text_from_completion(payload)
        return "pong" in text.lower()
    except (HTTPError, URLError, ValueError, json.JSONDecodeError):
        return False


def get_ollama_status() -> dict[str, Any]:
    model_name = settings.OLLAMA_MODEL
    status = {
        "ollama_installed": False,
        "ollama_running": False,
        "model_available": False,
        "model_name": model_name,
    }

    if shutil.which("ollama") is None:
        return status

    status["ollama_installed"] = True

    if not _check_server_root():
        return status

    status["ollama_running"] = True

    try:
        available_models = _fetch_model_list()
    except (HTTPError, URLError, ValueError, json.JSONDecodeError):
        return status

    normalized = model_name.strip().lower()
    available_names = [name.strip().lower() for name in available_models if isinstance(name, str)]
    if normalized not in available_names:
        return status

    if _test_model_response(model_name):
        status["model_available"] = True

    return status
