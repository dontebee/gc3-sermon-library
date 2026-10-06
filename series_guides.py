"""Daily: print each series' Personal Guide and Tribe Guide from GrowthTrack.

GrowthTrack builds a course pack for every sermon (gt_el_lessons.pack): the
memory verse, big idea, Pastor Donte's own words, discussion questions, the
"Living it" steps and a five-day devotional. The booklet is that pack, laid out
for paper. Nothing here writes copy, so the course and the booklet are the same
words. Fix a lesson in GrowthTrack and the next run reprints the guide.

When it runs:
  - a message joins a series (pinned, alias, or untagged inside the window)
  - GrowthTrack rebuilds a pack, or someone edits one (a title fixed by hand)
  - the series' title, sticky line or cover changes
it prints fresh guides and files them on the series in the Studio,
UNPUBLISHED. The guide already on the Sermon Calendar stays up until someone
taps approve; approving the new one retires the old (gc3-intranet,
studio-actions). A draft nobody approved is replaced, not stacked.

A Sunday message that belongs to no series gets its own guide in the Studio
Inbox, to be filed under a series or discarded.

This job sends nothing to anyone. It writes files and Studio rows only.

Env: the Supabase pair (see gc3_env.py). Optional:
  GUIDES_FROM   only series ending on/after this date (default 2026-09-01);
                set earlier to reprint older series from their packs
  DRY_RUN=1     build and save PDFs to ./guides-out, write nothing
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import uuid
from zoneinfo import ZoneInfo

import requests

import gc3_env
from guide_pdf import PERSONAL, TRIBE, Guide

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from supabase import create_client

LAYOUT_VERSION = "1"  # bump to reprint every guide after a layout change
BUCKET = "series-assets"
SITE = "https://www.mygc3.church"
GUIDES_FROM = os.environ.get("GUIDES_FROM") or "2026-09-01"
DRY_RUN = os.environ.get("DRY_RUN") == "1" or "--dry-run" in sys.argv
OUT = "guides-out"

sb = create_client(gc3_env.supabase_url(), gc3_env.service_key())
TODAY = dt.datetime.now(ZoneInfo("America/Chicago")).date()


def d(s):
    return dt.date.fromisoformat(str(s)[:10])


def norm(s):
    s = (s or "").lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", s)).strip()


def service_minutes(service):
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", service or "", re.I)
    if not m:
        return 9999
    h, mi = int(m.group(1)) % 12, int(m.group(2))
    return (h + (12 if (m.group(3) or "").upper() == "PM" else 0)) * 60 + mi


def sunday_on_or_after(day):
    return day + dt.timedelta(days=(6 - day.weekday()) % 7)


def month_span(a, b):
    if (a.year, a.month) == (b.year, b.month):
        return a.strftime("%B %Y")
    if a.year == b.year:
        return f"{a.strftime('%B')} - {b.strftime('%B %Y')}"
    return f"{a.strftime('%B %Y')} - {b.strftime('%B %Y')}"


# ---------- which sermon belongs to which series ----------
# Mirrors gc3-intranet/src/lib/series-match.ts so the guide never disagrees
# with the Sermon Calendar: pin first, then alias inside the window (padded
# three days), then an untagged message inside exactly one series window.

def match(series, alias_to, pin_to, sermon):
    sid = pin_to.get(sermon["id"])
    if sid is not None:
        return sid
    when = d(sermon["preached_date"]) if sermon.get("preached_date") else None
    if when is None:
        return None
    pad = dt.timedelta(days=3)
    by_id = {s["id"]: s for s in series}
    if sermon.get("series"):
        cand = alias_to.get(sermon["series"])
        w = by_id.get(cand)
        if w and d(w["starts_on"]) - pad <= when <= d(w["ends_on"]) + pad:
            return cand
        return None
    inside = [s["id"] for s in series if d(s["starts_on"]) <= when <= d(s["ends_on"])]
    return inside[0] if len(inside) == 1 else None


def verified_quote(pack, body):
    """The first of the lesson's quotes that is word for word in the transcript.
    None if none is: a guide without a pull quote beats one that misquotes."""
    hay = norm(body)
    for b in pack.get("lesson") or []:
        if b.get("kind") == "quote" and b.get("text") and norm(b["text"]) in hay:
            return b["text"]
    return None


def cover_bytes(path):
    if not path:
        return None
    url = path if path.startswith("http") else SITE + path
    try:
        r = requests.get(url, timeout=30)
        return r.content if r.ok else None
    except Exception:
        return None


# ---------- storage and rows ----------

def upload(path, data):
    if DRY_RUN:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, path.replace("/", "__")), "wb") as f:
            f.write(data)
        return
    sb.storage.from_(BUCKET).upload(path, data, {"content-type": "application/pdf"})


def drop_stale_drafts(asset_ids):
    """Remove the last run's drafts if nobody approved them; a published one stays."""
    ids = [i for i in asset_ids if i]
    if not ids or DRY_RUN:
        return
    rows = sb.table("series_assets").select("id, path, published").in_("id", ids).execute().data or []
    stale = [r for r in rows if not r["published"]]
    paths = [r["path"] for r in stale if r.get("path") and not r["path"].startswith("/")]
    if paths:
        sb.storage.from_(BUCKET).remove(paths)
    if stale:
        sb.table("series_assets").delete().in_("id", [r["id"] for r in stale]).execute()


