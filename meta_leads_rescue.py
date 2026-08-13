"""Mirror every Meta instant-form lead into the house's own database.

Meta deletes instant-form submissions 90 days after they are submitted, and
the ChurchFunnels Facebook integration that was supposed to ingest them has
been leaking. This job walks every Page the token can see, every lead form on
each Page, and every lead still alive on each form, and upserts them into
meta_leads in Supabase. Run once it is a rescue; on its daily schedule it is
the permanent backstop pipe: even if ChurchFunnels' integration breaks again,
every hand raised on a form lands in the house's database within a day.

It also prints the monthly lead counts, which is the Meta half of the leak
measurement (compare against contacts created in ChurchFunnels in the same
window).

**No lead content is ever printed or uploaded.** Names, emails and phone
numbers go to Supabase and nowhere else; the Action log gets counts only.
Never add a print of lead fields and never upload the table as a workflow
artifact: Action logs and artifacts are visible to anyone who can see the
repo.

Env vars:
  META_ACCESS_TOKEN      the System User token. Beyond ads_read, lead
                         retrieval needs the token generated with:
                         leads_retrieval, pages_show_list,
                         pages_read_engagement, pages_manage_ads.
                         The system user also needs the church's Facebook
                         PAGE assigned as an asset (Business settings >
                         Users > System users > Assign assets > Pages).
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database (the
                         NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_KEY
                         spellings also work)
Optional:
  DRY_RUN                "1" to fetch and count, but write nothing

Until the token and Page assignment are in place the job prints setup
instructions and exits cleanly, so the daily schedule is safe to merge now.
"""
import os
import sys
from datetime import datetime, timezone

import gc3_env
from meta_api import connected, meta_get_all

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")

SUPABASE_URL = gc3_env.supabase_url()
SERVICE_KEY = gc3_env.service_key()

try:
    from supabase import create_client
