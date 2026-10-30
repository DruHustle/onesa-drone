"""Download the immutable CI scanner with bounded transport retries."""

import subprocess
import time

SCANNER = "aquasec/trivy@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa"


def main() -> int:
    for attempt in range(3):
        try:
            result = subprocess.run(["docker", "pull", SCANNER], timeout=120, check=False)
            if result.returncode == 0:
                return 0
        except subprocess.TimeoutExpired:
            pass
        if attempt < 2:
            time.sleep(5)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
