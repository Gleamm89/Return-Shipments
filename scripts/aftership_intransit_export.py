import os
import json
import requests
from datetime import datetime, timezone, timedelta
from openpyxl import Workbook

# =========================
# Config
# =========================
AFTERSHIP_KEY = os.environ["AFTERSHIP_API_KEY"]
BASE_URL = "https://api.aftership.com/tracking/2026-01"

AFTERSHIP_TAG = os.environ.get("AFTERSHIP_TAG", "Delivered")  # e.g. InTransit, Delivered, Exception
ORDER_ID_CUSTOM_FIELD = os.environ.get("ORDER_ID_CUSTOM_FIELD", "OrderID")

# Dedupe controls (set in workflow env if you want)
DEDUP_DAYS = int(os.environ.get("DEDUP_DAYS", "30"))          # set 0 to disable
DEDUP_ENABLED = os.environ.get("DEDUP_ENABLED", "1") == "1"   # set 0 to disable
DEBUG_AFTERSHIP = os.environ.get("DEBUG_AFTERSHIP", "0") == "1"

STATE_DIR = "state"
STATE_PATH = os.path.join(STATE_DIR, "handled.json")


# =========================
# Helpers
# =========================
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_state() -> dict:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_custom_field(tracking: dict, field_name: str) -> str:
    """
    custom_fields can be:
      - dict: {"OrderID": "123", ...}
      - list: [{"name":"OrderID","value":"123"}, ...]
    """
    cf = tracking.get("custom_fields")

    if isinstance(cf, dict):
        val = cf.get(field_name)
        return "" if val is None else str(val)

    if isinstance(cf, list):
        for item in cf:
            if isinstance(item, dict) and item.get("name") == field_name:
                val = item.get("value")
                return "" if val is None else str(val)

    return ""


def get_all_custom_fields(tracking: dict) -> dict:
    """
    Return all custom fields as a plain dict[str, str] (JSON-friendly).
    Supports both dict and list shapes.
    """
    cf = tracking.get("custom_fields")

    if isinstance(cf, dict):
        return {str(k): "" if v is None else str(v) for k, v in cf.items()}

    if isinstance(cf, list):
        out = {}
        for item in cf:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if name is None:
                continue
            val = item.get("value")
            out[str(name)] = "" if val is None else str(val)
        return out

    return {}


def extract_last_checkpoint(tracking: dict) -> dict:
    """
    Robustly find a "last checkpoint" object across possible shapes.
    Tries:
      - last_checkpoint
      - latest_checkpoint
      - last element of checkpoints[]
    """
    last_cp = tracking.get("last_checkpoint") or tracking.get("latest_checkpoint") or {}
    if isinstance(last_cp, dict) and last_cp:
        return last_cp

    cps = tracking.get("checkpoints") or []
    if isinstance(cps, list) and cps:
        last = cps[-1]
        return last if isinstance(last, dict) else {}

    return {}


def key_for_tracking(tracking: dict) -> str:
    """
    Includes tag so the same tracking can be handled once per status.
    """
    tag = tracking.get("tag") or AFTERSHIP_TAG or "UNKNOWN"
    slug = tracking.get("slug") or ""
    tn = tracking.get("tracking_number") or ""
    return f"{tag}/{slug}/{tn}"


def should_skip(tracking: dict, handled_state: dict, now: datetime) -> bool:
    """
    Skip if we handled this key within the last DEDUP_DAYS (if enabled).
    Set DEDUP_ENABLED=0 or DEDUP_DAYS=0 to disable.
    """
    if not DEDUP_ENABLED or DEDUP_DAYS <= 0:
        return False

    k = key_for_tracking(tracking)
    last = handled_state.get(k)
    if not last:
        return False

    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False

    return (now - last_dt) < timedelta(days=DEDUP_DAYS)