except ImportError:
    print("ERROR: 'supabase' not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SERVICE_KEY)

LEAD_FIELDS = ",".join([
    "id", "created_time", "field_data", "is_organic",
    "ad_id", "ad_name", "adset_id", "adset_name",
    "campaign_id", "campaign_name",
])


def parse_fields(field_data):
    """Best-effort name, email and phone from a form's field_data. Field names
    vary per form; the raw jsonb stays in the row as the source of truth."""
    by_name = {}
    for f in (field_data or []):
        vals = f.get("values") or []
        if f.get("name") and vals:
            by_name[f["name"].lower()] = vals[0]
    full_name = by_name.get("full_name") or " ".join(
        x for x in (by_name.get("first_name"), by_name.get("last_name")) if x) or None
    email = by_name.get("email") or None
    phone = by_name.get("phone_number") or by_name.get("phone") or None
    return full_name, email, phone


def upsert(rows):
    if DRY_RUN:
        print(f"  DRY RUN: would store {len(rows)} lead(s); nothing written.")
        return
    for start in range(0, len(rows), 500):
        sb.table("meta_leads").upsert(
            rows[start:start + 500], on_conflict="leadgen_id").execute()


def known_lead_ids():
    """Every leadgen_id already mirrored, so a run can tell new from seen.
    The mirror runs every fifteen minutes now, and speed to first touch only
    matters for the leads that were not there fifteen minutes ago."""
    ids, start = set(), 0
    while True:
        batch = (sb.table("meta_leads").select("leadgen_id")
                 .range(start, start + 999).execute().data or [])
        ids.update(r["leadgen_id"] for r in batch)
        if len(batch) < 1000:
            return ids
        start += 1000


def main():
    now = datetime.now(timezone.utc)
    print(f"Meta lead mirror starting ({'DRY RUN' if DRY_RUN else 'live'}), {now:%Y-%m-%d %H:%M} UTC")
    if not connected():
        print("Not connected: add the META_ACCESS_TOKEN secret (see the README) and rerun.")
        return

    known = set() if DRY_RUN else known_lead_ids()
    fresh = 0

    pages = meta_get_all("me/accounts", {"fields": "id,name,access_token", "limit": 100},
                         fatal=False)
    if not pages:
        print("No Pages visible to this token. To activate the lead mirror:")
        print("  1. Assign the church's Facebook Page to the gc3-reporting system user")
        print("     (Business settings > Users > System users > Assign assets > Pages).")
        print("     If the Page lives in the church's own portfolio, partner-share it")
        print("     first, the same way the ad account was shared.")
        print("  2. Regenerate the token with leads_retrieval, pages_show_list,")
        print("     pages_read_engagement and pages_manage_ads (keep ads_read), and")
        print("     update the META_ACCESS_TOKEN secret.")
        print("Until then this job does nothing, so the daily schedule is safe.")
        return

    total, by_month, by_form = 0, {}, []
    for page in pages:
        ptoken = page.get("access_token")
        forms = meta_get_all(
            f"{page['id']}/leadgen_forms",
            {"fields": "id,name,status", "limit": 100, "access_token": ptoken},
            fatal=False)
        if forms is None:
            print(f"  NOTE: cannot list forms on Page '{page.get('name')}'. The token")
            print("  likely lacks pages_manage_ads; regenerate it with the permissions")
            print("  in the README and update the secret.")
            continue
        for form in forms:
            leads = meta_get_all(
                f"{form['id']}/leads",
                {"fields": LEAD_FIELDS, "limit": 100, "access_token": ptoken},
                fatal=False)
            if leads is None:
                print(f"  NOTE: cannot read leads on form '{form.get('name')}'. The token")
                print("  likely lacks leads_retrieval; regenerate it with the permissions")
                print("  in the README. If only this form fails, check Leads Access")
                print("  Manager on the Page (it can restrict lead access per app).")
                continue
            rows = []
            for lead in leads:
                full_name, email, phone = parse_fields(lead.get("field_data"))
                rows.append({
                    "leadgen_id": lead["id"],
                    "page_id": page.get("id"),
                    "page_name": page.get("name"),
                    "form_id": form.get("id"),
                    "form_name": form.get("name"),
                    "created_time": lead.get("created_time"),
                    "is_organic": bool(lead.get("is_organic")),
                    "ad_id": lead.get("ad_id"),
                    "ad_name": lead.get("ad_name"),
                    "adset_id": lead.get("adset_id"),
                    "adset_name": lead.get("adset_name"),
                    "campaign_id": lead.get("campaign_id"),
                    "campaign_name": lead.get("campaign_name"),
                    "full_name": full_name,
                    "email": email,
                    "phone": phone,
                    "field_data": lead.get("field_data") or [],
                })
                month = (lead.get("created_time") or "")[:7]
                if month:
                    by_month[month] = by_month.get(month, 0) + 1
            try:
                upsert(rows)
            except Exception as e:
                print(f"ERROR: could not write to meta_leads ({e}).")
                print("Has supabase/meta_leads_schema.sql been applied to the project?")
                sys.exit(1)
            total += len(rows)
            fresh += sum(1 for r in rows if r["leadgen_id"] not in known)
            # Counts only. Never print lead fields: logs are not a safe place
            # for names, emails or phone numbers.
            by_form.append((form.get("name") or form.get("id"), form.get("status"), len(rows)))

    print()
    print("Forms found (leads still alive on Meta; the 90-day window applies):")
    for name, status, n in by_form:
        print(f"  {name} ({status}): {n} lead(s)")
    if by_month:
        print("Leads by month:")
        for month in sorted(by_month):
            print(f"  {month}: {by_month[month]}")
    print()
    print(f"Done. {total} lead(s) {'counted' if DRY_RUN else 'mirrored into meta_leads'}.")
    if not DRY_RUN:
        print(f"New this run: {fresh}.")
        if fresh:
            # The workflow sees this file and runs the resolver immediately,
            # so a hand raised on Facebook is a card on the Board within the
            # quarter hour, not tomorrow.
            with open(".new_leads", "w", encoding="utf-8") as f:
                f.write(str(fresh))
    print("Compare the recent months against contacts created in ChurchFunnels in the")
    print("same window: the difference is the leak, measured.")


if __name__ == "__main__":
    main()
