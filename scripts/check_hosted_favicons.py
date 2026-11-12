"""Compare the public Drone site's favicon links and bytes with the local web build."""

from pathlib import Path

from scripts.release.oracle_drone import ORIGINS, verify_hosted_favicons


if __name__ == "__main__":
    static = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    try:
        verify_hosted_favicons(ORIGINS["production"][0], static)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
    print("Verified home and tracking favicon links, media types and branded image bytes.")