def mark_handled(trackings: list[dict], handled_state: dict, now: datetime) -> None:
    for t in trackings:
        handled_state[key_for_tracking(t)] = now.isoformat()


# =========================
# AfterShip API
# =========================
def get_trackings_by_tag(limit: int = 200) -> list[dict]:
    headers = {"Content-Type": "application/json", "as-api-key": AFTERSHIP_KEY}
    params = {
        "tag": AFTERSHIP_TAG,
        "limit": str(limit),
    }

    r = requests.get(f"{BASE_URL}/trackings", headers=headers, params=params, timeout=30)

    if not r.ok:
        print("AfterShip request failed.")
        print("URL:", r.url)
        print("Status:", r.status_code)
        print("Body:", r.text[:2000])
        r.raise_for_status()

    data = r.json()
    return data.get("data", {}).get("trackings", [])


# =========================
# Output
# =========================
def normalize(trackings: list[dict]) -> list[dict]:
    rows = []
    for t in trackings:
        last_cp = extract_last_checkpoint(t)

        location = last_cp.get("location")
        if not location:
            parts = [last_cp.get("city"), last_cp.get("state"), last_cp.get("country_name")]
            location = " ".join([p for p in parts if p])

        custom_fields = get_all_custom_fields(t)

        rows.append({
            "tracking_number": t.get("tracking_number") or "",
            "carrier_slug": t.get("slug") or "",
            "status_tag": t.get("tag") or AFTERSHIP_TAG or "",
            "title": t.get("title") or "",

            # Your specific mapping (used by the UI column "Order ID")
            "order_id": get_custom_field(t, ORDER_ID_CUSTOM_FIELD),

            # All custom fields in JSON export
            "custom_fields": custom_fields,

            # Also provide a stringified version for XLSX convenience
            "custom_fields_json": json.dumps(custom_fields, ensure_ascii=False),

            "last_checkpoint_id": (last_cp.get("id") or last_cp.get("checkpoint_id") or ""),
            "last_checkpoint_time": (last_cp.get("checkpoint_time") or ""),
            "last_checkpoint_location": (location or ""),
            "updated_at": t.get("updated_at") or "",
        })
    return rows


def write_json(rows: list[dict], path: str) -> None:
    payload = {
        "generated_at": utcnow().isoformat(),
        "tag": AFTERSHIP_TAG,
        "dedup_enabled": DEDUP_ENABLED,
        "dedup_days": DEDUP_DAYS,
        "count": len(rows),
        "items": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_xlsx(rows: list[dict], path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "AfterShip"

    headers = [
        "tracking_number",
        "carrier_slug",
        "status_tag",
        "order_id",
        "last_checkpoint_id",
        "last_checkpoint_time",
        "last_checkpoint_location",
        "updated_at",
        "title",
        "custom_fields_json",
    ]

    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])

    wb.save(path)


def main():
    now = utcnow()
    handled = load_state()

    trackings = get_trackings_by_tag(limit=200)

    if DEBUG_AFTERSHIP and trackings:
        print("=== RAW AFTERSHIP TRACKING (1 item) ===")
        print(json.dumps(trackings[0], indent=2))
        print("=== END RAW TRACKING ===")

    new_trackings = [t for t in trackings if not should_skip(t, handled, now)]
    rows = normalize(new_trackings)

    os.makedirs("output", exist_ok=True)
    write_json(rows, "output/returns_intransit.json")
    write_xlsx(rows, "output/returns_intransit.xlsx")

    # Only update state if dedupe is enabled (keeps behavior predictable)
    if DEDUP_ENABLED and DEDUP_DAYS > 0:
        mark_handled(new_trackings, handled, now)
        save_state(handled)

    print(f"Tag={AFTERSHIP_TAG} API returned={len(trackings)} after_dedupe={len(new_trackings)} "
          f"(dedup_enabled={DEDUP_ENABLED} dedup_days={DEDUP_DAYS})")


if __name__ == "__main__":
    main()
