"""Interactive mock client for posting space status updates.

Usage:
    .venv/bin/python tests/mock_updater_client.py

Input format (one update per line):
    <sensor_id> <f|o>

Examples:
    s1 free
    s2 occupied

Commands:
    help   Show command help
    quit   Exit the program
    exit   Exit the program
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib import error, request

ENDPOINT = "http://localhost:8000/space/update-state"


def parse_status_token(token: str) -> bool | None:
    """Map user-friendly status words to the API's boolean `occupied` field."""
    normalized = token.strip().lower()
    if normalized in {"occupied", "occ", "o"}:
        return True
    if normalized in {"free", "f"}:
        return False
    else:
        return None


def build_payload(sensor_id: str, occupied: bool) -> dict:
    """Build JSON body matching `SpaceUpdate` in the FastAPI route."""
    return {
        "id": sensor_id,
        "occ": occupied,
        "dt": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def post_update(body: dict) -> tuple[int, str]:
    """POST one status update and return (status_code, response_text)."""
    req = request.Request(
        url=ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            text = response.read().decode("utf-8", errors="replace")
            return response.status, text
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, text


def print_help() -> None:
    """Print interactive usage help."""
    print("Input format: <sensor_id> <free|occupied>")
    print("Examples: s1 free | sensor-2 occupied")
    print("Commands: help, quit, exit")


def main() -> int:
    print(f"Mock updater ready. Posting to: {ENDPOINT}")
    print_help()

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return 0

        if not line:
            continue

        cmd = line.lower()
        if cmd == "q":
            print("Exiting.")
            return 0
        if cmd == "h":
            print_help()
            continue

        parts = line.split()
        if len(parts) != 2:
            print("Invalid input. Expected: <sensor_id> <free|occupied>")
            continue

        sensor_id, status_token = parts
        occupied = parse_status_token(status_token)
        if occupied is None:
            print("Invalid status. Use 'free' or 'occupied'.")
            continue

        payload = build_payload(sensor_id, occupied)

        try:
            status_code, response_text = post_update(payload)
        except error.URLError as exc:
            print(f"Request failed: {exc.reason}")
            continue
        except Exception as exc:  # pragma: no cover - safety for manual script use
            print(f"Unexpected error: {exc}")
            continue

        state_label = "occupied" if occupied else "free"
        print(f"[{status_code}] {sensor_id} -> {state_label} @ {payload['dt']}")
        if response_text:
            print(response_text)


if __name__ == "__main__":
    raise SystemExit(main())
