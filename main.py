import uvicorn
import json
import sys
from pathlib import Path
from core.logger import monitor

def load_network_config(file_path="src/test_config.json"):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        monitor.log_error("CONFIG_LOAD_FAIL", e, message="Could not read test_config.json")
        sys.exit(1)


def main() -> None:
    config = load_network_config()
    api_host = config.get("ip_address", "127.0.0.1")
    api_port = int(config.get("api_port", 8000))

    monitor.log_event("UVICORN_STARTUP",
                      {"host": api_host, "port": api_port},
                      message="Starting ASGI Server Hub")
    try:
        uvicorn.run(
            "api:app",
            host=api_host,
            port=api_port,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        monitor.log_error("UVICORN_CRASH", e, message="Critical failure in ASGI server")
    finally:
        monitor.log_event("UVICORN_STOPPED", message="Main process exited")

if __name__ == "__main__":
    main()