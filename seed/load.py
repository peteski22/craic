#!/usr/bin/env python3
"""Load seed knowledge units into the CRAIC team store.

Reads seed/knowledge_units.json and POSTs each unit to the running team API.
After creation, calls /confirm or /flag the appropriate number of times to
reach the target confidence score defined by _target_confidence.

Usage:
    python seed/load.py [--url http://localhost:8742]

The team API must be running before this script is executed.
"""

import argparse
import json
import math
import urllib.error
import urllib.request
from pathlib import Path

SEED_FILE = Path(__file__).parent / "knowledge_units.json"


def _post(url: str, body: dict | None = None) -> dict:
    """POST JSON to url and return parsed response. Raises on HTTP error."""
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {url}: {body_text}") from exc


def _check_health(base_url: str) -> None:
    req = urllib.request.Request(f"{base_url}/health")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            if result.get("status") != "ok":
                raise SystemExit(f"Team API health check failed: {result}")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise SystemExit(f"Team API health check returned HTTP {exc.code}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach team API at {base_url}: {exc.reason}\n"
            "Make sure the Docker container is running: cd team-api && docker compose up -d"
        ) from exc


def _confirms_needed(target: float) -> int:
    """Number of /confirm calls to reach target confidence from 0.5."""
    return max(0, math.ceil((target - 0.5) / 0.1 - 1e-9))


def _flags_needed(target: float) -> int:
    """Number of /flag calls to reach target confidence from 0.5."""
    return max(0, math.ceil((0.5 - target) / 0.15 - 1e-9))


def load(base_url: str) -> None:
    units = json.loads(SEED_FILE.read_text())
    print(f"Loading {len(units)} seed units into {base_url}\n")

    for i, unit in enumerate(units, 1):
        target = unit.get("_target_confidence", 0.5)
        flag_reason = unit.get("_flag_reason", "stale")

        # Strip loader-only keys before posting
        payload = {k: v for k, v in unit.items() if not k.startswith("_")}

        # Create the unit
        result = _post(f"{base_url}/propose", payload)
        unit_id = result["id"]

        if target > 0.5:
            n = _confirms_needed(target)
            for _ in range(n):
                _post(f"{base_url}/confirm/{unit_id}")
        elif target < 0.5:
            n = _flags_needed(target)
            for _ in range(n):
                _post(f"{base_url}/flag/{unit_id}", {"reason": flag_reason})

        summary = unit["insight"]["summary"][:60]
        print(f"  [{i:2d}] {unit_id[:20]}  conf={target:.2f}  {summary}")

    print(f"\n✓ {len(units)} units loaded.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://localhost:8742",
        help="Base URL of the team API (default: http://localhost:8742)",
    )
    args = parser.parse_args()

    _check_health(args.url)
    load(args.url)


if __name__ == "__main__":
    main()
