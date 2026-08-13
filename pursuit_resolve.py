"""Pursuit identity resolution: many systems in, one person out.

Pursuit is a status board for every person God sends. Before any board can
show anyone, the house has to agree on who "anyone" is: the same human
appears in Meta's lead forms, in ChurchFunnels, in Growth Track, in
Planning Center, and in the intranet, wearing a different id each time.
This job walks every source, matches them, and keeps one row per person in
pursuit_people, with a card on the board for anyone still in the chase.

Matching, strongest evidence first:

  1. Planning Center person id. Authoritative when present.
  2. Exact email, lowercased.
  3. Phone, normalized to its last ten digits.
  4. Name alone: NEVER a merge. Two Michael Browns are two people until
     somebody who knows them says otherwise. Same-name pairs are written
     to pursuit_merge_candidates for a human to judge.

Ship assignment reads evidence, never guesses upward:

  friendship  a lead exists, a visit was planned
  fellowship  they attended something, or simply exist in Planning Center:
              PD's floor rule, a PCO record at all is Fellowship
  partnership Time, Talent, or Treasure at its bar: Growth Track finished,
              on a serving team, 10+ gifts in 24 months, or PCO calls them
              a Member or Partner (the promise, P1)
  discipleship  being formed: section one of Growth Track done, or ten or
              more Growth Track sign-in days. Groups join when synced.
  leadership  a Hub role at tier 50 or above: team leads, GLT, staff,
              directors, per PD

The clock rides alongside: every Time, Talent or Treasure signal stamps
last_signal_at, and PD's rule makes 24 silent months inactive, which takes
a person off the board while the record stays. Archive remains human-only.

Children never board. A four year old in PCO stays in pco_people for the
household roll-up and gets no pursuit_people row: ships are for people who
can answer for themselves, and kids' check-ins credit their adults.

Nobody is ever moved backward by this job. If a person is already further
along than the evidence suggests (a human moved them, or a track promoted
them), the higher ship stands.

**Counts only in the log.** Names, emails and phone numbers belong in the
database and nowhere else: Action logs are visible to anyone who can read
the repo.

Env vars:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database (the
      NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_KEY spellings also work)
Optional:
  DRY_RUN   "1" to read and report, writing nothing
"""
import os
import re
import sys
from datetime import datetime, timezone

import gc3_env

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

# The fleet, in order. Index is rank: a person never moves down.
SHIPS = ["friendship", "fellowship", "partnership", "discipleship", "leadership"]

# ChurchFunnels pipeline stages map onto the board's working sub-stages.
# Same vocabulary the team already uses, so nobody relearns anything.
GHL_STAGE_MAP = {
    "planned a visit": "planned_visit",
    "attended a service": "attended",
    "pyv no show": "no_show",
    "pyv not coming this week": "not_coming",
    "attended - no check in": "attended",
}


def fetch_all(table, select="*"):
    """Read a whole table through PostgREST, 1000 rows at a time."""
    rows, start = [], 0
    while True:
        batch = sb.table(table).select(select).range(start, start + 999).execute().data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def norm_email(v):
    v = (v or "").strip().lower()
    return v if "@" in v and "." in v.split("@")[-1] else None


def norm_phone(v):
    """Last ten digits: enough to match a person across systems that
    disagree about country codes, dashes and parentheses."""
    digits = re.sub(r"\D", "", v or "")
    return digits[-10:] if len(digits) >= 10 else None


def split_name(full):
    parts = (full or "").strip().split()
    if not parts:
        return None, None
    return parts[0], (" ".join(parts[1:]) or None)


DAY = 86400.0


def parse_when(v):
    """ISO timestamp or date string to epoch seconds, else None."""
    if not v:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def signal(person, when, source):
    """A Time, Talent or Treasure signal landed for this person. The state
    clock reads only these: PD's rule is 'given, served or registered', so a
    mere PCO record edit never counts as life."""
    ts = when if isinstance(when, (int, float)) else parse_when(when)
    if ts is None:
        return
    if ts > person.get("_signal_ts", 0):
        person["_signal_ts"] = ts
        person["_signal_src"] = source


