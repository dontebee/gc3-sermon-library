"""Weekly: add new GodChasers sermons to Supabase, fully analyzed on the way in.

Pulls the most recent uploads AND live streams, keeps only public videos at or
above MIN_DURATION_SECONDS whose titles do not contain music or promo keywords,
skips any already in the database, downloads English auto-captions only (no
media), cleans them, then runs an AI analysis (scriptures, big idea, themes,
quotes, word studies, frameworks, series) before inserting. New sermons land
with verified=false for review, but already enriched.

Env vars:
  SUPABASE_URL, SUPABASE_SERVICE_KEY   the database
  ANTHROPIC_API_KEY                     the analysis (required for enrichment)
Optional: YT_COOKIES (path to a cookies.txt file) if YouTube throttles the host.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

import gc3_env

# Titles often contain emoji (e.g. the red live dot). Make stdout UTF-8 safe so a
# print never crashes the run on Windows consoles that default to cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CHANNEL = "https://www.youtube.com/@godchaserschurch"
TABS = ["/videos", "/streams"]  # regular uploads AND past live streams
RECENT_LIMIT = 12
MIN_DURATION_SECONDS = 1200  # 20 minutes. The supervised backfill used 600 (10 min).
EXCLUDE_KEYWORDS = ["official video", "lyric", "worship", "cover",
                    "trailer", "promo", "behind the scenes"]
ENRICH_MODEL = "claude-sonnet-4-6"  # strong + cost-effective for extraction. Change to
# "claude-haiku-4-5" for cheaper, or "claude-opus-4-8" for maximum depth.

SUPABASE_URL = gc3_env.supabase_url()
SUPABASE_SERVICE_KEY = gc3_env.service_key()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY is not set. New sermons will be saved WITHOUT")
    print("analysis (no scriptures, themes, word studies, or frameworks). Set the key")
    print("to enrich on pull. The sermon body is still captured and searchable.")

try:
    from supabase import create_client
except ImportError:
    print("ERROR: 'supabase' not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
COOKIES = os.environ.get("YT_COOKIES")

ANALYSIS_TOOL = {
    "name": "save_analysis",
    "description": "Save the structured analysis of one sermon transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "series": {"type": "string", "description": "The sermon series name if the title clearly indicates one (e.g. '#MMM' = Monday Morning Manna, 'AFUERA (Week 2)' = AFUERA). Empty string if standalone or unclear."},
            "big_idea": {"type": "string", "description": "ONE sentence (max 25 words) capturing the central message."},
            "scriptures": {"type": "array", "items": {"type": "string"}, "description": "Bible passages actually taught from or quoted, e.g. 'John 21:15-17'. Best 1 to 6. Empty if none."},
            "themes": {"type": "array", "items": {"type": "string"}, "description": "3 to 6 lowercase keyword tags."},
            "quotes": {"type": "array", "items": {"type": "string"}, "description": "1 to 3 short verbatim standout quotes from the preacher, each max 30 words."},
            "word_studies": {"type": "array", "items": {"type": "object", "properties": {
                "term": {"type": "string"}, "language": {"type": "string"}, "gloss": {"type": "string"},
                "usage": {"type": "string"}, "quote": {"type": "string"}}, "required": ["term", "language", "gloss", "usage", "quote"]},
                "description": "Only when the preacher explicitly teaches a Greek or Hebrew word's meaning. Empty array otherwise."},
            "frameworks": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "description": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["name", "description", "quote"]},
                "description": "Only for a named or clearly structured repeatable teaching device (named concepts, memorable contrasts like 'X vs Y', acronyms). Not generic three-point outlines. Empty array otherwise."},
        },
        "required": ["series", "big_idea", "scriptures", "themes", "quotes", "word_studies", "frameworks"],
    },
}


def enrich(title, body):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = ("You are analyzing a sermon by Pastor Donte Banks. The transcript is from "
                  "auto-captions (unpunctuated). Extract the structured analysis and call the "
                  "save_analysis tool. Auto-captions garble Greek and Hebrew words; give your best "
                  f"transliteration.\n\nTITLE: {title}\n\nTRANSCRIPT:\n{body[:80000]}")
        msg = client.messages.create(
            model=ENRICH_MODEL, max_tokens=2000, tools=[ANALYSIS_TOOL],
            tool_choice={"type": "tool", "name": "save_analysis"},
            messages=[{"role": "user", "content": prompt}])
        for b in msg.content:
            if b.type == "tool_use":
                return b.input
    except Exception as e:
        print("  enrichment failed:", repr(e))
    return None


def yt(args):
    base = ["yt-dlp", "--ignore-errors", "--retries", "3"]
    if COOKIES:
        base += ["--cookies", COOKIES]
    try:
        return subprocess.run(base + args, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        print("ERROR: yt-dlp is not installed or not on PATH.")
        sys.exit(1)


def recent_videos():
    out, seen = [], set()
    last_stderr = ""
    for tab in TABS:
        res = yt(["--dump-json", "--playlist-end", str(RECENT_LIMIT), CHANNEL + tab])
        last_stderr = res.stderr or last_stderr
        for line in (res.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = d.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(d)
    if not out:
        print("No videos returned from YouTube (checked uploads and live streams).")
        for ln in (last_stderr or "").strip().splitlines()[-3:]:
            print("  yt-dlp:", ln)
    return out


def clean_vtt(path):
    lines = []
    for raw in open(path, encoding="utf-8-sig"):
        ln = raw.strip()
        if not ln or ln.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")):
            continue
        if "-->" in ln:
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if ln:
            lines.append(ln)
    out = []
    for ln in lines:
        if out and (ln == out[-1] or out[-1].endswith(ln)):
            continue
        out.append(ln)
    text = " ".join(out)
    for tag in ("[Music]", "[Applause]", "[Laughter]"):
        text = text.replace(tag, " ")
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    paras, cur, wc = [], [], 0
    for p in parts:
        cur.append(p)
        wc += len(p.split())
        if len(cur) >= 4 or wc >= 120:
            paras.append(" ".join(cur))
            cur, wc = [], 0
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras).strip()


def fetch_captions(video_id, outdir):
    yt(["--skip-download", "--write-auto-subs", "--sub-langs", "en,en-orig",
        "--sub-format", "vtt", "-o", os.path.join(outdir, "%(id)s"),
        f"https://www.youtube.com/watch?v={video_id}"])
    hits = glob.glob(os.path.join(outdir, f"{video_id}*.vtt"))
    return hits[0] if hits else None


def main():
    checked = added = skip_existing = skip_filtered = skip_nocaps = errored = 0
    for d in recent_videos():
        checked += 1
        try:
            vid = d.get("id")
            title = (d.get("title") or "").strip()
            dur = d.get("duration") or 0
            avail = d.get("availability")
            if avail and avail != "public":
                skip_filtered += 1
                continue
            if dur and dur < MIN_DURATION_SECONDS:
                skip_filtered += 1
                continue
            if any(k in title.lower() for k in EXCLUDE_KEYWORDS):
                skip_filtered += 1
                continue
            if sb.table("sermons").select("id").eq("youtube_video_id", vid).execute().data:
                skip_existing += 1
                continue
            with tempfile.TemporaryDirectory() as tmp:
                vtt = fetch_captions(vid, tmp)
                if not vtt:
                    skip_nocaps += 1
                    print("NO CAPTIONS YET:", title)
                    continue
                body = clean_vtt(vtt)

            analysis = enrich(title, body)
            upload = d.get("upload_date")
            iso = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if upload and len(upload) == 8 else None
            row = {
                "youtube_video_id": vid,
                "title": title,
                "preached_date": iso,
                "youtube_url": d.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                "duration_seconds": int(dur) if dur else None,
                "speaker": "PD",
                "verified": False,
                "body": body,
            }
            if analysis:
                row["series"] = (analysis.get("series") or "").strip() or None
                row["big_idea"] = analysis.get("big_idea")
                row["scriptures"] = analysis.get("scriptures") or []
                row["themes"] = analysis.get("themes") or []
                row["quotes"] = analysis.get("quotes") or []

            res = sb.table("sermons").upsert(row, on_conflict="youtube_video_id").execute()
            sermon_id = res.data[0]["id"] if res.data else None

            n_ws = n_fw = 0
            if analysis and sermon_id:
                ws = [{"sermon_id": sermon_id, **{k: w.get(k) for k in ("term", "language", "gloss", "usage", "quote")}}
                      for w in (analysis.get("word_studies") or []) if w.get("term")]
                fw = [{"sermon_id": sermon_id, **{k: f.get(k) for k in ("name", "description", "quote")}}
                      for f in (analysis.get("frameworks") or []) if f.get("name")]
                if ws:
                    sb.table("word_studies").insert(ws).execute()
                if fw:
                    sb.table("frameworks").insert(fw).execute()
                n_ws, n_fw = len(ws), len(fw)

            added += 1
            tag = f"ENRICHED ({n_ws} word studies, {n_fw} frameworks)" if analysis else "RAW (no analysis key)"
            print(f"ADDED [{tag}]:", title)
        except Exception as e:
            errored += 1
            print("ERROR on video:", d.get("id"), repr(e))

    print(f"\nWeekly run complete. checked={checked} added={added} "
          f"skipped_existing={skip_existing} skipped_filtered={skip_filtered} "
          f"skipped_no_captions={skip_nocaps} errored={errored}")

    # A healthy run always lists the channel's recent uploads, so checked is
    # normally RECENT_LIMIT-ish even on a week with nothing new. checked == 0
    # means the listing itself failed (YouTube bot-checking the runner's IP,
    # most likely) - and swallowing that froze the library for three straight
    # weeks in August 2026 while every run reported success. Fail loudly so
    # GitHub emails the owner instead of the calendar quietly going stale.
    if checked == 0:
        print("\nFAILING LOUDLY: YouTube returned nothing, so this run verified nothing.")
        print("Fix options: run `python weekly_update.py` from a residential IP to catch up,")
        print("and/or set the YT_COOKIES secret (see weekly.yml) so the runner can list videos.")
        sys.exit(1)


if __name__ == "__main__":
    main()
