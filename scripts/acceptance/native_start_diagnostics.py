"""Privacy-preserving transport counters for the disposable installed fixture."""

import json
from pathlib import Path


def read_start_diagnostics(path):
    """Only bounded counters from the disposable native start route may leave it."""
    keys = {"attempts", "responses200", "responsesOther2xx", "responses3xx",
            "responses4xx", "responses5xx", "responsesOther", "proxyErrors"}
    try:
        with Path(path).open("rb") as source:
            raw = source.read(1025)
        if len(raw) > 1024:
            raise ValueError("oversized")
        value = json.loads(raw)
        if (not isinstance(value, dict) or set(value) != keys | {"version"}
                or type(value["version"]) is not int or value["version"] != 1
                or any(type(value[key]) is not int or not 0 <= value[key] <= 999 for key in keys)):
            raise ValueError("shape")
        return {"status": "recorded", **value}
    except FileNotFoundError:
        return {"status": "not-recorded"}
    except (OSError, ValueError, TypeError):
        return {"status": "invalid-diagnostics"}

