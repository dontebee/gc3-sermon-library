"""Daily engagement job: giving sync, Growth Track reporting, Monday digest.

**This job does not email members.** It emails DIGEST_TO and nobody else.
Every member-facing note — the first-gift welcome, the monthly-partner
invitation, GrowthTrack milestones — is a Pathway in gc3-intranet, where the
on/off switch, the shared suppression list, unsubscribe links, editable rules
and the admin page live. See CLAUDE.md for why that rule exists.

One run does three things:

1. Giving sync. Pulls donations from Planning Center Giving into giving_gifts,
   then backfills each donor's name and email from Planning Center People.
   Giving hands back a person id but never a name or an address, and the
   Pathways engine enrols first_gift and monthly_partner straight off this
   table — so those two columns are the whole point, not decoration.

2. Growth Track reporting. Reads gt_progress to work out who reached a
   milestone, who is active, and who has gone quiet. Reporting only; the
   congratulation is the growth_track_celebrations Pathway.

3. Monday digest. One email to the Lead Pastor: Growth Track movement,
   intranet activity, giving totals, first-time givers, new monthly partners,
   last week's Meta ads numbers and recommendations (written to Supabase by
   meta_ads_report.py, read here so the digest needs no Meta credentials),
   and the personal touches that should not be automated — a text from the
   pastor, a handwritten note.

Env vars:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database (required; the
      NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_KEY spellings also work)
  RESEND_API_KEY                       sending (absent = report-only dry run)
  PCO_APP_ID, PCO_SECRET               Planning Center personal access token
                                       (absent = giving section skipped)
Optional:
  DIGEST_TO     where the digest goes, and the only address this job will
                send to (default dontebee@gmail.com)
  NUDGE_FROM    From header on the digest
  REPLY_TO      Reply-To on the digest
  DRY_RUN       "1" to print instead of send
  MAX_EMAILS    cap on sends per run (default 30)
"""
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests

import gc3_env

CT = ZoneInfo("America/Chicago")
NOW = datetime.now(timezone.utc)
WEEK_AGO = NOW - timedelta(days=7)
CELEBRATE_WINDOW_DAYS = 10   # only celebrate milestones reached this recently
FIRST_GIFT_WINDOW_DAYS = 14  # a "first gift" counts as new for this long
STALLED_AFTER_DAYS = 14


SUPABASE_URL = gc3_env.supabase_url()
SERVICE_KEY = gc3_env.service_key()

RESEND_API_KEY = (os.environ.get("RESEND_API_KEY") or "").strip()
PCO_APP_ID = (os.environ.get("PCO_APP_ID") or "").strip()
PCO_SECRET = (os.environ.get("PCO_SECRET") or "").strip()
DIGEST_TO = (os.environ.get("DIGEST_TO") or "dontebee@gmail.com").strip()
# The name stays personal because PD signs these; the address is the house
# inbox so a reply reaches someone who can answer it the same day.
NUDGE_FROM = (os.environ.get("NUDGE_FROM") or "Pastor Donte <hello@godchasers.church>").strip()
REPLY_TO = (os.environ.get("REPLY_TO") or "hello@godchasers.church").strip()
DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")
MAX_EMAILS = int(os.environ.get("MAX_EMAILS", "30"))

if not RESEND_API_KEY and not DRY_RUN:
    print("NOTE: no RESEND_API_KEY secret; running as a dry run (nothing is sent).")
    DRY_RUN = True

try:
    from supabase import create_client
