import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import settings
from backend.startup.ollama_validator import get_ollama_status


def main() -> int:
    status = get_ollama_status()

    if not status["ollama_installed"]:
        print("✗ Ollama executable not found")
        return 1

    print("✓ Ollama installed")

    if not status["ollama_running"]:
        print("✗ Ollama server not running at", settings.OLLAMA_SERVER_URL)
        return 1

    print("✓ Ollama server running")

    if not status["model_available"]:
        print(f"✗ Model {status['model_name']} not available")
        return 1

    print(f"✓ {status['model_name']} available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
