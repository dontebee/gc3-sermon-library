"""Mirror the Planning Center People roster into pco_people.

This is the sync that takes Pursuit from hundreds to thousands. PD's floor
rule says a Planning Center record at all puts a person in Fellowship, and
the resolver cannot apply that rule to a roster it cannot see.

What comes over, per person: names, primary email and phone, membership as
PCO spells it, PCO's own active/inactive flag, the child flag, the avatar
URL, and the first household id (the kids roll-up will want it). One row
per PCO person, upserted, so re-runs are harmless.

A full walk every run, on purpose. The roster is a few thousand rows, which
is a few dozen pages; incremental sync would save seconds and add a way to
miss an edit. pco_get already survives PCO's rate limiter.

**Counts only in the log.** Names, emails and phone numbers belong in the
database and nowhere else: Action logs are visible to anyone who can read
the repo.

Env vars:
  PCO_APP_ID, PCO_SECRET                    Planning Center personal access token
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database (the
      NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_KEY spellings also work)
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
    """GET from Planning Center with retry. PCO rate-limits aggressively
    (HTTP 429 with a Retry-After header); a full roster walk will meet it."""
    for attempt in range(5):
        r = requests.get(PCO_BASE + path, params=params or {},
                         auth=(PCO_APP_ID, PCO_SECRET), timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After") or 2 ** attempt)
            print(f"  PCO {r.status_code} on {path}, retrying in {wait}s...")
            time.sleep(min(wait, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def pick_contact(person, included, rel_name, attr_name):
    """The primary email address or phone number, else the first on file.

    PCO hands contacts back as included resources; the person only carries
    ids. Walk the person's relationship list against the included map and
    prefer the one PCO marks primary.
    """
    rel = (((person.get("relationships") or {}).get(rel_name) or {}).get("data")) or []
    found = None
    for r in rel:
        item = included.get((r.get("type"), r.get("id")))
        if not item:
            continue
        a = item.get("attributes", {})
        if a.get("primary"):
            return a.get(attr_name)
        if found is None:
            found = a.get(attr_name)
    return found


def main():
    print(f"PCO People sync starting ({'DRY RUN' if DRY_RUN else 'live'}).")
    if not (PCO_APP_ID and PCO_SECRET):
        print("ERROR: PCO_APP_ID / PCO_SECRET not set.")
        sys.exit(1)

    offset, pages, total, children, with_avatar, with_email = 0, 0, 0, 0, 0, 0
    memberships = {}

    while True:
        data = pco_get("/people/v2/people", {
            "per_page": 100, "offset": offset,
            "include": "emails,phone_numbers,households",
            "order": "created_at",
        })
        items = data.get("data", [])
        if not items:
            break
        included = {(i.get("type"), i.get("id")): i for i in data.get("included", [])}

        batch = []
        for p in items:
            a = p.get("attributes", {})
            email = pick_contact(p, included, "emails", "address")
            phone = pick_contact(p, included, "phone_numbers", "number")
            households = (((p.get("relationships") or {}).get("households") or {}).get("data")) or []
            is_child = bool(a.get("child"))
            membership = (a.get("membership") or "").strip() or None

            total += 1
            children += 1 if is_child else 0
            with_avatar += 1 if a.get("avatar") else 0
            with_email += 1 if email else 0
            if membership:
                memberships[membership] = memberships.get(membership, 0) + 1

            batch.append({
                "pco_person_id": p["id"],
                "first_name": a.get("first_name"),
                "last_name": a.get("last_name"),
                "name": a.get("name"),
                "email": email,
                "phone": phone,
                "membership": membership,
                "pco_status": a.get("status"),
                "child": is_child,
                "avatar_url": a.get("avatar"),
                "household_id": households[0]["id"] if households else None,
                "pco_created_at": a.get("created_at"),
                "pco_updated_at": a.get("updated_at"),
            })

        if batch and not DRY_RUN:
            sb.table("pco_people").upsert(batch, on_conflict="pco_person_id").execute()

        pages += 1
        if pages % 10 == 0:
            print(f"  ...{total} people through page {pages}")
        offset += 100
        if not data.get("links", {}).get("next"):
            break

    print()
    print(f"Roster: {total} people across {pages} page(s).")
    print(f"  adults: {total - children}, children: {children}")
    print(f"  with email: {with_email}, with photo: {with_avatar}")
    print("  membership spellings (the resolver matches these case-insensitively):")
    for m, n in sorted(memberships.items(), key=lambda x: -x[1]):
        print(f"    {m}: {n}")

    if DRY_RUN:
        print()
        print("DRY RUN: nothing written.")
        return
    print()
    print("Done. The roster is mirrored; the resolver reads it next run.")


if __name__ == "__main__":
    main()