def rank(ship):
    try:
        return SHIPS.index(ship or "friendship")
    except ValueError:
        return 0


class Registry:
    """People being assembled this run, indexed by every id we know them by."""

    def __init__(self):
        self.people = []            # list of dicts
        self.by_pco = {}
        self.by_email = {}
        self.by_phone = {}
        self.by_name = {}           # for merge candidates only, never a match
        self.same_name_pairs = []

    def find(self, pco=None, email=None, phone=None):
        if pco and pco in self.by_pco:
            return self.by_pco[pco]
        if email and email in self.by_email:
            return self.by_email[email]
        if phone and phone in self.by_phone:
            return self.by_phone[phone]
        return None

    def index(self, person):
        if person.get("pco_person_id"):
            self.by_pco[person["pco_person_id"]] = person
        if person.get("email"):
            self.by_email[person["email"]] = person
        if person.get("phone"):
            self.by_phone[person["phone"]] = person
        key = (person.get("display_name") or "").strip().lower()
        if key:
            twin = self.by_name.get(key)
            if twin is not None and twin is not person:
                # A name collision is a question for a human, not a merge.
                self.same_name_pairs.append((twin, person))
            else:
                self.by_name[key] = person

    def upsert(self, *, pco=None, email=None, phone=None, name=None,
               ship="friendship", source=None, seen_at=None, **extra):
        email, phone = norm_email(email), norm_phone(phone)
        person = self.find(pco, email, phone)
        if person is None:
            first, last = split_name(name)
            person = {
                "first_name": first, "last_name": last,
                "display_name": (name or "").strip() or None,
                "email": email, "phone": phone,
                "pco_person_id": pco,
                "ship": ship, "source": source,
                "first_seen_at": seen_at,
            }
            person.update({k: v for k, v in extra.items() if v})
            self.people.append(person)
        else:
            # Fill blanks, never overwrite something we already trust.
            if not person.get("email") and email:
                person["email"] = email
            if not person.get("phone") and phone:
                person["phone"] = phone
            if not person.get("pco_person_id") and pco:
                person["pco_person_id"] = pco
            if not person.get("display_name") and name:
                person["display_name"] = name.strip()
                person["first_name"], person["last_name"] = split_name(name)
            for k, v in extra.items():
                if v and not person.get(k):
                    person[k] = v
            if rank(ship) > rank(person.get("ship")):
                person["ship"] = ship          # evidence promotes
            if seen_at and (not person.get("first_seen_at") or seen_at < person["first_seen_at"]):
                person["first_seen_at"] = seen_at
        self.index(person)
        return person


