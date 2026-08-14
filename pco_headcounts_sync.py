"""Mirror Planning Center Headcounts into pco_headcounts.

The room counts: how many people were IN the building (or watching), per
service time, per attendance type. This is the attendance series PD reads
on Planning Center's own dashboard, and mirroring it lets the Pulse draw
it next to everything else the house knows.

Headcounts are aggregates. No person ids, no names: the smallest, safest
attendance data Planning Center has. The person-level Check-Ins mirror
(who was here, for the state clock) is a separate, bigger job.

**Counts only in the log.** There is nothing else here to leak, which is
the point.

Env vars:
  PCO_APP_ID, PCO_SECRET                    Planning Center personal access token
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database
Optional:
  DRY_RUN   "1" to read and report, writing nothing
"""
import os
import sys
import time

import requests

import gc3_env

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")

PCO_APP_ID = (os.environ.get("PCO_APP_ID") or "").strip()
PCO_SECRET = (os.environ.get("PCO_SECRET") or "").strip()
PCO_BASE = "https://api.planningcenteronline.com"

SUPABASE_URL = gc3_env.supabase_url()
SERVICE_KEY = gc3_env.service_key()

try:
    from supabase import create_client
except ImportError:
    print("ERROR: 'supabase' not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SERVICE_KEY)


def pco_get(path, params=None):
    for attempt in range(5):
        r = requests.get(PCO_BASE + path, params=params or {},
                         auth=(PCO_APP_ID, PCO_SECRET), timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After") or 2 ** attempt)
            print(f"  PCO {r.status_code} on {path}, retrying in {wait}s...")
            time.sleep(min(wait, 30))
            continue
        if r.status_code in (401, 403, 404):
            print(f"ERROR: PCO returned {r.status_code} for Check-Ins headcounts. The")
            print("personal access token may not include the Check-Ins product. Open")
            print("the token's settings in Planning Center, grant Check-Ins, and rerun.")
            sys.exit(1)
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def walk_with_included(path, params=None):
    """Every page of a PCO collection, keeping the included resources too."""
    data, included, offset = [], [], 0
    while True:
        p = dict(params or {})
        p.update({"per_page": 100, "offset": offset})
        page = pco_get(path, p)
        data.extend(page.get("data", []))
        included.extend(page.get("included", []))
        if not page.get("links", {}).get("next"):
            return data, included
        offset += 100


def main():
    print(f"PCO Headcounts sync starting ({'DRY RUN' if DRY_RUN else 'live'}).")
    if not (PCO_APP_ID and PCO_SECRET):
        print("ERROR: PCO_APP_ID / PCO_SECRET not set.")
        sys.exit(1)

    # Headcounts is a vertex of the Check-Ins product, not its own API:
    # the Headcounts app writes into Check-Ins event times.
    counts, included = walk_with_included(
        "/check-ins/v2/headcounts", {"include": "event_time,attendance_type"})

    # The included pile carries the names and the clock for every count.
    type_name = {i["id"]: (i.get("attributes", {}).get("name") or "").strip()
                 for i in included if i.get("type") == "AttendanceType"}
    time_starts = {i["id"]: i.get("attributes", {}).get("starts_at")
                   for i in included if i.get("type") == "EventTime"}

    rows = []
    for c in counts:
        rel = c.get("relationships") or {}
        at = ((rel.get("attendance_type") or {}).get("data") or {}).get("id")
        et = ((rel.get("event_time") or {}).get("data") or {}).get("id")
        rows.append({
            "headcount_id": c["id"],
            "total": c.get("attributes", {}).get("total"),
            "attendance_type_id": at,
            "attendance_type": type_name.get(at),
            "event_time_id": et,
            "starts_at": time_starts.get(et),
        })

    dated = sum(1 for r in rows if r["starts_at"])
    types = sorted({r["attendance_type"] for r in rows if r["attendance_type"]})
    print(f"  headcounts: {len(rows)} count(s), {dated} with a service time,")
    print(f"  attendance types: {', '.join(types) if types else '(none)'}")

    if DRY_RUN:
        print()
        print("DRY RUN: nothing written.")
        return

    for start in range(0, len(rows), 500):
        sb.table("pco_headcounts").upsert(
            rows[start:start + 500], on_conflict="headcount_id").execute()
    print()
    print(f"Done. {len(rows)} headcount(s) mirrored.")


if __name__ == "__main__":
    main()
