#!/usr/bin/env python3
"""
fetch_mandi.py — daily mandi price ingestion for nashik-mandi-watch.

Every field name, date format, filter rule and market-string rule in this file
traces to docs/api-contract.md (Loop 0, verified live 2026-08-07).

Pulls:
  1. All commodities, district=Nashik   (card + movers)
  2. Onion, all Maharashtra markets     (district comparison)

Writes:
  data/raw/YYYY-MM-DD.json   raw combined pull (run date, IST)
  data/history.csv           normalized rows, deduped, last-write-wins

Exit codes:
  0 ok | 1 zero Nashik records / hard API failure (fail loudly, per spec)

Offline self-test (no network):
  python fetch_mandi.py --from-file data/raw/fixtures/*.json
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ---- constants traced to docs/api-contract.md ------------------------------
RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
BASE = f"https://api.data.gov.in/resource/{RESOURCE}"
SAMPLE_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"  # 10-rec cap
API_KEY = os.environ.get("DATA_GOV_IN_KEY", "")
# data.gov.in returns HTTP 400 to non-browser user agents (contract: access-path
# constraints; same workaround as nashik-air-watch).
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; nashik-mandi-watch)"}

STATE = "Maharashtra"
DISTRICT = "Nashik"          # district field; city market is spelled "Nasik APMC"
ONION = "Onion"              # exact commodity string, verified
DATE_FMT = "%d/%m/%Y"        # arrival_date is DD/MM/YYYY, verified
FIELDS = ["state", "district", "market", "commodity", "variety", "grade",
          "arrival_date", "min_price", "max_price", "modal_price"]
DEDUPE_KEY = ["market", "commodity", "variety", "grade", "arrival_date"]

IST = timezone(timedelta(hours=5, minutes=30))
RAW_DIR = os.path.join("data", "raw")
HISTORY = os.path.join("data", "history.csv")
HISTORY_COLS = ["arrival_date", "state", "district", "market", "commodity",
                "variety", "grade", "min_price", "max_price", "modal_price",
                "fetched_at"]

# ---- HTTP layer -------------------------------------------------------------

def get_json(params, attempt_backoffs=(5, 15, 45)):
    """One API call, 3 retries with backoff. Returns parsed JSON or None."""
    qs = {"api-key": API_KEY or SAMPLE_KEY, "format": "json", **params}
    for i, backoff in enumerate((*attempt_backoffs, None)):
        try:
            r = requests.get(BASE, params=qs, headers=HEADERS, timeout=120)
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code}: {r.text[:200]}")
        except (requests.RequestException, ValueError) as e:
            print(f"  request error: {e}")
        if backoff is None:
            return None
        print(f"  retry {i + 1} in {backoff}s")
        time.sleep(backoff)
    return None


def fetch_all(filters, label):
    """
    Paginate through every record matching `filters`.
    Contract rules honored:
      - advance offset by observed count (sample key clamps limit to 10)
      - the index mutates intraday: re-read total after the sweep; if it grew,
        sweep once more (records are deduped later anyway)
      - never trust filters[market]; callers filter client-side
    """
    out, offset, page_limit = [], 0, 1000
    sweeps = 0
    while sweeps < 2:
        sweeps += 1
        total = None
        while True:
            data = get_json({"limit": page_limit, "offset": offset, **filters})
            if data is None or data.get("status") != "ok":
                print(f"FATAL: API failure during '{label}' at offset {offset}")
                return out, False
            recs = data.get("records", [])
            total = int(data.get("total", 0))
            out.extend(recs)
            got = len(recs)
            print(f"  [{label}] offset={offset} got={got} total={total}")
            if got == 0 or offset + got >= total:
                break
            offset += got
        # mutation check: one extra sweep if the index grew mid-pagination
        data = get_json({"limit": 1, "offset": 0, **filters})
        new_total = int(data.get("total", 0)) if data and data.get("status") == "ok" else total
        if new_total is not None and total is not None and new_total > total:
            print(f"  [{label}] index grew {total} -> {new_total} during sweep; re-sweeping")
            offset = 0
            continue
        break
    return out, True

# ---- normalization ----------------------------------------------------------

def parse_date(s):
    return datetime.strptime(s.strip(), DATE_FMT).date()


def normalize(records, fetched_at):
    """Validate + coerce raw records into history rows. Drops malformed rows loudly."""
    rows, dropped = [], 0
    for r in records:
        try:
            d = parse_date(r["arrival_date"])
            rows.append({
                "arrival_date": d.isoformat(),
                "state": r["state"].strip(),
                "district": r["district"].strip(),
                "market": r["market"].strip(),
                "commodity": r["commodity"].strip(),
                "variety": str(r.get("variety", "")).strip(),
                "grade": str(r.get("grade", "")).strip(),
                "min_price": float(r["min_price"]),
                "max_price": float(r["max_price"]),
                "modal_price": float(r["modal_price"]),
                "fetched_at": fetched_at,
            })
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            dropped += 1
            print(f"  dropped malformed record ({e}): {json.dumps(r)[:160]}")
    if dropped:
        print(f"  WARNING: dropped {dropped} malformed record(s)")
    return rows


def dedupe_key(row):
    return tuple(row[k] if k != "arrival_date" else row["arrival_date"] for k in
                 ["market", "commodity", "variety", "grade", "arrival_date"])


def merge_history(new_rows):
    """Append to history.csv, dedupe last-write-wins on the contract key."""
    existing = {}
    if os.path.exists(HISTORY):
        with open(HISTORY, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[dedupe_key(row)] = row
    before = len(existing)
    updated = 0
    for row in new_rows:
        k = dedupe_key(row)
        if k in existing:
            updated += 1
        existing[k] = {c: str(row[c]) for c in HISTORY_COLS}
    rows = sorted(existing.values(), key=lambda r: (r["arrival_date"], r["market"], r["commodity"]))
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_COLS)
        w.writeheader()
        w.writerows(rows)
    return before, len(rows), updated

# ---- diagnostics -------------------------------------------------------------

def dedupe_rows(rows):
    """Last-write-wins dedupe on the contract key, preserving order of last sight."""
    seen = {}
    for r in rows:
        seen[dedupe_key(r)] = r
    return list(seen.values())


def report(nashik_rows, onion_mh_rows):
    dates = sorted({r["arrival_date"] for r in nashik_rows})
    markets = sorted({r["market"] for r in nashik_rows})
    lasalgaon = [m for m in markets if m.startswith("Lasalgaon")]
    onion_nashik = [r for r in nashik_rows if r["commodity"] == ONION]
    print("\n=== FETCH REPORT ===")
    print(f"Nashik rows: {len(nashik_rows)}  (dates: {', '.join(dates) or 'NONE'})")
    print(f"Maharashtra onion rows: {len(onion_mh_rows)}")
    print(f"Distinct Nashik markets ({len(markets)}):")
    for m in markets:
        print(f"  - {m}")
    print(f"Lasalgaon yards seen: {lasalgaon or 'NONE'}")
    print(f"Nashik onion rows: {len(onion_nashik)}")
    for r in sorted(onion_nashik, key=lambda x: x["market"])[:12]:
        print(f"  {r['arrival_date']} {r['market']}: {r['variety']}/{r['grade']} "
              f"min {r['min_price']:.0f} / modal {r['modal_price']:.0f} / max {r['max_price']:.0f}")

# ---- backfill probe (contract open item #3) ----------------------------------

def probe_backfill():
    """arrival_date is not in field_exposed; prove whether filtering by it works."""
    yesterday = (datetime.now(IST) - timedelta(days=1)).strftime(DATE_FMT)
    print(f"\n=== BACKFILL PROBE: filters[arrival_date]={yesterday} ===")
    data = get_json({"limit": 10, "offset": 0,
                     "filters[state.keyword]": STATE,
                     "filters[district]": DISTRICT,
                     "filters[arrival_date]": yesterday})
    if not data or data.get("status") != "ok":
        print("probe failed (API error) — backfill feasibility unresolved")
        return
    recs = data.get("records", [])
    got_dates = sorted({r.get("arrival_date") for r in recs})
    print(f"total={data.get('total')} sample dates returned: {got_dates}")
    if recs and all(d == yesterday for d in got_dates):
        print("VERDICT: arrival_date filter honored -> historical backfill MAY be possible")
    else:
        print("VERDICT: arrival_date filter NOT honored -> resource is current-day only; "
              "history builds forward from today (update docs/api-contract.md item #3)")

# ---- main ---------------------------------------------------------------------

def run_live(args):
    key_kind = "REAL (DATA_GOV_IN_KEY)" if API_KEY else "SAMPLE (10-record cap!)"
    print(f"API key in use: {key_kind}")
    now = datetime.now(IST)
    fetched_at = now.isoformat(timespec="seconds")

    nashik_raw, ok1 = fetch_all(
        {"filters[state.keyword]": STATE, "filters[district]": DISTRICT}, "nashik-all")
    onion_raw, ok2 = fetch_all(
        {"filters[state.keyword]": STATE, "filters[commodity]": ONION}, "mh-onion")
    if not (ok1 and ok2):
        sys.exit(1)

    # contract: server-side filters beyond district/state are not trusted -> re-filter
    nashik_raw = [r for r in nashik_raw if r.get("district") == DISTRICT]
    onion_raw = [r for r in onion_raw
                 if r.get("commodity") == ONION and r.get("state") == STATE]

    if not nashik_raw:
        print("FATAL: zero Nashik records returned — failing loudly so the Action surfaces it.")
        sys.exit(1)

    os.makedirs(RAW_DIR, exist_ok=True)
    raw_path = os.path.join(RAW_DIR, now.strftime("%Y-%m-%d") + ".json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": fetched_at,
                   "nashik_all": nashik_raw,
                   "maharashtra_onion": onion_raw}, f, ensure_ascii=False, indent=1)
    print(f"raw saved: {raw_path} ({len(nashik_raw)} + {len(onion_raw)} records)")

    rows = normalize(nashik_raw + onion_raw, fetched_at)
    before, after, updated = merge_history(rows)
    print(f"history.csv: {before} -> {after} rows ({updated} updated in place)")

    deduped = dedupe_rows(rows)
    nashik_rows = [r for r in deduped if r["district"] == DISTRICT]
    onion_mh_rows = [r for r in deduped if r["commodity"] == ONION]
    report(nashik_rows, onion_mh_rows)

    if args.probe_backfill:
        probe_backfill()


def run_offline(paths):
    print(f"OFFLINE self-test on {len(paths)} fixture file(s) — no network")
    fetched_at = datetime.now(IST).isoformat(timespec="seconds")
    raw = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        recs = data.get("records", data.get("nashik_all", []))
        if "maharashtra_onion" in data:
            recs = data["nashik_all"] + data["maharashtra_onion"]
        print(f"  {p}: {len(recs)} records")
        raw.extend(recs)
    rows = normalize(raw, fetched_at)
    before, after, updated = merge_history(rows)
    print(f"history.csv: {before} -> {after} rows ({updated} updated in place)")
    deduped = dedupe_rows(rows)
    nashik_rows = [r for r in deduped if r["district"] == DISTRICT]
    onion_rows = [r for r in deduped if r["commodity"] == ONION]
    report(nashik_rows, onion_rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file", nargs="+", metavar="JSON",
                    help="offline mode: run the pipeline on saved API responses")
    ap.add_argument("--probe-backfill", action="store_true",
                    help="test whether filters[arrival_date] is honored (contract item #3)")
    a = ap.parse_args()
    if a.from_file:
        run_offline(a.from_file)
    else:
        run_live(a)
