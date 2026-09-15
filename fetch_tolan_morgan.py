"""
Re-pull the eleven Tolan Morgan sermons and write them as an exemplar CSV.

These eleven were transcribed once, in September 2026, and read end to end to
build "Tolan Morgan - Preaching Style Reference". The analysis was saved. The
transcripts were not: they are in no Drive folder, no repo and no table. The
video ids survived inside the reference document, which is what makes this
script possible.

It writes `tolan_morgan_sermons.csv` in the column shape `exemplar_ingest.py`
already reads, so the second step is the same command as every other preacher:

    python3 fetch_tolan_morgan.py
    python3 exemplar_ingest.py --file tolan_morgan_sermons.csv \
        --preacher "Tolan Morgan" --ministry "Fellowship Bible Baptist Church" \
        --apply

Needs yt-dlp and network. Run it somewhere both exist; a sandbox usually has
neither.

Two of the eleven are inside full-service videos, so the sermon does not start
at zero. Those carry a start offset and everything before it is dropped. Take
the offsets as approximate to about a minute, which is how the reference
recorded them.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys

# id, title, scripture, start offset in seconds (None = whole video)
SERMONS = [
    ("Vb4xAhHXTeI", "It's About That Time",      "Acts 16:25-26",     None),
    ("x0M0GI8jQfU", "It's Time to Recover",      "1 Samuel 30:3-19",  None),
    ("rCrkqEeQ98w", "Touch Me Again",            "Mark 8:22-26",      None),
    ("YxLTay9ZWmE", "I'm the One",               "Luke 17:11-19",     None),
    ("_DUPhMY_k9I", "Signs of Life",             "John 20:1-9",       29 * 60),
    ("TO_Pcu1o650", "He's Stretching Me",        "Mark 3:1-6",        None),
    ("S3nRXWHQ1Zw", "Give Me Some Room",         "Genesis 26:12-25",  None),
    ("6iBjzJXPgL4", "How to Stop the Bleeding",  "Mark 5:21-34",      98 * 60),
    ("yQ0xFTL8ZGc", "I've Come Too Far to Quit", "Acts 4:13-22",      None),
    ("SIa65bs3-NQ", "Keep Knocking",             "Acts 12:12-18",     None),
    ("skc_SIxWe5E", "Why Did You Pick a Devil?", "John 6:66-71",      None),
]

OUT = "tolan_morgan_sermons.csv"

TIMESTAMP = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.\d{3}\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.\d{3}"
)
TAGS = re.compile(r"<[^>]+>")


def yt_dlp(args, timeout=180):
    cmd = ["yt-dlp", "--no-warnings", *args]
    cookies = os.environ.get("YT_COOKIES")
    if cookies and os.path.exists(cookies):
        cmd += ["--cookies", cookies]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        sys.exit("ERROR: yt-dlp is not installed.  pip install -U yt-dlp")
    except subprocess.TimeoutExpired:
        return None


def parse_vtt(path, start_offset):
    """VTT to plain text, in order, without the rolling-caption duplication.

    Auto-captions repeat each line as the next one scrolls in, so a naive read
    doubles every sentence. Keeping a cue only when its text differs from the
    last one kept is enough: the duplicates are always adjacent.
    """
    out, last, keep = [], None, True
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        m = TIMESTAMP.match(line)
        if m:
            secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            keep = start_offset is None or secs >= start_offset
            continue
        if not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if not keep:
            continue
        text = TAGS.sub("", line).strip()
        if not text or text == last:
            continue
        out.append(text)
        last = text
    body = " ".join(out)
    body = re.sub(r"\[\s*(music|applause|laughter)\s*\]", " ", body, flags=re.I)
    return re.sub(r"\s+", " ", body).strip()


def fetch(video_id, title, offset, workdir):
    url = f"https://www.youtube.com/watch?v={video_id}"
    meta = yt_dlp(["--skip-download", "--dump-single-json", url])
    if meta is None or meta.returncode != 0:
        err = (meta.stderr or "").strip().splitlines() if meta else ["timed out"]
        return None, f"video unavailable ({err[-1][:70] if err else 'unknown'})"
    info = json.loads(meta.stdout)

    stem = os.path.join(workdir, video_id)
    # Manual captions first; they are cleaner than the machine pass.
    for args in (["--write-sub"], ["--write-auto-sub"]):
        yt_dlp(["--skip-download", *args, "--sub-lang", "en.*", "--sub-format", "vtt",
                "-o", stem + ".%(ext)s", url])
        found = [f for f in os.listdir(workdir)
                 if f.startswith(video_id) and f.endswith(".vtt")]
        if found:
            body = parse_vtt(os.path.join(workdir, found[0]), offset)
            if body:
                return {
                    "Title": title,
                    "Video URL": url,
                    "Duration (mins)": round((info.get("duration") or 0) / 60, 2),
                    "Date Published": info.get("upload_date", ""),
                    "Transcript": body,
                }, None
    return None, "no captions"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workdir", default=".tolan_captions")
    args = ap.parse_args()
    os.makedirs(args.workdir, exist_ok=True)

    rows, failed = [], []
    for vid, title, scripture, offset in SERMONS:
        print(f"  {title} ({vid}) ... ", end="", flush=True)
        row, why = fetch(vid, title, offset, args.workdir)
        if row is None:
            print(why)
            failed.append((title, vid, why))
            continue
        print(f"{len(row['Transcript']):,} chars"
              + (f"  (trimmed to sermon start)" if offset else ""))
        rows.append(row)

    if rows:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    print(f"\nWrote {len(rows)} of {len(SERMONS)} to {args.out}")
    if failed:
        print("Could not fetch:")
        for title, vid, why in failed:
            print(f"  {title} ({vid}): {why}")
        print("\nA video that is gone needs another copy; the rest still load.")
    print(f"\nNext:\n  python3 exemplar_ingest.py --file {args.out} \\\n"
          '      --preacher "Tolan Morgan" --ministry "Fellowship Bible Baptist Church"')
    print("  (add --apply to write)")


if __name__ == "__main__":
    main()
