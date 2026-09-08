import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"
TARGET_URL = "https://example.com"


def main() -> int:
    target = request_json(
        "POST",
        "/targets",
        {"name": "Smoke Test Target", "url": TARGET_URL},
    )
    target_id = target["id"]

    request_json("POST", f"/targets/{target_id}/check")
    target = wait_for_terminal_status(target_id)
    if target["status"] not in {"OK", "Changed"}:
        raise RuntimeError(f"Unexpected first check status: {target['status']}")

    request_json("POST", f"/targets/{target_id}/check")
    target = wait_for_terminal_status(target_id)

    checks = request_json("GET", f"/targets/{target_id}/checks")
    if checks:
        check = checks[0]
        request_json("POST", f"/checks/{check['id']}/ack")
        request_json(
            "POST",
            f"/targets/{target_id}/baseline/approve",
            {"snapshot_id": check["current_snapshot_id"]},
        )

    print(f"Smoke test completed for target {target_id} with status {target['status']}")
    return 0


def wait_for_terminal_status(target_id: str) -> dict:
    for _ in range(60):
        target = request_json("GET", f"/targets/{target_id}")
        if target["status"] != "Checking":
            return target
        time.sleep(1)
    raise TimeoutError(f"Target did not finish checking: {target_id}")


def request_json(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {body}") from exc
    return json.loads(body) if body else None


if __name__ == "__main__":
    raise SystemExit(main())
