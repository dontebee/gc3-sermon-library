"""One-time backfill: load a local folder of cleaned .txt transcripts into Supabase.

Each .txt has a header block delimited by lines of "=" signs:

    ============================================================
    Title: ...
    Date: ...
    Series/Playlist: ...
    Speaker: ...
    URL: ...
    Duration: ...
    ============================================================

    <body text>

Env vars:
  SUPABASE_URL               your project URL
  SUPABASE_SERVICE_ROLE_KEY  the service_role key
  TRANSCRIPT_FOLDER          folder of .txt files (searched recursively)

Note: this loads title, date, series, url, duration, speaker, and body. The
richer fields (big_idea, themes, scriptures, word_studies, frameworks) come from
the separate analysis pipeline, not from the transcript headers.
"""
import os
import re
from datetime import datetime
from supabase import create_client

import gc3_env

sb = create_client(gc3_env.supabase_url(), gc3_env.service_key())
FOLDER = os.environ["TRANSCRIPT_FOLDER"]


def parse(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    delims = [i for i, ln in enumerate(lines) if set(ln.strip()) == {"="} and len(ln.strip()) > 5]
    header = lines[delims[0] + 1:delims[1]] if len(delims) >= 2 else []
    body = "\n".join(lines[delims[1] + 1:]).strip() if len(delims) >= 2 else "\n".join(lines).strip()
    h = {}
    for ln in header:
        if ":" in ln:
            k, v = ln.split(":", 1)
            h[k.strip().lower()] = v.strip()
    return h, body


def vid(url):
    m = re.search(r"[?&]v=([\w-]+)", url or "")
    return m.group(1) if m else None


def dur_seconds(s):
    p = (s or "").split(":")
    try:
        if len(p) == 3:
            return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])
        if len(p) == 2:
            return int(p[0]) * 60 + int(p[1])
    except ValueError:
        pass
    return None


def iso_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def main():
    inserted = skipped = failed = 0
    for root, _, files in os.walk(FOLDER):
        for fn in sorted(files):
            if not fn.endswith(".txt"):
                continue
            try:
                h, body = parse(os.path.join(root, fn))
                v = vid(h.get("url"))
                if not v:
                    failed += 1
                    print("NO VIDEO ID:", fn)
                    continue
                if sb.table("sermons").select("id").eq("youtube_video_id", v).execute().data:
                    skipped += 1
                    continue
                sb.table("sermons").upsert({
                    "youtube_video_id": v,
                    "title": h.get("title") or fn,
                    "preached_date": iso_date(h.get("date")),
                    "series": h.get("series/playlist") or h.get("series"),
                    "youtube_url": h.get("url"),
                    "duration_seconds": dur_seconds(h.get("duration")),
                    "speaker": h.get("speaker") or "PD",
                    "verified": True,
                    "body": body,
                }, on_conflict="youtube_video_id").execute()
                inserted += 1
            except Exception as e:
                failed += 1
                print("FAILED:", fn, e)
    print(f"\nBackfill done. inserted={inserted} skipped_existing={skipped} failed={failed}")


if __name__ == "__main__":
    main()
