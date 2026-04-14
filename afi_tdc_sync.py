import datetime
import json
import os
import time
from typing import Optional, Tuple


def ensure_sync_dirs(sync_root: str) -> dict:
    requests_dir = os.path.join(sync_root, "requests")
    processing_dir = os.path.join(sync_root, "processing")
    done_dir = os.path.join(sync_root, "done")
    failed_dir = os.path.join(sync_root, "failed")
    for path in (sync_root, requests_dir, processing_dir, done_dir, failed_dir):
        os.makedirs(path, exist_ok=True)
    return {
        "root": sync_root,
        "requests": requests_dir,
        "processing": processing_dir,
        "done": done_dir,
        "failed": failed_dir,
    }


def heartbeat_path(sync_root: str) -> str:
    return os.path.join(sync_root, "listener_heartbeat.json")


def write_heartbeat(sync_root: str, payload: dict) -> str:
    path = heartbeat_path(sync_root)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def read_heartbeat(sync_root: str) -> Optional[dict]:
    path = heartbeat_path(sync_root)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_request_id(group_name: str, step_index: int, voltage: float) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    voltage_tag = f"{voltage:.2f}V".replace(".", "p")
    return f"{ts}_{group_name}_step{step_index:03d}_{voltage_tag}"


def enqueue_request(sync_dirs: dict, payload: dict) -> Tuple[str, str]:
    request_id = payload["request_id"]
    request_path = os.path.join(sync_dirs["requests"], f"{request_id}.json")
    done_path = os.path.join(sync_dirs["done"], f"{request_id}.json")
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return request_path, done_path


def claim_next_request(sync_dirs: dict) -> Tuple[Optional[dict], Optional[str]]:
    candidates = sorted(
        name for name in os.listdir(sync_dirs["requests"]) if name.lower().endswith(".json")
    )
    for name in candidates:
        src = os.path.join(sync_dirs["requests"], name)
        dst = os.path.join(sync_dirs["processing"], name)
        try:
            os.replace(src, dst)
        except FileNotFoundError:
            continue
        except PermissionError:
            continue
        with open(dst, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload, dst
    return None, None


def complete_request(sync_dirs: dict, processing_path: str, payload: dict) -> str:
    request_id = payload["request_id"]
    done_path = os.path.join(sync_dirs["done"], f"{request_id}.json")
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if processing_path and os.path.exists(processing_path):
        os.remove(processing_path)
    return done_path


def fail_request(sync_dirs: dict, processing_path: str, payload: dict, error_message: str) -> str:
    request_id = payload["request_id"]
    payload = dict(payload)
    payload["status"] = "failed"
    payload["error"] = error_message
    failed_path = os.path.join(sync_dirs["failed"], f"{request_id}.json")
    with open(failed_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if processing_path and os.path.exists(processing_path):
        os.remove(processing_path)
    return failed_path


def wait_for_done(done_path: str, failed_path: str, timeout_s: float, poll_s: float = 0.1) -> dict:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if os.path.exists(done_path):
            with open(done_path, "r", encoding="utf-8") as f:
                return json.load(f)
        if os.path.exists(failed_path):
            with open(failed_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            raise RuntimeError(payload.get("error", "TDC sync request failed."))
        time.sleep(poll_s)
    raise TimeoutError(f"Timed out waiting for sync result: {os.path.basename(done_path)}")


def wait_for_claim_or_done(
    request_path: str,
    processing_path: str,
    done_path: str,
    failed_path: str,
    timeout_s: float,
    poll_s: float = 0.1,
) -> str:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if os.path.exists(processing_path):
            return "processing"
        if os.path.exists(done_path):
            return "done"
        if os.path.exists(failed_path):
            return "failed"
        if not os.path.exists(request_path):
            return "claimed"
        time.sleep(poll_s)
    raise TimeoutError(f"Timed out waiting for sync worker to claim: {os.path.basename(request_path)}")