except ImportError:
    print("ERROR: 'supabase' not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SERVICE_KEY)

emails_sent = []   # (kind, to) tuples, for the digest and the cap
send_failures = []


# ---------------------------------------------------------------- helpers

def fetch_all(table, select="*", order=None):
    """Read a whole table through PostgREST, 1000 rows at a time."""
    rows, start = [], 0
    while True:
        q = sb.table(table).select(select)
        if order:
            q = q.order(order)
        batch = q.range(start, start + 999).execute().data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


_auth_emails_cache = None


def auth_emails():
    """Map auth user id -> email via the GoTrue admin API. Cached per run
    because both the growth track and giving sections need it."""
    global _auth_emails_cache
    if _auth_emails_cache is not None:
        return _auth_emails_cache
    out = {}
    page = 1
    while True:
        try:
            res = sb.auth.admin.list_users(page=page, per_page=200)
        except Exception as e:
            print(f"WARNING: could not list auth users ({e}); falling back to profiles.email")
            break
        users = getattr(res, "users", res) or []
        for u in users:
            uid = getattr(u, "id", None)
            em = getattr(u, "email", None)
            if uid and em:
                out[str(uid)] = em
        if len(users) < 200:
            break
        page += 1
    for p in fetch_all("profiles", "id,email"):
        if p.get("email"):
            out.setdefault(str(p["id"]), p["email"])
    _auth_emails_cache = out
    return out


def _int_env(name, default):
    """An integer from the environment, tolerating unset, empty and rubbish.

    GitHub passes an unfilled workflow_dispatch input through as an empty
    string rather than omitting it, so os.environ.get(name, default) hands
    back "" and int() raises. Fall back rather than fail the run over an
    input someone left blank on purpose.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        print(f"NOTE: {name}={raw!r} is not a number; using {default}.")
        return default


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def send_email(to, subject, html_body, kind, capped=True, unsub=None):
    """Send through Resend, honouring DRY_RUN and the per-run cap.

    There is exactly one caller: the Monday digest, addressed to DIGEST_TO.
    Nothing in this repo emails a member — that is the Pathways engine's job,
    where the switch, the shared suppression list and unsubscribe live.

    If you are about to add a second caller, read CLAUDE.md first. A second
    sender in this repo is what put 30 monthly-partner invitations in front of
    people on 2026-08-05 while every Pathway was switched off.
    """
    if to != DIGEST_TO:
        # Belt and braces. The rule above is a paragraph; this is a guard.
        print(f"  REFUSED: {kind} -> {to}. This repo only emails DIGEST_TO.")
        return False
    if capped and len(emails_sent) >= MAX_EMAILS:
        print(f"  SKIP (cap of {MAX_EMAILS} reached): {kind} -> {to}")
        return False
    if DRY_RUN:
        print(f"  DRY RUN {kind} -> {to}: {subject}")
        emails_sent.append((kind, to))
        return True
    payload = {"from": NUDGE_FROM, "to": [to], "reply_to": REPLY_TO,
               "subject": subject, "html": html_body}
    if unsub:
        # Gmail and Outlook surface this as a native Unsubscribe button, which
        # is far better for the domain than someone reaching for "spam".
        payload["headers"] = {
            "List-Unsubscribe": f"<{unsub}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json=payload,
        timeout=30,
    )
    if r.status_code in (200, 201):
        print(f"  SENT {kind} -> {to}: {subject}")
        emails_sent.append((kind, to))
        return True
    print(f"  FAILED {kind} -> {to}: HTTP {r.status_code} {r.text[:200]}")
    send_failures.append((kind, to, r.status_code))
    return False


# ---------------------------------------------------------------- growth track

def growth_track():
    """Celebrate fresh milestones and return facts for the digest."""
    print("Growth Track: reading progress...")
    lessons = [l for l in fetch_all("gt_lessons", "progress_key,submodule_id,is_published") if l.get("is_published")]
    submods = {s["id"]: s for s in fetch_all("gt_submodules", "id,module_id")}
    modules = {m["id"]: m for m in fetch_all("gt_modules", "id,title,phase_key,sort_order")}
    progress = fetch_all("gt_progress", "user_id,lesson_id,completed_at")
    gt_profiles = {p["id"]: p for p in fetch_all("gt_profiles", "id,display_name,first_name,last_name,email_optout,created_at")}
    email_log = fetch_all("gt_email_log", "user_id,kind")
    already = {(r["user_id"], r["kind"]) for r in email_log}
    emails = auth_emails()

    lesson_module = {}
    for l in lessons:
        sub = submods.get(l["submodule_id"])
        if sub and sub.get("module_id") in modules:
            lesson_module[l["progress_key"]] = sub["module_id"]
    module_lessons = {}
    for key, mid in lesson_module.items():
        module_lessons.setdefault(mid, set()).add(key)
    all_keys = set(lesson_module)

    per_user = {}
    for row in progress:
        ts = parse_ts(row.get("completed_at"))
        per_user.setdefault(row["user_id"], {})[row["lesson_id"]] = ts

    def display(uid):
        p = gt_profiles.get(uid, {})
        full = (p.get("display_name")
                or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
                or "Unknown member")
        first = p.get("first_name") or full.split(" ")[0]
        return full, first

    celebrate_cutoff = NOW - timedelta(days=CELEBRATE_WINDOW_DAYS)
    milestones, active, celebrated = [], [], []

    for uid, done in per_user.items():
        done_keys = set(done) & all_keys
        recent = [(k, t) for k, t in done.items() if t and t >= WEEK_AGO]
        if recent:
            active.append((uid, len(recent)))

        reached = []  # (kind, label, latest completion inside the milestone)
        for mid, keys in module_lessons.items():
            if keys and keys <= done_keys:
                latest = max((done.get(k) for k in keys if done.get(k)), default=None)
                phase = (modules[mid].get("phase_key") or modules[mid]["title"]).lower()
                reached.append((f"celebrate_{phase}", modules[mid]["title"], latest))
        if all_keys and all_keys <= done_keys:
            latest = max((done.get(k) for k in all_keys if done.get(k)), default=None)
            reached.append(("celebrate_course", "the whole Growth Track", latest))

        for kind, label, latest in reached:
            if (uid, kind) in already or not latest or latest < celebrate_cutoff:
                continue
            full, _first = display(uid)
            milestones.append((full, label))
            # Milestones are collected for the digest only. The congratulation
            # itself is the growth_track_celebrations / growth_track_complete
            # Pathway in gc3-intranet, which has the switch, the shared
            # suppression list and an unsubscribe. This repo does not email
            # members. See CLAUDE.md.

    stalled = []
    stall_cutoff = NOW - timedelta(days=STALLED_AFTER_DAYS)
    for uid, done in per_user.items():
        done_keys = set(done) & all_keys
        if all_keys and all_keys <= done_keys:
            continue  # finished, nothing to stall on
        latest = max((t for t in done.values() if t), default=None)
        if latest and latest < stall_cutoff:
            full, _ = display(uid)
            stalled.append((full, (NOW - latest).days))
    stalled.sort(key=lambda x: -x[1])

    new_members = []
    for uid, p in gt_profiles.items():
        ts = parse_ts(p.get("created_at"))
        if ts and ts >= WEEK_AGO:
            new_members.append(display(uid)[0])

    active_named = sorted(
        ((display(uid)[0], n) for uid, n in active), key=lambda x: -x[1])
    return {
        "new_members": new_members,
        "active": active_named,
        "milestones": milestones,
        "celebrated": celebrated,
        "stalled": stalled[:15],
        "total_learners": len(per_user),
    }


PCO_BASE = "https://api.planningcenteronline.com"


def pco_get(path, params=None):
    """GET from Planning Center with retry. PCO rate-limits aggressively
    (HTTP 429 with a Retry-After header), which a first-run backfill of years
    of donations will absolutely hit; without this the whole job would crash
    mid-sync."""
    import time
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


def sync_gifts():
    """Upsert PCO donations into giving_gifts. Full walk when empty, then a
    recent overlap walk (upsert makes overlap harmless)."""
    existing = fetch_all("giving_gifts", "pco_donation_id,pco_person_id,donor_email,donor_name")
    known = {g["pco_donation_id"] for g in existing}
    full_backfill = not existing
    print(f"Giving: syncing donations from Planning Center ({'full backfill' if full_backfill else 'recent window'})...")

    offset, added, stop = 0, 0, False
    while not stop:
        data = pco_get("/giving/v2/donations", {
            "per_page": 100, "offset": offset,
            "order": "received_at" if full_backfill else "-received_at",
            "include": "person",
        })
        items = data.get("data", [])
        people = {i["id"]: i for i in data.get("included", []) if i.get("type") == "Person"}
        if not items:
            break
        batch, all_known = [], True
        for d in items:
            a = d.get("attributes", {})
            # Skip refunded gifts and payments that have not actually cleared;
            # celebrating a declined card would be worse than sending nothing.
            if a.get("refunded") or (a.get("payment_status") or "succeeded") in ("pending", "failed"):
                continue
            pid = (((d.get("relationships") or {}).get("person") or {}).get("data") or {}).get("id")
            person = people.get(pid, {}).get("attributes", {}) if pid else {}
            name = " ".join(x for x in (person.get("first_name"), person.get("last_name")) if x) or None
            if d["id"] not in known:
                all_known = False
            batch.append({
                "pco_donation_id": d["id"],
                "pco_person_id": pid,
                "donor_name": name,
                "amount_cents": a.get("amount_cents") or 0,
                "received_at": a.get("received_at") or a.get("created_at"),
                "recurring": (a.get("payment_method") or "") == "recurring" or bool(a.get("recurring")),
            })
        if batch:
            sb.table("giving_gifts").upsert(batch, on_conflict="pco_donation_id").execute()
            added += sum(1 for b in batch if b["pco_donation_id"] not in known)
        # Incremental mode: once a whole page is already known, we are caught up.
        if not full_backfill and all_known:
            stop = True
        offset += 100
        if not data.get("links", {}).get("next"):
            break
    print(f"Giving: {added} new gift(s) recorded.")


def recurring_person_ids():
    ids, new_recurring, offset = set(), [], 0
    while True:
        data = pco_get("/giving/v2/recurring_donations", {"per_page": 100, "offset": offset, "include": "person"})
        people = {i["id"]: i for i in data.get("included", []) if i.get("type") == "Person"}
        items = data.get("data", [])
        for d in items:
            pid = (((d.get("relationships") or {}).get("person") or {}).get("data") or {}).get("id")
            if pid:
                ids.add(pid)
                created = parse_ts(d.get("attributes", {}).get("created_at"))
                if created and created >= WEEK_AGO:
                    person = people.get(pid, {}).get("attributes", {})
                    nm = " ".join(x for x in (person.get("first_name"), person.get("last_name")) if x)
                    new_recurring.append(nm or pid)
        if not data.get("links", {}).get("next"):
            return ids, new_recurring
        offset += 100


def donor_identity(pid, cache):
    """A donor's first name and email from PCO People, in ONE request.

    Planning Center Giving hands back a person id and nothing else — no name,
    no address — and the Pathways engine enrols first_gift and monthly_partner
    straight off giving_gifts. Those two columns are the whole reason this
    function exists; without them the pathways reach nobody and any letter
    that did go out would open "friend,".

    `include=emails` returns the person and their addresses together, so this
    costs one call per donor rather than two. With thousands of donors to
    backfill, halving the calls is the difference between finishing and
    spending the run inside PCO's rate limiter.

    Writes both columns back, so a donor is looked up once ever rather than
    once per run.
    """
    if pid in cache:
        return cache[pid]
    first, email, full = None, None, None
    try:
        data = pco_get(f"/people/v2/people/{pid}", {"include": "emails"})
        attrs = (data.get("data") or {}).get("attributes", {})
        # nickname first: it is what the person actually answers to.
        first = (attrs.get("nickname") or attrs.get("first_name") or "").strip() or None
        full = " ".join(x for x in (attrs.get("first_name"), attrs.get("last_name")) if x) or None
        rows = [i for i in data.get("included", []) if i.get("type") == "Email"]
        primary = [r for r in rows if r.get("attributes", {}).get("primary")]
        pick = primary or rows
        if pick:
            email = pick[0]["attributes"].get("address")
    except Exception as e:
        print(f"  WARNING: identity lookup failed for person {pid}: {e}")

    patch = {}
    if full:
        patch["donor_name"] = full
    if email:
        patch["donor_email"] = email
    if patch:
        try:
            sb.table("giving_gifts").update(patch).eq("pco_person_id", pid).execute()
        except Exception as e:
            print(f"  WARNING: could not save identity for person {pid}: {e}")

    cache[pid] = (first, email)
    return cache[pid]





def donor_phone(pid):
    """Best phone number for a donor, for the digest's personal-touch prompts."""
    try:
        data = pco_get(f"/people/v2/people/{pid}/phone_numbers")
        rows = data.get("data", [])
        primary = [r for r in rows if r.get("attributes", {}).get("primary")]
        pick = (primary or rows)
        if pick:
            return pick[0]["attributes"].get("number")
    except Exception as e:
        print(f"  WARNING: phone lookup failed for person {pid}: {e}")
    return None


def giving():
    """Sync gifts, celebrate first-time givers, nudge repeat givers monthly."""
    if not (PCO_APP_ID and PCO_SECRET):
        print("Giving: no PCO_APP_ID / PCO_SECRET secrets; section skipped.")
        return {"connected": False}

    sync_gifts()
    _recurring_ids, new_recurring = recurring_person_ids()
    gifts = fetch_all("giving_gifts", "pco_person_id,donor_name,donor_email,amount_cents,received_at,recurring")
    nudge_log = fetch_all("giving_nudge_log", "donor_key,kind,sent_on")

    donors = {}
    for g in gifts:
        key = g.get("pco_person_id") or (g.get("donor_email") or "").lower()
        if not key:
            continue
        donors.setdefault(key, []).append(g)

    identity_cache = {}
    # A list so the loop below can decrement it. Roughly 350 PCO calls keeps a
    # run comfortably inside its window even when every donor needs looking up;
    # raise it with BACKFILL_PER_RUN once the backlog is cleared.
    # A list so the loop can decrement it. Tolerates an unset OR empty value:
    # the workflow passes "" when the input is left blank, and int("") raises.
    backfill_budget = [_int_env("BACKFILL_PER_RUN", 350)]
    first_cutoff = NOW - timedelta(days=FIRST_GIFT_WINDOW_DAYS)
    ninety = NOW - timedelta(days=90)
    first_timers, nudged, touches = [], [], []
    run_welcomed = set()

    # Weekly totals come from every gift, including ones we cannot tie to a
    # donor; the per-donor loop below skips keyless gifts and would undercount.
    week_gift_times = [(g, parse_ts(g.get("received_at"))) for g in gifts]
    week_gifts = [g for g, t in week_gift_times if t and t >= WEEK_AGO]
    week_count = len(week_gifts)
    week_total = sum(g.get("amount_cents") or 0 for g in week_gifts)

    def _latest(pair):
        ts = [t for t in (parse_ts(d.get("received_at")) for d in pair[1]) if t]
        return max(ts) if ts else datetime.min.replace(tzinfo=timezone.utc)

    for key, ds in sorted(donors.items(), key=_latest, reverse=True):
        times = sorted(t for t in (parse_ts(d["received_at"]) for d in ds) if t)
        if not times:
            continue
        name = next((d["donor_name"] for d in ds if d.get("donor_name")), None)
        pid = ds[0].get("pco_person_id")
        to = next((d.get("donor_email") for d in ds if d.get("donor_email")), None)

        # Backfill name and email from PCO People onto the gift rows.
        #
        # This is the point of this loop now. Giving returns a person id but
        # never a name or an address, and the Pathways engine enrols the
        # first-gift and monthly-partner pathways straight off giving_gifts —
        # so if these columns stay empty, those pathways reach nobody and any
        # letter that did go out would open "friend,".
        #
        # Budgeted, because there are thousands of donors to catch up on and
        # PCO rate-limits hard. Donors are walked newest gift first, so the
        # people a pathway might actually reach are filled in first and the
        # long tail catches up over subsequent runs.
        if pid and (not name or not to) and backfill_budget[0] > 0:
            backfill_budget[0] -= 1
            got_name, got_email = donor_identity(pid, identity_cache)
            name = name or got_name
            to = to or got_email

        # Both the first-gift welcome and the monthly invitation are Pathways
        # now, enrolled and sent by gc3-intranet from this same table. Nothing
        # is emailed from here; what follows only feeds the digest.
        if times[0] >= first_cutoff:
            first_timers.append(name)

    # Personal-touch prompts for the digest: everyone welcomed into the pathway
    # in the last 7 days (any run), with a phone number when PCO has one.
    week_ago_date = (NOW - timedelta(days=7)).date().isoformat()
    welcomed = run_welcomed | {
        r["donor_key"] for r in nudge_log
        if r["kind"] == "first_gift" and str(r["sent_on"]) >= week_ago_date}
    for key in welcomed:
        ds = donors.get(key)
        if not ds:
            continue
        name = next((d["donor_name"] for d in ds if d.get("donor_name")), None) or key
        pid = ds[0].get("pco_person_id")
        touches.append((name, donor_phone(pid) if pid else None))

    return {
        "connected": True,
        "week_count": week_count,
        "week_total": week_total / 100.0,
        "first_timers": first_timers,
        "new_recurring": new_recurring,
        "nudged": nudged,
        "touches": touches,
    }


# ---------------------------------------------------------------- intranet

def intranet():
    """Light activity pulse from the intranet side, last 7 days."""
    since = WEEK_AGO.isoformat()
    out = {}

    def count(table, ts_col="created_at"):
        try:
            res = sb.table(table).select("id", count="exact").gte(ts_col, since).execute()
            return res.count or 0
        except Exception:
            return None

    out["new_accounts"] = count("profiles")
    out["wall_posts"] = count("wall_posts")
    out["prayers"] = count("wall_prayers")
    out["testimonies"] = count("testimonies")
    out["gt_posts"] = count("gt_posts")
    out["mood_checkins"] = count("mood_checkins")
    try:
        res = sb.table("pending_role_grants").select("id", count="exact").execute()
        out["pending_grants"] = res.count or 0
    except Exception:
        out["pending_grants"] = None
    return out


# ---------------------------------------------------------------- meta ads

def meta_ads():
    """Last week's Meta ads numbers and the latest recommendations, as written
    by meta_ads_report.py (its own workflow, Mondays before this one). Reads
    Supabase only, so the digest holds no Meta credentials. Missing tables or
    no rows yet: the section explains how to connect instead of breaking the
    digest."""
    since = (NOW - timedelta(days=7)).date().isoformat()
    try:
        rows = sb.table("meta_ad_insights").select(
            "day,spend,impressions,results,result_type,ad_name"
        ).gte("day", since).execute().data or []
    except Exception:
        rows = []
    if not rows:
        return {"connected": False}

    spend = sum(float(r.get("spend") or 0) for r in rows)
    impressions = sum(int(r.get("impressions") or 0) for r in rows)
    results = {}
    for r in rows:
        t = r.get("result_type")
        if t:
            results[t] = results.get(t, 0) + int(r.get("results") or 0)

    per_ad = {}
    for r in rows:
        a = per_ad.setdefault(r.get("ad_name") or "unnamed", {"spend": 0.0, "results": 0})
        a["spend"] += float(r.get("spend") or 0)
        a["results"] += int(r.get("results") or 0)
    best = None
    for name, a in per_ad.items():
        if a["results"] >= 3:
            cpr = a["spend"] / a["results"]
            if best is None or cpr < best[1]:
                best = (name, cpr)

    recs, strategy = [], None
    try:
        latest = sb.table("meta_ad_recommendations").select(
            "run_on,kind,recommendation"
        ).order("run_on", desc=True).limit(100).execute().data or []
        if latest:
            newest = latest[0]["run_on"]
            for r in latest:
                if r["run_on"] != newest:
                    continue
                if r["kind"] == "strategy":
                    strategy = r["recommendation"]
                else:
                    recs.append(r["recommendation"])
    except Exception:
        pass

    return {"connected": True, "spend": spend, "impressions": impressions,
            "results": results, "best": best, "recs": recs, "strategy": strategy}


# ---------------------------------------------------------------- digest

def h(s):
    return html.escape(str(s))


def section(title, inner):
    return (f'<h2 style="font-size:16px;margin:26px 0 8px;color:#1a1a1a;'
            f'border-bottom:2px solid #eee;padding-bottom:6px;">{title}</h2>{inner}')


def ul(items, empty="Nothing this week."):
    if not items:
        return f'<p style="color:#888;margin:4px 0;">{empty}</p>'
    lis = "".join(f'<li style="margin:3px 0;">{i}</li>' for i in items)
    return f'<ul style="margin:6px 0;padding-left:20px;color:#222;">{lis}</ul>'


def digest(gt, giv, intra, ads):
    week_of = NOW.astimezone(CT).strftime("%B %d, %Y")
    parts = [f'<div style="max-width:640px;margin:0 auto;padding:24px;'
             f'font-family:Arial,Helvetica,sans-serif;font-size:14px;">'
             f'<h1 style="font-size:20px;margin:0 0 4px;">GC3 Weekly Engagement Digest</h1>'
             f'<p style="color:#777;margin:0 0 10px;">Week ending {week_of}</p>']

    gt_inner = ul([h(n) for n in gt["new_members"]], "No new Growth Track members.")
    parts.append(section("New Growth Track members", gt_inner))
    parts.append(section(
        "Moving through Growth Track",
        ul([f"{h(n)}: {c} lesson{'s' if c != 1 else ''} completed" for n, c in gt["active"]],
           "No lessons completed this week.")))
    parts.append(section(
        "Milestones reached",
        ul([f"{h(n)} finished {h(m)}" for n, m in gt["milestones"]])))
    parts.append(section(
        "Gone quiet (started but no activity in 14+ days)",
        ul([f"{h(n)}: quiet {d} days" for n, d in gt["stalled"]],
           "Nobody is stalled. Wonderful.")))

    if giv.get("connected"):
        giv_lines = [f"{giv['week_count']} gift(s) this week totaling ${giv['week_total']:,.2f}"]
        parts.append(section("Giving", ul(giv_lines)))
        parts.append(section("First-time givers", ul([h(n) for n in giv["first_timers"]],
                                                     "No first-time givers this week.")))
        parts.append(section("New monthly partners", ul([h(n) for n in giv["new_recurring"]],
                                                        "No new recurring donors this week.")))
        parts.append(section("Monthly giving invitations sent", ul([h(n) for n in giv["nudged"]],
                                                                   "None sent this run.")))
        touch_lines = []
        for name, phone in giv.get("touches", []):
            first = h(str(name).split(" ")[0])
            shown = h(phone) if phone else "no phone on file, check PCO"
            touch_lines.append(
                f"<b>{h(name)}</b> ({shown}): send a personal text, then have the office mail "
                f"a handwritten thank-you note. Suggested text: &quot;Hey {first}, it's Pastor "
                f"Donte. I saw your first gift come through this week. Thank you for trusting "
                f"God with that. Proud to be your pastor.&quot;")
        parts.append(section(
            "Personal touches to make this week (not automated on purpose)",
            ul(touch_lines, "No new givers to personally reach out to this week.")))
    else:
        parts.append(section("Giving", '<p style="color:#888;">Not connected yet. Add PCO_APP_ID '
                                       'and PCO_SECRET repo secrets (a Planning Center personal '
                                       'access token) to activate first-time giver celebrations '
                                       'and monthly giving nudges.</p>'))

    if ads.get("connected"):
        parts_line = f"${ads['spend']:,.2f} spent, {ads['impressions']:,} impressions"
        if ads["results"]:
            counted = ", ".join(f"{v} {h(k)}" for k, v in
                                sorted(ads["results"].items(), key=lambda x: -x[1]))
            parts_line += f", results: {counted}"
        ad_lines = [parts_line]
        if ads.get("best"):
            name, cpr = ads["best"]
            ad_lines.append(f"Best value: <b>{h(name)}</b> at ${cpr:,.2f} per result")
        parts.append(section("Meta ads (last 7 days)", ul(ad_lines)))
        parts.append(section(
            "Meta ads: recommended moves (made in Ads Manager, not automated)",
            ul([h(r) for r in ads["recs"][:8]], "No flags this week; let it ride.")))
        if ads.get("strategy"):
            body = "<br>".join(h(ln) for ln in ads["strategy"].splitlines() if ln.strip())
            parts.append(section("Meta ads: strategy note",
                                 f'<p style="margin:6px 0;color:#222;">{body}</p>'))
    else:
        parts.append(section("Meta ads", '<p style="color:#888;">Not connected yet. Apply '
                                         'supabase/meta_ads_schema.sql, add META_ACCESS_TOKEN and '
                                         'META_AD_ACCOUNT_ID repo secrets, and the Meta ads workflow '
                                         'fills this in each Monday. See the README.</p>'))

    intra_lines = []
    labels = [("new_accounts", "New intranet accounts"), ("wall_posts", "Wall posts"),
              ("prayers", "Prayer requests"), ("testimonies", "Testimonies"),
              ("gt_posts", "Growth Track community posts"), ("mood_checkins", "Mood check-ins")]
    for key, label in labels:
        v = intra.get(key)
        if v is not None:
            intra_lines.append(f"{label}: {v}")
    if intra.get("pending_grants"):
        intra_lines.append(f"<b>Pending role grants awaiting action: {intra['pending_grants']}</b>")
    parts.append(section("Intranet pulse (7 days)", ul(intra_lines, "No activity recorded.")))

    sent_summary = {}
    for kind, _ in emails_sent:
        sent_summary[kind] = sent_summary.get(kind, 0) + 1
    auto_lines = [f"{k}: {v} email(s)" for k, v in sorted(sent_summary.items())]
    if DRY_RUN:
        auto_lines.append("DRY RUN: nothing was actually sent.")
    if send_failures:
        auto_lines.append(f"<b>{len(send_failures)} send failure(s), check the Action log.</b>")
    parts.append(section("What this automation sent", ul(auto_lines, "No nudges were due.")))

    parts.append('<p style="color:#aaa;font-size:12px;margin-top:26px;">Automated weekly by the '
                 'gc3-sermon-library engagement job.</p></div>')
    return "".join(parts)


# ---------------------------------------------------------------- main

def main():
    print(f"Engagement job starting ({'DRY RUN' if DRY_RUN else 'live'}), {NOW.astimezone(CT):%Y-%m-%d %H:%M} Central")
    gt = growth_track()
    giv = giving()
    intra = intranet()
    ads = meta_ads()
    # The job runs daily so pathway steps land on time; the digest ships once a
    # week (Mondays, Central) unless FORCE_DIGEST asks for it now.
    digest_day = NOW.astimezone(CT).weekday() == 0
    force = os.environ.get("FORCE_DIGEST", "").strip() in ("1", "true", "yes")
    if digest_day or force:
        body = digest(gt, giv, intra, ads)
        week_of = NOW.astimezone(CT).strftime("%b %d")
        send_email(DIGEST_TO, f"GC3 Weekly Digest: Growth Track and Giving ({week_of})",
                   body, "weekly_digest", capped=False)
    else:
        print("Not digest day (Monday Central); nudges only.")
    print(f"Done. {len(emails_sent)} email(s) {'previewed' if DRY_RUN else 'sent'}, "
          f"{len(send_failures)} failure(s).")
    if send_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
