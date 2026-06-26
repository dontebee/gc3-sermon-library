"""Weekly: add new GodChasers sermons to Supabase.

Pulls the most recent uploads, keeps only public videos at or above
MIN_DURATION_SECONDS whose titles do not contain music or promo keywords, skips
any already in the database, downloads English auto-captions only (no media),
cleans them, and inserts a row with verified=false for review.

Env vars: SUPABASE_URL, SUPABASE_SERVICE_KEY
Optional: YT_COOKIES (path to a cookies.txt file) if YouTube throttles the runner.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

# Titles often contain emoji (e.g. the red live dot). Make stdout UTF-8 safe so a
# print never crashes the run on Windows consoles that default to cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CHANNEL = "https://www.youtube.com/@godchaserschurch"
TABS = ["/videos", "/streams"]  # regular uploads AND past live streams (sermons stream live)
RECENT_LIMIT = 12
MIN_DURATION_SECONDS = 1200  # 20 minutes. The supervised backfill used 600 (10 min).
EXCLUDE_KEYWORDS = ["official video", "lyric", "worship", "cover",
                    "trailer", "promo", "behind the scenes"]

# Fail early with a clear message if the secrets are missing or misnamed.
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
missing = [name for name, val in
           (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY))
           if not val]
if missing:
    print("ERROR: missing required secret(s): " + ", ".join(missing))
    print("In the repo: Settings > Secrets and variables > Actions. The names must")
    print("match exactly: SUPABASE_URL and SUPABASE_SERVICE_KEY.")
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("ERROR: the 'supabase' package is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
COOKIES = os.environ.get("YT_COOKIES")


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
    # Check both the uploads tab and the live-streams tab, then dedupe by id.
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
        # Most often this is YouTube blocking the IP of the runner.
        print("No videos returned from YouTube (checked uploads and live streams).")
        print("This usually means the IP was rate-limited or asked to sign in. The run")
        print("is not failed; it will try again next week.")
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
            upload = d.get("upload_date")
            iso = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if upload and len(upload) == 8 else None
            sb.table("sermons").upsert({
                "youtube_video_id": vid,
                "title": title,
                "preached_date": iso,
                "youtube_url": d.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                "duration_seconds": int(dur) if dur else None,
                "speaker": "PD",
                "verified": False,
                "body": body,
            }, on_conflict="youtube_video_id").execute()
            added += 1
            print("ADDED:", title)
        except Exception as e:
            errored += 1
            print("ERROR on video:", d.get("id"), repr(e))

    print(f"\nWeekly run complete. checked={checked} added={added} "
          f"skipped_existing={skip_existing} skipped_filtered={skip_filtered} "
          f"skipped_no_captions={skip_nocaps} errored={errored}")


if __name__ == "__main__":
    main()
