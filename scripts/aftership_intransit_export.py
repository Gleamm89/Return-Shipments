import os
import json
import requests
from datetime import datetime, timezone, timedelta
from openpyxl import Workbook

# =========================
# Config
# =========================
AFTERSHIP_KEY = os.environ["AFTERSHIP_API_KEY"]

# AfterShip Tracking API base (you used this earlier)
BASE_URL = "https://api.aftership.com/tracking/2026-01"

# Change this if you want a different status
AFTERSHIP_TAG = os.environ.get("AFTERSHIP_TAG", "Delivered")  # e.g. InTransit, Exception, OutForDelivery

# The custom field name in AfterShip you mentioned
ORDER_ID_CUSTOM_FIELD = "OrderID"

STATE_DIR = "state"
STATE_PATH = os.path.join(STATE_DIR, "handled.json")
DEDUP_DAYS = 30


# =========================
# Helpers
# =========================
def utcnow():
    return datetime.now(timezone.utc)


def load_state():
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_custom_field(tracking: dict, field_name: str) -> str:
    """
    AfterShip custom_fields can appear as:
      - dict: {"OrderID": "123", ...}
      - list: [{"name":"OrderID","value":"123"}, ...]
    This function supports both.
    """
    cf = tracking.get("custom_fields")

    if isinstance(cf, dict):
        val = cf.get(field_name)
        return "" if val is None else str(val)

    if isinstance(cf, list):
        for item in cf:
            if not isinstance(item, dict):
                continue
            if item.get("name") == field_name:
                val = item.get("value")
                return "" if val is None else str(val)

    return ""


def extract_last_checkpoint(tracking: dict) -> dict:
    """
    Robustly find a "last checkpoint" object across possible response shapes.
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
    Dedupe key includes TAG so a shipment can be handled once per status.
    """
    tag = tracking.get("tag") or AFTERSHIP_TAG or "UNKNOWN"
    slug = tracking.get("slug") or ""
    tn = tracking.get("tracking_number") or ""
    return f"{tag}/{slug}/{tn}"


def should_skip(tracking: dict, handled_state: dict, now: datetime) -> bool:
    k = key_for_tracking(tracking)
    last = handled_state.get(k)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False
        return False
    #return (now - last_dt) < timedelta(days=DEDUP_DAYS)
#line above to be discoded

def mark_handled(trackings: list[dict], handled_state: dict, now: datetime) -> None:
    for t in trackings:
        handled_state[key_for_tracking(t)] = now.isoformat()


# =========================
# AfterShip API
# =========================
def get_trackings_by_tag(limit=200) -> list[dict]:
    headers = {"Content-Type": "application/json", "as-api-key": AFTERSHIP_KEY}
    params = {
        "tag": AFTERSHIP_TAG,
        "limit": str(limit),
        # Optional if you tag return labels:
        # "shipment_tags": "returns",
        # Optional if you want only return-to-sender:
        # "return_to_sender": "true",
    }

    r = requests.get(f"{BASE_URL}/trackings", headers=headers, params=params, timeout=30)

    # Better error visibility in Actions logs
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

        # Location can be a single "location" string or split across fields.
        location = last_cp.get("location")
        if not location:
            parts = [last_cp.get("city"), last_cp.get("state"), last_cp.get("country_name")]
            location = " ".join([p for p in parts if p])

        rows.append({
            "tracking_number": t.get("tracking_number") or "",
            "carrier_slug": t.get("slug") or "",
            "status_tag": t.get("tag") or AFTERSHIP_TAG or "",
            "title": t.get("title") or "",

            # Map AfterShip custom field OrderID into a standard column
            "order_id": get_custom_field(t, ORDER_ID_CUSTOM_FIELD),

            "last_checkpoint_id": (last_cp.get("id") or last_cp.get("checkpoint_id") or ""),
            "last_checkpoint_time": (last_cp.get("checkpoint_time") or ""),
            "last_checkpoint_location": (location or ""),
            "updated_at": t.get("updated_at") or "",
        })
    return rows


def write_json(rows: list[dict], path: str) -> None:
    payload = {
        "generated_at": utcnow().isoformat(),
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
    ]

    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])

    wb.save(path)


def main():
    now = utcnow()
    handled = load_state()


    trackings = get_trackings_by_tag(limit=1)
    print(json.dumps(trackings[0], indent=2))

    
    new_trackings = [t for t in trackings if not should_skip(t, handled, now)]

    rows = normalize(new_trackings)

    os.makedirs("output", exist_ok=True)
    write_json(rows, "output/returns_intransit.json")
    write_xlsx(rows, "output/returns_intransit.xlsx")

    mark_handled(new_trackings, handled, now)
    save_state(handled)

    print(f"Tag={AFTERSHIP_TAG} API returned={len(trackings)} after_dedupe={len(new_trackings)}")


if __name__ == "__main__":
    main()