def drop_stale_inbox(inbox_ids):
    if not inbox_ids or DRY_RUN:
        return
    rows = sb.table("studio_inbox").select("id, path").in_("id", inbox_ids).execute().data or []
    if rows:
        sb.storage.from_(BUCKET).remove([r["path"] for r in rows])
        sb.table("studio_inbox").delete().in_("id", [r["id"] for r in rows]).execute()


def checks_for(messages):
    missing = [m["pack"].get("title") for m in messages if not m["quote"]]
    findings = [f"No pull quote on \"{t}\": none of the lesson's quotes matched the transcript word for word."
                for t in missing]
    return {"status": "skipped", "findings": findings,
            "note": "Printed from the GrowthTrack course packs. Approve by eye."}


def pack_hash(pack):
    """What the guide actually prints from. Hashing the content, not
    pack_built_at, means a title or quote fixed by hand in GrowthTrack reprints
    the guide too; a rebuild that changes nothing does not."""
    return hashlib.sha1(json.dumps(pack, sort_keys=True, default=str).encode()).hexdigest()


def signature(parts):
    return hashlib.sha1(json.dumps([LAYOUT_VERSION, parts], sort_keys=True, default=str).encode()).hexdigest()


def message_entry(lesson, sermon, week):
    day = d(lesson["preached_on"])
    return {
        "week": week,
        "date_label": f"{day.strftime('%A').upper()}, {day.strftime('%B').upper()} {day.day}",
        "service": lesson.get("service"),
        "pack": lesson["pack"],
        "quote": verified_quote(lesson["pack"], sermon.get("body") or ""),
    }


# ---------- main ----------