def main():
    now = datetime.now(timezone.utc)
    print(f"Pursuit resolve starting ({'DRY RUN' if DRY_RUN else 'live'}), {now:%Y-%m-%d %H:%M} UTC")

    reg = Registry()
    cards = []          # (person, card dict) pending person ids

    # --- The Planning Center roster: PD's floor rule (L0). A PCO record at
    # all is Fellowship; a membership of Member or Partner is the promise
    # and boards Partnership (P1). This source goes first so the PCO person
    # id anchors identity before the fuzzier sources arrive.
    roster = fetch_all("pco_people",
                       "pco_person_id,name,first_name,last_name,email,phone,"
                       "membership,child,avatar_url,pco_created_at")
    kids = 0
    for r in roster:
        if r.get("child"):
            kids += 1
            continue                 # children never board; households roll up
        member = (r.get("membership") or "").strip().lower() in ("member", "partner")
        name = (r.get("name")
                or " ".join(x for x in (r.get("first_name"), r.get("last_name")) if x)
                or None)
        person = reg.upsert(pco=r["pco_person_id"], email=r.get("email"),
                            phone=r.get("phone"), name=name,
                            ship="partnership" if member else "fellowship",
                            source="pco_people", seen_at=r.get("pco_created_at"),
                            avatar_url=r.get("avatar_url"))
        # The moment the house entered them is the floor signal: a record
        # typed in last month cannot have two years of silence behind it.
        signal(person, r.get("pco_created_at"), "pco_record")
    print(f"  pco roster: {len(roster)} record(s), {kids} kept ashore as children")

    # --- Growth Track: people the house is already forming. Emails live in
    # profiles (gt_profiles has none), keyed by the same auth user id.
    gt = fetch_all("gt_profiles",
                   "id,display_name,first_name,last_name,phone,created_at,pw_team")
    emails = {p["id"]: p["email"] for p in fetch_all("profiles", "id,email") if p.get("email")}
    progress = fetch_all("gt_progress", "user_id,lesson_id,completed_at")
    lessons = [l for l in fetch_all("gt_lessons", "id,submodule_id,progress_key,is_published")
               if l.get("is_published")]
    total_lessons = len({l["progress_key"] for l in lessons})

    # Section one, for PD's rule D10: finishing the first module of Growth
    # Track is formation begun, and boards Discipleship.
    modules = sorted([m for m in fetch_all("gt_modules", "id,sort_order,is_published")
                      if m.get("is_published")], key=lambda m: m.get("sort_order") or 0)
    sub_by_module = {}
    for sm in fetch_all("gt_submodules", "id,module_id"):
        sub_by_module.setdefault(sm["module_id"], set()).add(sm["id"])
    section1_lessons = set()
    if modules:
        first_subs = sub_by_module.get(modules[0]["id"], set())
        section1_lessons = {l["id"] for l in lessons if l.get("submodule_id") in first_subs}

    done_per_user, last_done = {}, {}
    for row in progress:
        if row.get("completed_at"):
            done_per_user.setdefault(row["user_id"], set()).add(row["lesson_id"])
            ts = parse_when(row["completed_at"])
            if ts and ts > last_done.get(row["user_id"], 0):
                last_done[row["user_id"]] = ts

    # D3: signed in 10+ distinct days. gt_activity is one row per user-day.
    activity_days, last_active = {}, {}
    for a in fetch_all("gt_activity", "user_id,day"):
        activity_days[a["user_id"]] = activity_days.get(a["user_id"], 0) + 1
        ts = parse_when(a.get("day"))
        if ts and ts > last_active.get(a["user_id"], 0):
            last_active[a["user_id"]] = ts
    for p in gt:
        name = (p.get("display_name")
                or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
                or None)
        done = done_per_user.get(p["id"], set())
        finished = total_lessons and len(done) >= total_lessons
        planted = finished or bool(p.get("pw_team"))
        # PD's Discipleship rules: section one of Growth Track done (D10), or
        # signed in ten or more days (D3). Formation outranks partnership.
        formed = (section1_lessons and section1_lessons <= done) \
            or activity_days.get(p["id"], 0) >= 10
        ship = "discipleship" if formed else ("partnership" if planted else "fellowship")
        person = reg.upsert(email=emails.get(p["id"]), phone=p.get("phone"), name=name,
                            ship=ship,
                            source="growth_track", seen_at=p.get("created_at"),
                            gt_profile_id=p["id"])
        signal(person, last_done.get(p["id"]), "growth_track")
        signal(person, last_active.get(p["id"]), "growth_track")
    print(f"  growth track: {len(gt)} profile(s)")

    # --- Serving teams: partnership evidence from Planning Center.
    serving = fetch_all("pco_serving", "person_id,full_name,email")
    now_ts = now.timestamp()
    for s in serving:
        person = reg.upsert(pco=s.get("person_id"), email=s.get("email"),
                            name=s.get("full_name"),
                            ship="partnership", source="serving")
        # The serving table is the CURRENT roster, so being on it is Talent
        # being given now, whatever the other clocks say.
        signal(person, now_ts, "serving")
    print(f"  serving: {len(serving)} assignment(s)")

    # --- Group life: Charisma and every life group. PD's D9: being in any
    # group is formation and boards Discipleship; D2: leading one likewise
    # (leaders also hold Leadership rules elsewhere when they carry a Hub
    # role). A current membership is ongoing Time, so it keeps the clock
    # alive the way the serving roster does.
    memberships = fetch_all("pco_group_memberships",
                            "pco_person_id,group_name,role,joined_at")
    in_groups = 0
    for m in memberships:
        pid = m.get("pco_person_id")
        if not pid:
            continue
        in_groups += 1
        person = reg.upsert(pco=pid, ship="discipleship", source="group")
        signal(person, now.timestamp(), "group")
        signal(person, m.get("joined_at"), "group")
    print(f"  groups: {len(memberships)} membership(s), {in_groups} with a person id")

    # --- Giving: Treasure. PD's P3: ten or more gifts in 24 months is
    # partnership. Counts and dates only; amounts are never read here, and
    # nothing outward is ever triggered by any of it.
    gifts = fetch_all("giving_gifts", "pco_person_id,donor_email,donor_name,received_at")
    gift_count_24mo, last_gift = {}, {}
    cutoff_24 = now.timestamp() - 730 * DAY
    for g in gifts:
        pid = g.get("pco_person_id")
        if not pid:
            continue
        ts = parse_when(g.get("received_at"))
        if ts is None:
            continue
        if ts >= cutoff_24:
            gift_count_24mo[pid] = gift_count_24mo.get(pid, 0) + 1
        if ts > last_gift.get(pid, (0, None))[0]:
            last_gift[pid] = (ts, g)
    strong = 0
    for pid, (ts, g) in last_gift.items():
        is_strong = gift_count_24mo.get(pid, 0) >= 10
        strong += 1 if is_strong else 0
        person = reg.upsert(pco=pid, email=g.get("donor_email"),
                            name=g.get("donor_name"),
                            ship="partnership" if is_strong else "friendship",
                            source="giving")
        signal(person, ts, "gift")
    print(f"  giving: {len(last_gift)} giver(s), {strong} at the Partnership bar")

    # --- Leadership: PD's E1/E2. Team leads sit at tier 50 in the Hub's own
    # roles table; GLT, staff and directors sit above. Tier 50 is the line.
    role_tier = {r["id"]: r.get("tier") or 0 for r in fetch_all("roles", "id,tier")}
    lead_uids = set()
    for ur in fetch_all("user_roles", "user_id,role_id,expires_at"):
        exp = parse_when(ur.get("expires_at"))
        if exp and exp < now.timestamp():
            continue
        if role_tier.get(ur.get("role_id"), 0) >= 50:
            lead_uids.add(ur["user_id"])
    leads = 0
    for uid in lead_uids:
        email = emails.get(uid)
        if not email:
            continue
        leads += 1
        person = reg.upsert(email=email, ship="leadership",
                            source="role", auth_user_id=uid)
        signal(person, now.timestamp(), "leads")
    print(f"  leadership: {leads} role holder(s) at tier 50 or above")

    # --- ChurchFunnels: the chase as it stands today.
    ghl = fetch_all("ghl_opportunities",
                    "ghl_contact_id,contact_name,email,phone,stage,source,created_on")
    for o in ghl:
        stage = GHL_STAGE_MAP.get((o.get("stage") or "").strip().lower())
        if stage is None:
            continue                      # test rows and unknown stages stay out
        person = reg.upsert(email=o.get("email"), phone=o.get("phone"),
                            name=o.get("contact_name"),
                            ship="fellowship" if stage in ("attended", "returned") else "friendship",
                            source="churchfunnels", seen_at=o.get("created_on"),
                            ghl_contact_id=o.get("ghl_contact_id"))
        signal(person, o.get("created_on"), "registration")
        cards.append((person, {"stage": stage, "source": "churchfunnels",
                               "created_at": o.get("created_on")}))
    print(f"  churchfunnels: {len(ghl)} opportunity(s)")

    # --- Meta lead forms: the newest hands raised.
    leads = fetch_all("meta_leads",
                      "leadgen_id,full_name,email,phone,created_time,campaign_id,campaign_name,ad_id")
    for l in leads:
        person = reg.upsert(email=l.get("email"), phone=l.get("phone"),
                            name=l.get("full_name"), ship="friendship",
                            source="meta_form", seen_at=l.get("created_time"),
                            meta_leadgen_id=l.get("leadgen_id"))
        signal(person, l.get("created_time"), "registration")
        cards.append((person, {"stage": "planned_visit", "source": "meta_form",
                               "meta_leadgen_id": l.get("leadgen_id"),
                               "campaign_id": l.get("campaign_id"),
                               "campaign_name": l.get("campaign_name"),
                               "ad_id": l.get("ad_id"),
                               "created_at": l.get("created_time")}))
    print(f"  meta leads: {len(leads)} lead(s)")

    # --- The state clock. PD: no Time, Talent or Treasure in 24 months
    # takes a person off the board. Ship is a high-water mark and never
    # moves for silence; state is the pulse that decides visibility.
    from datetime import datetime as _dt, timezone as _tz
    states = {"active": 0, "dormant": 0, "inactive": 0}
    for p in reg.people:
        ts = p.pop("_signal_ts", 0)
        src = p.pop("_signal_src", None)
        age_days = (now.timestamp() - ts) / DAY if ts else None
        if age_days is None or age_days > 730:
            p["state"] = "inactive"
        elif age_days > 180:
            p["state"] = "dormant"
            p["dormant_since"] = _dt.fromtimestamp(ts + 180 * DAY, tz=_tz.utc).isoformat()
        else:
            p["state"] = "active"
        if ts:
            p["last_signal_at"] = _dt.fromtimestamp(ts, tz=_tz.utc).isoformat()
            p["last_signal_source"] = src
        states[p["state"]] += 1

    ships = {}
    for p in reg.people:
        ships[p["ship"]] = ships.get(p["ship"], 0) + 1
    print()
    print(f"Resolved {len(reg.people)} person(s) from "
          f"{len(roster) + len(gt) + len(serving) + len(ghl) + len(leads)} source row(s).")
    for s in SHIPS:
        if ships.get(s):
            print(f"  {s}: {ships[s]}")
    print(f"State: {states['active']} active, {states['dormant']} dormant, "
          f"{states['inactive']} inactive (off the board, record kept)")
    print(f"Cards to place: {len(cards)}")
    print(f"Same-name pairs for a human to judge: {len(reg.same_name_pairs)}")

    if DRY_RUN:
        print()
        print("DRY RUN: nothing written.")
        return

    # --- Write. Existing people keep their id and their ship if it is higher.
    existing = fetch_all("pursuit_people",
                         "id,email,phone,pco_person_id,ship,pinned_by,pinned_at,state,deceased")
    by_email = {e["email"]: e for e in existing if e.get("email")}
    by_phone = {e["phone"]: e for e in existing if e.get("phone")}
    by_pco = {e["pco_person_id"]: e for e in existing if e.get("pco_person_id")}

    inserts, updates = [], []
    for p in reg.people:
        prior = (by_pco.get(p.get("pco_person_id"))
                 or by_email.get(p.get("email"))
                 or by_phone.get(p.get("phone")))
        row = {k: v for k, v in p.items() if v is not None}
        row["updated_at"] = now.isoformat()
        if prior:
            if prior.get("pinned_by"):
                row["ship"] = prior["ship"]     # a human pin beats every rule
                # The pin is also testimony. A human looked at this person and
                # said "here". That beats a stale clock: the serving mirror
                # misses whole teams, and without this a leader PD pinned
                # yesterday can read inactive off a 2022 record date.
                pin_ts = parse_when(prior.get("pinned_at"))
                if pin_ts and pin_ts > (parse_when(row.get("last_signal_at")) or 0):
                    row["last_signal_at"] = _dt.fromtimestamp(pin_ts, tz=_tz.utc).isoformat()
                    row["last_signal_source"] = "pin"
                    pin_age = (now.timestamp() - pin_ts) / DAY
                    if pin_age > 730:
                        row["state"] = "inactive"
                    elif pin_age > 180:
                        row["state"] = "dormant"
                        row["dormant_since"] = _dt.fromtimestamp(
                            pin_ts + 180 * DAY, tz=_tz.utc).isoformat()
                    else:
                        row["state"] = "active"
                        row["dormant_since"] = None
            elif rank(prior["ship"]) > rank(row.get("ship")):
                row["ship"] = prior["ship"]     # never demote
            if prior.get("state") == "archived":
                row["state"] = "archived"       # archive is a human act; the clock keeps out
            row["id"] = prior["id"]
            updates.append(row)
        else:
            inserts.append(row)

    # Two registry people can resolve to the SAME existing row: the roster
    # matched it by PCO id while Growth Track matched it by email, and the
    # registry had no key connecting them. Postgres refuses a batch that
    # touches one row twice (21000), and it is right to: merge them here,
    # fill blanks, keep the furthest ship, and the write is one row again.
    merged: dict[str, dict] = {}
    for row in updates:
        prev = merged.get(row["id"])
        if prev is None:
            merged[row["id"]] = row
            continue
        for k, v in row.items():
            if v is not None and not prev.get(k):
                prev[k] = v
        if rank(row.get("ship")) > rank(prev.get("ship")):
            prev["ship"] = row["ship"]
    if len(merged) < len(updates):
        print(f"  merged {len(updates) - len(merged)} update(s) aimed at the same person.")
    updates = list(merged.values())

    for start in range(0, len(inserts), 500):
        sb.table("pursuit_people").insert(inserts[start:start + 500]).execute()
    for start in range(0, len(updates), 500):
        sb.table("pursuit_people").upsert(updates[start:start + 500], on_conflict="id").execute()
    print()
    print(f"  people: {len(inserts)} new, {len(updates)} updated.")

    # Re-read to get ids for card placement.
    people_rows = fetch_all("pursuit_people", "id,email,phone,pco_person_id")
    id_by_email = {r["email"]: r["id"] for r in people_rows if r.get("email")}
    id_by_phone = {r["phone"]: r["id"] for r in people_rows if r.get("phone")}
    id_by_pco = {r["pco_person_id"]: r["id"] for r in people_rows if r.get("pco_person_id")}

    have_cards = {c["person_id"] for c in fetch_all("pursuit_cards", "person_id")}
    new_cards = []
    for person, card in cards:
        pid = (id_by_pco.get(person.get("pco_person_id"))
               or id_by_email.get(person.get("email"))
               or id_by_phone.get(person.get("phone")))
        if not pid or pid in have_cards:
            continue                       # one live card per person
        have_cards.add(pid)
        row = {k: v for k, v in card.items() if v is not None}
        row["person_id"] = pid
        new_cards.append(row)
    for start in range(0, len(new_cards), 500):
        sb.table("pursuit_cards").insert(new_cards[start:start + 500]).execute()
    print(f"  cards: {len(new_cards)} placed.")

    # Same-name pairs, for the merge queue. Never merged by a job.
    pairs, seen_pairs = [], set()
    for a, b in reg.same_name_pairs:
        ida = (id_by_pco.get(a.get("pco_person_id")) or id_by_email.get(a.get("email"))
               or id_by_phone.get(a.get("phone")))
        idb = (id_by_pco.get(b.get("pco_person_id")) or id_by_email.get(b.get("email"))
               or id_by_phone.get(b.get("phone")))
        if ida and idb and ida != idb:
            key = frozenset((ida, idb))
            if key in seen_pairs:
                continue          # the same twins can surface from two sources
            seen_pairs.add(key)
            pairs.append({"person_id": ida, "other_person_id": idb,
                          "evidence": {"matched_on": "display_name"},
                          "confidence": 0.30})
    if pairs:
        sb.table("pursuit_merge_candidates").upsert(
            pairs, on_conflict="person_id,other_person_id").execute()
    print(f"  merge candidates: {len(pairs)} awaiting a human.")
    print()
    print("Done. The board has its people.")


if __name__ == "__main__":
    main()
