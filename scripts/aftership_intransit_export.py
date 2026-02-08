import os
import json
import requests
from datetime import datetime, timezone, timedelta
from openpyxl import Workbook

AFTERSHIP_KEY = os.environ["AFTERSHIP_API_KEY"]
BASE_URL = "https://api.aftership.com/tracking/2026-01"

STATE_DIR = "state"
STATE_PATH = os.path.join(STATE_DIR, "handled.json")
DEDUP_DAYS = 30

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

def get_intransit_trackings(limit=200):
    headers = {"Content-Type": "application/json", "as-api-key": AFTERSHIP_KEY}
    params = {
        "tag": "Delivered",
        "limit": str(limit),
        # Optional if you tag return labels:
        # "shipment_tags": "returns"
        # Optional if you want return-to-sender items only:
        # "return_to_sender": "true",
    }

    r = requests.get(f"{BASE_URL}/trackings", headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("trackings", [])

def key_for_tracking(t):
    tag = t.get("tag") or "UNKNOWN"
    return f"{tag}/{t.get('slug','')}/{t.get('tracking_number','')}"


def should_skip(t, handled_state, now):
    k = key_for_tracking(t)
    last = handled_state.get(k)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False
    return (now - last_dt) < timedelta(days=DEDUP_DAYS)

def mark_handled(trackings, handled_state, now):
    for t in trackings:
        handled_state[key_for_tracking(t)] = now.isoformat()

def normalize(trackings):
    rows = []
    for t in trackings:
        last_cp = t.get("last_checkpoint") or {}
        rows.append({
            "tracking_number": t.get("tracking_number"),
            "carrier_slug": t.get("slug"),
            "status_tag": t.get("tag"),
            "title": t.get("title"),
            "order_id": t.get("order_id"),
            "last_checkpoint_time": last_cp.get("checkpoint_time"),
            "last_checkpoint_location": last_cp.get("location"),
            "updated_at": t.get("updated_at"),
        })
    return rows

def write_json(rows, path):
    payload = {
        "generated_at": utcnow().isoformat(),
        "count": len(rows),
        "items": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def write_xlsx(rows, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "InTransit"

    if not rows:
        ws.append(["No new InTransit trackings (deduped for 30 days)."])
        wb.save(path)
        return

    headers = list(rows[0].keys())
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    wb.save(path)

def main():
    now = utcnow()
    handled = load_state()

    trackings = get_intransit_trackings(limit=200)
    new_trackings = [t for t in trackings if not should_skip(t, handled, now)]

    rows = normalize(new_trackings)

    os.makedirs("output", exist_ok=True)
    write_json(rows, "output/returns_intransit.json")
    write_xlsx(rows, "output/returns_intransit.xlsx")

    mark_handled(new_trackings, handled, now)
    save_state(handled)

if __name__ == "__main__":
    main()
