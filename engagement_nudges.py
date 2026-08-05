"""Weekly engagement job: Growth Track movement, giving celebrations, digest.

One run does four things:

1. Growth Track milestones. Reads gt_progress and celebrates, by email from
   Pastor Donte, anyone who just finished a phase (GATHER, GROW, GO) or the
   whole course. Sends are logged to gt_email_log (kinds celebrate_gather,
   celebrate_grow, celebrate_go, celebrate_course) so nobody is emailed twice,
   and email_optout on gt_profiles is respected.

2. Giving sync. Pulls donations from Planning Center Giving into the
   giving_gifts table (needs PCO_APP_ID and PCO_SECRET, a PCO personal access
   token). Skipped gracefully when the secrets are absent.

3. Giving journey and nudges. First-time givers enter a 90 day generosity
   journey: a personal welcome from Pastor Donte on day 0 (kind first_gift),
   then touchpoints on day 5, day 30 (with a monthly partner invitation), and
   day 90 (kinds first_gift_d5, first_gift_d30, first_gift_d90). Repeat givers
   past the journey who are not on a recurring schedule get a warm invitation
   to become monthly givers (kind monthly_nudge, at most once every 60 days).
   Logged in giving_nudge_log, keyed by donor, because givers are not always
   platform users. The weekly digest also prompts the personal touches that
   should not be automated: a text from the pastor and a handwritten note.

4. Weekly digest. One email to the Lead Pastor covering Growth Track movement
   (new members, active learners, milestones, who has gone quiet), intranet
   activity (new accounts, wall posts, prayers, testimonies), giving (weekly
   totals, first-time givers, new monthly partners), and what this job sent.

Env vars:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database (required; the
      NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_KEY spellings also work)
  RESEND_API_KEY                       sending (absent = report-only dry run)
  PCO_APP_ID, PCO_SECRET               Planning Center personal access token
                                       (absent = giving section skipped)
Optional:
  DIGEST_TO     where the weekly digest goes (default dontebee@gmail.com)
  NUDGE_FROM    From header (default "Pastor Donte <hello@godchasers.church>")
  REPLY_TO      Reply-To on every send (default hello@godchasers.church)
  DRY_RUN       "1" to print instead of send
  MAX_EMAILS    cap on member and giver emails per run (default 30)
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
JOURNEY_CATCHUP_DAYS = 14    # how late a journey step may still be sent
MONTHLY_NUDGE_COOLDOWN_DAYS = 60
STALLED_AFTER_DAYS = 14

GIVING_URL = "https://godchasers.churchcenter.com/giving?frequency=monthly"

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


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def send_email(to, subject, html_body, kind, capped=True):
    """Send through Resend, honoring DRY_RUN and the per-run cap."""
    if capped and len(emails_sent) >= MAX_EMAILS:
        print(f"  SKIP (cap of {MAX_EMAILS} reached): {kind} -> {to}")
        return False
    if DRY_RUN:
        print(f"  DRY RUN {kind} -> {to}: {subject}")
        emails_sent.append((kind, to))
        return True
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": NUDGE_FROM, "to": [to], "reply_to": REPLY_TO,
              "subject": subject, "html": html_body},
        timeout=30,
    )
    if r.status_code in (200, 201):
        print(f"  SENT {kind} -> {to}: {subject}")
        emails_sent.append((kind, to))
        return True
    print(f"  FAILED {kind} -> {to}: HTTP {r.status_code} {r.text[:200]}")
    send_failures.append((kind, to, r.status_code))
    return False


def letter(first_name, paragraphs, cta=None):
    """A short personal note styled as a letter from Pastor Donte."""
    name = html.escape(first_name or "friend")
    body = "".join(
        f'<p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:#222;">{p}</p>'
        for p in paragraphs
    )
    button = ""
    if cta:
        label, url = cta
        button = (f'<p style="margin:20px 0;"><a href="{url}" '
                  f'style="background:#1a56db;color:#fff;text-decoration:none;'
                  f'padding:11px 22px;border-radius:6px;font-size:15px;">{label}</a></p>')
    return (
        '<div style="max-width:560px;margin:0 auto;padding:28px 24px;'
        'font-family:Georgia,serif;">'
        f'<p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:#222;">{name},</p>'
        f"{body}{button}"
        '<p style="margin:22px 0 0;font-size:16px;line-height:1.6;color:#222;">'
        "With you and for you,<br>Pastor Donte<br>"
        '<span style="color:#777;font-size:14px;">GodChasers Church</span></p></div>'
    )


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
            full, first = display(uid)
            milestones.append((full, label))
            prof = gt_profiles.get(uid, {})
            to = emails.get(str(uid))
            if prof.get("email_optout") or not to:
                continue
            if kind == "celebrate_course":
                paras = [
                    "You did it. You finished the entire Growth Track, and I could not be more proud of you.",
                    "This was never about checking boxes. It was about you discovering who God made you to be and where you fit in His house. You leaned in, and it shows.",
                    "Your next step is simple: get planted on a team and in a tribe. I would love to help you find the right spot, so just reply to this email.",
                ]
                subject = "You finished Growth Track. I'm proud of you."
            else:
                paras = [
                    f"I saw that you just completed the {html.escape(label)} phase of Growth Track, and I wanted you to hear it from me: well done.",
                    "Every lesson you finish is a step deeper into who God is calling you to be. Keep going, the next phase is ready when you are.",
                    "If anything in this phase raised questions, reply to this email. I read these.",
                ]
                subject = f"You finished {label}. Keep going!"
            if send_email(to, subject, letter(first, paras), kind):
                celebrated.append((full, label))
                if not DRY_RUN:
                    sb.table("gt_email_log").insert({"user_id": uid, "kind": kind}).execute()

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


# ---------------------------------------------------------------- giving

# The 90 day generosity journey for first-time givers. Each step fires once the
# donor's first gift is at least `day` days old, and is skipped entirely if it
# is more than JOURNEY_CATCHUP_DAYS late (so donors who gave long before this
# automation existed never get stale touchpoints). One step per donor per run.
JOURNEY = [
    {
        "kind": "first_gift", "day": 0,
        "subject": "You just did something most people never do",
        "paras": [
            "I don't want to let this moment pass without telling you how much it means. "
            "You just gave to GodChasers Church for the first time, and I want to personally "
            "say thank you. Not just on behalf of our church family, but as your pastor.",
            "Here is what I know about this moment: this was not just a transaction, it was a "
            "declaration. By taking this step you declared that you are putting God first, and "
            "that your heart is moving toward something bigger than yourself. Jesus said it "
            "plainly: where your treasure goes, your heart follows. You just moved your heart.",
            "And because of your faithfulness, families in our community are going to be served, "
            "people searching for hope are going to find it, and real lives are going to change. "
            "That is not church talk. That is what your generosity actually does.",
            "So as your pastor, I am proud of you. This is a big moment, and I wanted to "
            "celebrate it with you. God is not done with what He has started in you.",
            '<i>P.S. Keep an eye on your mailbox. I am sending you something personally.</i>',
        ],
    },
    {
        "kind": "first_gift_d5", "day": 5,
        "subject": "The story your generosity is writing",
        "paras": [
            "A few days ago you gave to GodChasers Church for the first time, and I have been "
            "thinking about it since. I wanted you to see what you are now part of.",
            "Every week, people walk through our doors carrying things nobody can see: grief, "
            "questions, empty tanks. And every week, because people like you sow into this "
            "house, they meet a God who sees them. Your gift is already in that story.",
            "If there is anything I can be praying about for you, reply to this email. "
            "I read these myself.",
        ],
    },
    {
        "kind": "first_gift_d30", "day": 30,
        "subject": "One month ago you took a step",
        "paras": [
            "One month ago you gave to GodChasers Church for the first time. I told you then "
            "that it was a declaration, and I meant it. Today I want to invite you into a rhythm.",
            "The people who grow the most in generosity are not the ones who give the biggest "
            "gifts. They are the ones who give consistently. Would you pray about becoming a "
            "monthly partner? It takes about a minute to set up, and it turns a moment of "
            "obedience into a lifestyle of faith.",
            "No pressure and no obligation. If it is not your season, that is okay. "
            "But if God nudges you, I would love for you to follow it.",
        ],
        "cta": ("Become a monthly partner", GIVING_URL),
    },
    {
        "kind": "first_gift_d90", "day": 90,
        "subject": "90 days ago something shifted",
        "paras": [
            "Ninety days ago you gave your first gift to GodChasers Church. I do not know if "
            "you have thought about it since, but I have. That day something shifted in you, "
            "and I have watched God honor it.",
            "Thank you for being part of this house. Not just for what you have given, but for "
            "who you are becoming. I am praying that the next ninety days hold more of God's "
            "presence, more open doors, and more of the purpose He wrote on your life.",
            "If you ever want to talk, pray, or find your place on a team, my inbox is open. "
            "Just reply.",
        ],
    },
]

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


def donor_email(pid, cache):
    """Look up a donor's primary email in PCO People, at most once per run."""
    if pid in cache:
        return cache[pid]
    email = None
    try:
        data = pco_get(f"/people/v2/people/{pid}/emails")
        rows = data.get("data", [])
        primary = [r for r in rows if r.get("attributes", {}).get("primary")]
        pick = (primary or rows)
        if pick:
            email = pick[0]["attributes"].get("address")
    except Exception as e:
        print(f"  WARNING: email lookup failed for person {pid}: {e}")
    cache[pid] = email
    if email:
        sb.table("giving_gifts").update({"donor_email": email}).eq("pco_person_id", pid).execute()
    return email


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
    recurring_ids, new_recurring = recurring_person_ids()
    gifts = fetch_all("giving_gifts", "pco_person_id,donor_name,donor_email,amount_cents,received_at,recurring")
    nudge_log = fetch_all("giving_nudge_log", "donor_key,kind,sent_on")

    def last_sent(key, kind):
        dates = [r["sent_on"] for r in nudge_log if r["donor_key"] == key and r["kind"] == kind]
        return max(dates) if dates else None

    donors = {}
    for g in gifts:
        key = g.get("pco_person_id") or (g.get("donor_email") or "").lower()
        if not key:
            continue
        donors.setdefault(key, []).append(g)

    email_cache = {}
    first_cutoff = NOW - timedelta(days=FIRST_GIFT_WINDOW_DAYS)
    ninety = NOW - timedelta(days=90)
    journey_span = max(s["day"] for s in JOURNEY) + JOURNEY_CATCHUP_DAYS
    first_timers, nudged, touches = [], [], []
    run_welcomed = set()

    # Weekly totals come from every gift, including ones we cannot tie to a
    # donor; the per-donor loop below skips keyless gifts and would undercount.
    week_gift_times = [(g, parse_ts(g.get("received_at"))) for g in gifts]
    week_gifts = [g for g, t in week_gift_times if t and t >= WEEK_AGO]
    week_count = len(week_gifts)
    week_total = sum(g.get("amount_cents") or 0 for g in week_gifts)

    optout_emails = set()
    gt_profiles = {p["id"]: p for p in fetch_all("gt_profiles", "id,email_optout")}
    for uid, em in auth_emails().items():
        if gt_profiles.get(uid, {}).get("email_optout"):
            optout_emails.add(em.lower())

    for key, ds in donors.items():
        times = sorted(t for t in (parse_ts(d["received_at"]) for d in ds) if t)
        if not times:
            continue
        name = next((d["donor_name"] for d in ds if d.get("donor_name")), None) or "friend"
        first = name.split(" ")[0]
        pid = ds[0].get("pco_person_id")
        to = next((d.get("donor_email") for d in ds if d.get("donor_email")), None)

        # 90 day generosity journey: fires while the first gift is fresh enough.
        days_since_first = (NOW - times[0]).days
        if times[0] >= first_cutoff:
            first_timers.append(name)
        if days_since_first <= journey_span:
            step = next(
                (s for s in JOURNEY
                 if s["day"] <= days_since_first <= s["day"] + JOURNEY_CATCHUP_DAYS
                 and not last_sent(key, s["kind"])),
                None)
            if step:
                if not to and pid:
                    to = donor_email(pid, email_cache)
                if to and to.lower() not in optout_emails:
                    if send_email(to, step["subject"],
                                  letter(first, step["paras"], step.get("cta")),
                                  step["kind"]):
                        if step["kind"] == "first_gift":
                            run_welcomed.add(key)
                        if not DRY_RUN:
                            sb.table("giving_nudge_log").upsert(
                                {"donor_key": key, "kind": step["kind"]},
                                on_conflict="donor_key,kind,sent_on").execute()
            continue  # donors inside the journey never get the generic nudge

        # Monthly nudge: 2+ gifts in 90 days, past the journey, not recurring.
        recent = [t for t in times if t >= ninety]
        if len(recent) >= 2 and pid not in recurring_ids:
            last = last_sent(key, "monthly_nudge")
            if last and (NOW.date() - datetime.fromisoformat(last).date()).days < MONTHLY_NUDGE_COOLDOWN_DAYS:
                continue
            if not to and pid:
                to = donor_email(pid, email_cache)
            if to and to.lower() not in optout_emails:
                paras = [
                    "I have noticed your faithfulness in giving, and I want you to know it does not go unseen, by me or by God.",
                    "Would you pray about taking one more step: becoming a monthly partner? Consistent giving is what lets us plan boldly, and it turns your generosity into a rhythm instead of a decision you have to remake every time.",
                    "No pressure and no obligation. If it is not your season, that is okay. But if God nudges you, it takes about a minute to set up.",
                ]
                if send_email(to, "Would you pray about becoming a monthly partner?",
                              letter(first, paras, ("Set up monthly giving", GIVING_URL)),
                              "monthly_nudge"):
                    nudged.append(name)
                    if not DRY_RUN:
                        sb.table("giving_nudge_log").upsert(
                            {"donor_key": key, "kind": "monthly_nudge"},
                            on_conflict="donor_key,kind,sent_on").execute()

    # Personal-touch prompts for the digest: everyone welcomed into the journey
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


def digest(gt, giv, intra):
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
    # The job runs daily so journey steps land on time; the digest ships once a
    # week (Mondays, Central) unless FORCE_DIGEST asks for it now.
    digest_day = NOW.astimezone(CT).weekday() == 0
    force = os.environ.get("FORCE_DIGEST", "").strip() in ("1", "true", "yes")
    if digest_day or force:
        body = digest(gt, giv, intra)
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