def main():
    series = [s for s in (sb.table("series")
              .select("id, slug, title, sticky_line, anchor_scripture, starts_on, ends_on, status, cover_path")
              .execute().data or []) if s["status"] != "draft"]
    alias_to = {a["alias"]: a["series_id"] for a in
                (sb.table("series_aliases").select("series_id, alias").execute().data or [])}
    pin_to = {p["sermon_id"]: p["series_id"] for p in
              (sb.table("series_pins").select("series_id, sermon_id").execute().data or [])}

    in_scope = [s for s in series if d(s["ends_on"]) >= d(GUIDES_FROM) and d(s["starts_on"]) <= TODAY]
    earliest = min([d(s["starts_on"]) for s in in_scope] + [d(GUIDES_FROM)]) - dt.timedelta(days=3)

    lessons = (sb.table("gt_el_lessons")
               .select("id, sermon_id, service, preached_on, pack, pack_built_at")
               .eq("pack_status", "ready").eq("is_published", True)
               .gte("preached_on", earliest.isoformat())
               .not_.is_("sermon_id", "null").execute().data or [])
    lessons = [l for l in lessons if isinstance(l.get("pack"), dict)]
    ids = sorted({l["sermon_id"] for l in lessons})
    sermons = {}
    for i in range(0, len(ids), 50):
        for s in (sb.table("sermons").select("id, series, preached_date, body")
                  .in_("id", ids[i:i + 50]).execute().data or []):
            sermons[s["id"]] = s

    members, one_offs = {}, []
    for l in lessons:
        s = sermons.get(l["sermon_id"])
        if not s:
            continue
        sid = match(series, alias_to, pin_to, s)
        if sid is None:
            if d(l["preached_on"]).weekday() == 6 and d(l["preached_on"]) >= d(GUIDES_FROM):
                one_offs.append(l)
        else:
            members.setdefault(sid, []).append(l)

    builds = {b["scope"]: b for b in (sb.table("series_guide_builds").select("*").execute().data or [])}
    print(f"{len(in_scope)} series in scope, {len(lessons)} ready packs, {len(one_offs)} one-offs"
          f"{'  [DRY RUN]' if DRY_RUN else ''}")

    for s in in_scope:
        ls = sorted(members.get(s["id"], []), key=lambda l: (l["preached_on"], service_minutes(l.get("service"))))
        if not ls:
            print(f"- {s['title']}: no ready packs yet")
            continue
        running = TODAY <= d(s["ends_on"])
        scope = f"series:{s['id']}"
        sig = signature([[l["sermon_id"], pack_hash(l["pack"])] for l in ls]
                        + [s["title"], s["sticky_line"], s["anchor_scripture"], s["cover_path"], running])
        prev = builds.get(scope)
        if prev and prev["signature"] == sig:
            print(f"- {s['title']}: up to date ({len(ls)} messages)")
            continue

        first = sunday_on_or_after(d(s["starts_on"]))
        msgs = [message_entry(l, sermons[l["sermon_id"]],
                              max(1, (sunday_on_or_after(d(l["preached_on"])) - first).days // 7 + 1)) for l in ls]
        meta = {"title": s["title"], "sticky": s["sticky_line"], "anchor": s["anchor_scripture"],
                "dates": month_span(d(s["starts_on"]), d(s["ends_on"]))}
        art = cover_bytes(s["cover_path"])
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M")
        suffix = " (so far)" if running else ""
        made = {}
        for kind, slugpart, asset_kind in ((PERSONAL, "guide", "guide"), (TRIBE, "tribe-guide", "notes")):
            pdf = Guide(kind, meta, msgs, art, running).build()
            path = f"{s['slug']}/guides/{s['slug']}-{slugpart}-{stamp}.pdf"
            upload(path, pdf)
            made[kind] = {"series_id": s["id"], "kind": asset_kind, "label": f"{kind} (PDF){suffix}",
                          "path": path, "audience": "public", "published": False,
                          "checks": checks_for(msgs), "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        print(f"- {s['title']}: printed {len(msgs)} messages"
              f"{' (replacing an unapproved draft)' if prev else ''}")
        if DRY_RUN:
            continue
        drop_stale_drafts([prev and prev.get("personal_asset_id"), prev and prev.get("tribe_asset_id")])
        rows = sb.table("series_assets").insert([made[PERSONAL], made[TRIBE]]).execute().data
        sb.table("series_guide_builds").upsert({
            "scope": scope, "signature": sig, "sermon_ids": [l["sermon_id"] for l in ls],
            "personal_asset_id": rows[0]["id"], "tribe_asset_id": rows[1]["id"], "inbox_ids": [],
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }).execute()

    for l in one_offs:
        scope = f"sermon:{l['sermon_id']}"
        sig = signature([l["sermon_id"], pack_hash(l["pack"])])
        prev = builds.get(scope)
        title = l["pack"].get("title") or "Message"
        if prev and prev["signature"] == sig:
            print(f"- one-off {title}: up to date")
            continue
        day = d(l["preached_on"])
        meta = {"title": title, "sticky": None, "anchor": l["pack"].get("passage"),
                "dates": f"{day.strftime('%B')} {day.day}, {day.year}"}
        msgs = [message_entry(l, sermons[l["sermon_id"]], None)]
        inbox = []
        for kind, asset_kind in ((PERSONAL, "guide"), (TRIBE, "notes")):
            pdf = Guide(kind, meta, msgs).build()
            fname = re.sub(r"[^\w.\-]+", "_", f"{title} {kind}.pdf")[-80:]
            path = f"inbox/{uuid.uuid4()}-{fname}"
            upload(path, pdf)
            inbox.append({"path": path, "file_name": f"{title} - {kind}.pdf"[:200], "source": "guide-job",
                          "status": "ready", "checks": checks_for(msgs),
                          "suggestion": {"series_slug": None, "kind": asset_kind, "label": f"{title}: {kind} (PDF)",
                                         "audience": "public",
                                         "reason": "Printed from the GrowthTrack lesson for a Sunday message that is "
                                                   "in no series. File it under the series it belongs to, or discard."}})
        print(f"- one-off {title}: printed, waiting in the Studio Inbox")
        if DRY_RUN:
            continue
        drop_stale_inbox(prev.get("inbox_ids") if prev else [])
        rows = sb.table("studio_inbox").insert(inbox).execute().data
        sb.table("series_guide_builds").upsert({
            "scope": scope, "signature": sig, "sermon_ids": [l["sermon_id"]],
            "personal_asset_id": None, "tribe_asset_id": None, "inbox_ids": [r["id"] for r in rows],
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }).execute()


if __name__ == "__main__":
    main()
