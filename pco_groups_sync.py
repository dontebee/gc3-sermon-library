"""Mirror Planning Center Groups into pco_groups and pco_group_memberships.

Charisma, life groups, every circle the house runs. PD's Discipleship rules
read from here: being in any group is formation (D9), leading one is D2,
and Charisma is D1 by name. The resolver reads this mirror and never
queries PCO directly.

Full walk every run: the group list is small and a request per group for
memberships is well inside PCO's limits. Stale memberships are cleared by
delete-then-insert per group, so someone who leaves a group actually
leaves the mirror.

**Counts and group names only in the log.** Person ids go to the database
and nowhere else.

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
        if r.status_code in (401, 403):
            print(f"ERROR: PCO returned {r.status_code} for Groups. The personal access")
            print("token may not have the Groups product. Open the token's settings in")
            print("Planning Center and grant Groups, then rerun.")
            sys.exit(1)
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def walk(path, params=None):
    """Every page of a PCO collection."""
    out, offset = [], 0
    while True:
        p = dict(params or {})
        p.update({"per_page": 100, "offset": offset})
        data = pco_get(path, p)
        items = data.get("data", [])
        out.extend(items)
        if not data.get("links", {}).get("next"):
            return out
        offset += 100


def main():
    print(f"PCO Groups sync starting ({'DRY RUN' if DRY_RUN else 'live'}).")
    if not (PCO_APP_ID and PCO_SECRET):
        print("ERROR: PCO_APP_ID / PCO_SECRET not set.")
        sys.exit(1)

    groups = walk("/groups/v2/groups", {"include": "group_type"})
    print(f"Groups: {len(groups)} found.")

    total_members, rows_groups = 0, []
    for g in groups:
        a = g.get("attributes", {})
        gt = (((g.get("relationships") or {}).get("group_type") or {}).get("data") or {})
        archived = bool(a.get("archived_at"))
        rows_groups.append({
            "group_id": g["id"],
            "name": a.get("name"),
            "group_type": gt.get("id"),
            "archived": archived,
            "memberships_count": a.get("memberships_count"),
        })

        if archived:
            continue
        memberships = walk(f"/groups/v2/groups/{g['id']}/memberships")
        m_rows = []
        for m in memberships:
            ma = m.get("attributes", {})
            pid = (((m.get("relationships") or {}).get("person") or {}).get("data") or {}).get("id")
            m_rows.append({
                "membership_id": m["id"],
                "group_id": g["id"],
                "group_name": a.get("name"),
                "pco_person_id": pid or ma.get("account_center_identifier"),
                "role": (ma.get("role") or "").lower() or None,
                "joined_at": ma.get("joined_at"),
            })
        total_members += len(m_rows)
        leaders = sum(1 for m in m_rows if m["role"] == "leader")
        print(f"  {a.get('name')}: {len(m_rows)} member(s), {leaders} leader(s)")
        if not DRY_RUN:
            # Delete-then-insert per group: leaving a group leaves the mirror.
            sb.table("pco_group_memberships").delete().eq("group_id", g["id"]).execute()
            for start in range(0, len(m_rows), 500):
                sb.table("pco_group_memberships").insert(m_rows[start:start + 500]).execute()

    if not DRY_RUN and rows_groups:
        sb.table("pco_groups").upsert(rows_groups, on_conflict="group_id").execute()

    print()
    print(f"Done. {len(groups)} group(s), {total_members} membership(s) "
          f"{'counted' if DRY_RUN else 'mirrored'}.")


if __name__ == "__main__":
    main()
