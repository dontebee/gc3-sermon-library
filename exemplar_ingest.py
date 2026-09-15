"""
Load outside preachers' transcripts into exemplar_sermons.

These are litmus-test exemplars for the sermon grading engine: known-great
preaching the rubric can be measured against. They are NOT PD's material.

They go in their own table, never in `sermons`. `sermons` carries an fts
tsvector and an embedding, and every ranked and semantic search over the
corpus walks it. A thousand Furtick sermons in there pollutes every future
rank and every nearest-neighbour hit, and no `where speaker = 'PD'` bolted on
afterwards un-pollutes a similarity search that already ran.

The table has no `speaker` column on purpose. It is `preacher`, so a query
copy-pasted from a `sermons` query fails loudly instead of quietly answering
about the wrong corpus.

`preacher` and `ministry` are set per file by the operator, on the command
line. They are never inferred from the transcript, because the CSVs in the
Drive folder are not all what their filenames suggest: several are failed
scrapes, several mix preachers, and four of them are PD's own preaching.
--survey prints what a file actually holds before anything is written.

Dry run is the default. Pass --apply to write.
"""
import argparse
import base64
import csv
import json
import os
import re
import statistics
import sys
import urllib.parse
from collections import Counter

import gc3_env

csv.field_size_limit(sys.maxsize)

MIN_BODY_CHARS = 2000

# Clips, trailers, promos and music, by title.
TITLE_SKIP_PATTERNS = [
    "worship",
    "live stream",
    "full service",
    "(official",
    "music video",
]

# A scraper that failed still wrote a row. The transcript column holds its
# error text. Length alone would catch these, but "scraper error" tells PD
# something different from "too short" when he reads the skip list.
SCRAPER_ERROR_MARKERS = [
    "yt-dlp not installed",
    "error fetching transcript",
    "an unexpected error occurred",
    "no transcript available",
    "transcripts disabled",
    "sign in to confirm",
]

BRACKET_MARKERS = re.compile(r"\[\s*(music|applause|laughter)\s*\]", re.IGNORECASE)

# Header spellings seen across the CSVs in the Drive folder. Compared after
# lowercasing and dropping everything that is not a letter or digit.
COLUMN_ALIASES = {
    "title": ("title", "sermonname", "videotitle"),
    "url": ("videourl", "url", "link"),
    "published": ("datepublished", "publishdate", "publisheddate", "uploaddate"),
    "duration_mins": ("durationmins", "duration"),
    "duration_seconds": ("durationseconds",),
    "transcript": ("transcript", "transcripttext", "body"),
    "video_id": ("videoid",),
}


def _norm(header):
    return re.sub(r"[^a-z0-9]", "", (header or "").lower())


def map_columns(fieldnames):
    """Match this file's headers onto the fields we need. Never assume."""
    found = {}
    for raw in fieldnames or []:
        n = _norm(raw)
        for field, aliases in COLUMN_ALIASES.items():
            if n in aliases and field not in found:
                found[field] = raw
    return found


def video_id_from_url(url):
    if not url:
        return None
    try:
        parts = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    if parts.netloc.endswith("youtu.be"):
        vid = parts.path.lstrip("/").split("/")[0]
        return vid or None
    qs = urllib.parse.parse_qs(parts.query)
    vid = (qs.get("v") or [None])[0]
    if vid:
        return vid
    m = re.search(r"/(?:embed|shorts|live)/([A-Za-z0-9_-]{6,})", parts.path)
    return m.group(1) if m else None


def clean_body(text):
    """Auto-captions, lightly.

    Strip the bracket markers, collapse whitespace, leave the words alone.
    No punctuation, no capitalisation, no improving. The grader scores
    repetition and cadence, so it needs what was actually said.
    """
    if not text:
        return ""
    text = BRACKET_MARKERS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_published(value):
    """Return (timestamptz string, date string). ISO in, ISO out."""
    if not value:
        return None, None
    v = value.strip()
    if not v:
        return None, None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return v, m.group(0)
    # 01/30/2024
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", v)
    if m:
        d = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        return d, d
    # 20240130
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", v)
    if m:
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return d, d
    return None, None


def parse_duration_seconds(row, cols):
    if "duration_seconds" in cols:
        raw = (row.get(cols["duration_seconds"]) or "").strip()
        if raw:
            try:
                return int(float(raw))
            except ValueError:
                pass
    if "duration_mins" in cols:
        raw = (row.get(cols["duration_mins"]) or "").strip()
        if not raw:
            return None
        # Either 58.9 or 12:46.
        if ":" in raw:
            bits = raw.split(":")
            try:
                bits = [int(b) for b in bits]
            except ValueError:
                return None
            secs = 0
            for b in bits:
                secs = secs * 60 + b
            return secs
        try:
            return int(round(float(raw) * 60))
        except ValueError:
            return None
    return None


def skip_reason(title, body):
    if not body:
        return "empty transcript"
    low_body = body[:400].lower()
    for marker in SCRAPER_ERROR_MARKERS:
        if marker in low_body:
            return "scraper error, not a transcript"
    low_title = (title or "").lower()
    for pattern in TITLE_SKIP_PATTERNS:
        if pattern in low_title:
            return f"title matches {pattern!r}"
    if len(body) < MIN_BODY_CHARS:
        return f"body under {MIN_BODY_CHARS} chars"
    return None


def read_rows(path):
    """Yield raw dict rows, whatever this file's header shape turns out to be."""
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh)
        cols = map_columns(reader.fieldnames)
        missing = [f for f in ("title", "transcript") if f not in cols]
        if missing:
            raise SystemExit(
                f"ERROR: {os.path.basename(path)} has no {', '.join(missing)} column.\n"
                f"Headers found: {reader.fieldnames}"
            )
        for row in reader:
            yield row, cols


def build_records(path, preacher, ministry, source_file):
    kept, skipped, seen = [], [], set()
    dupes_in_file = 0
    total = 0
    for row, cols in read_rows(path):
        total += 1
        title = (row.get(cols["title"]) or "").strip()
        body = clean_body(row.get(cols["transcript"]))
        reason = skip_reason(title, body)
        if reason:
            skipped.append((title or "(untitled)", reason))
            continue
        url = (row.get(cols["url"]) or "").strip() if "url" in cols else ""
        vid = None
        if "video_id" in cols:
            vid = (row.get(cols["video_id"]) or "").strip() or None
        vid = vid or video_id_from_url(url)
        published_ts, published_date = parse_published(
            row.get(cols["published"]) if "published" in cols else None
        )
        key = (preacher, vid or title)
        if key in seen:
            dupes_in_file += 1
            continue
        seen.add(key)
        kept.append(
            {
                "preacher": preacher,
                "ministry": ministry,
                "title": title,
                "preached_date": published_date,
                "date_published": published_ts,
                "duration_seconds": parse_duration_seconds(row, cols),
                "source_url": url or None,
                "source_video_id": vid,
                "source_type": "transcript",
                "source_file": source_file,
                "body": body,
            }
        )
    return kept, skipped, dupes_in_file, total


# Titles on these channels name their preacher, which is how we can tell a
# single-preacher file from a mixed one without reading any transcript.
KNOWN_PREACHERS = [
    ("Steven Furtick", ("furtick",)),
    ("T.D. Jakes", ("t.d. jakes", "td jakes", "bishop jakes")),
    ("Sarah Jakes Roberts", ("sarah jakes",)),
    ("Dharius Daniels", ("dharius", "darius daniels")),
    ("Conway Edwards", ("conway edwards",)),
    ("Donte Banks (PD)", ("donte banks", "godchasers")),
]


def survey(path):
    """What does this file actually hold? Printed before anything is written."""
    counts = Counter()
    rows = 0
    with_body = 0
    for row, cols in read_rows(path):
        rows += 1
        title = (row.get(cols["title"]) or "")
        body = clean_body(row.get(cols["transcript"]))
        if body and not skip_reason(title, body):
            with_body += 1
        low = title.lower()
        hit = None
        for name, needles in KNOWN_PREACHERS:
            if any(n in low for n in needles):
                hit = name
                break
        counts[hit or "unattributed in title"] += 1
    print(f"File: {os.path.basename(path)}")
    print(f"Rows: {rows}")
    print(f"Rows with a usable transcript: {with_body}")
    print("Preacher named in title:")
    for name, n in counts.most_common():
        print(f"  {n:5d}  {name}")


def report(source_file, preacher, total, kept, skipped, dupes):
    print(f"File: {source_file}")
    print(f"Preacher: {preacher}")
    print(f"Rows read: {total}")
    print(f"Inserted: {len(kept)}")
    print(f"Skipped: {len(skipped)}")
    for reason, n in Counter(r for _, r in skipped).most_common():
        print(f"  {n:5d}  {reason}")
    print(f"Duplicates blocked: {dupes}")
    dates = sorted(r["preached_date"] for r in kept if r["preached_date"])
    print(f"Date range: {dates[0]} to {dates[-1]}" if dates else "Date range: none")
    lengths = [len(r["body"]) for r in kept]
    med = int(statistics.median(lengths)) if lengths else 0
    print(f"Median body length: {med} chars")


def write_rows(records, batch_size=25):
    """Insert through the Supabase REST endpoint.

    Needs egress to the project URL, which a GitHub Actions run has and a
    sandbox may not. --sql-out is the fallback.
    """
    import requests

    url = gc3_env.supabase_url() + "/rest/v1/exemplar_sermons"
    key = gc3_env.service_key()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # The unique index is the dedupe; a repeat run should be a no-op.
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }
    written = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        resp = requests.post(url, headers=headers, data=json.dumps(batch), timeout=120)
        if resp.status_code >= 300:
            raise SystemExit(f"ERROR: insert failed ({resp.status_code}): {resp.text[:400]}")
        written += len(batch)
        print(f"  ... {written}/{len(records)}", flush=True)
    return written


def sql_literal(value):
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def write_sql(records, path, batch_size=5):
    """Emit the inserts as SQL, for running where REST egress is not available."""
    cols = [
        "preacher", "ministry", "title", "preached_date", "date_published",
        "duration_seconds", "source_url", "source_video_id", "source_type",
        "source_file", "body",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            values = ",\n".join(
                "(" + ", ".join(sql_literal(r[c]) for c in cols) + ")" for r in batch
            )
            fh.write(
                f"insert into exemplar_sermons ({', '.join(cols)}) values\n{values}\n"
                "on conflict do nothing;\n"
            )
    print(f"Wrote {len(records)} rows of SQL to {path}")


def write_verify_sql(records, path):
    """Emit a query that checks what landed against what was read.

    Any transport can truncate. A body that arrives short is the failure that
    would otherwise go unnoticed, because a short sermon still looks like a
    sermon. This compares every row's length against the source CSV and
    returns only the rows that disagree, so a clean run prints nothing.
    """
    pairs = ",\n    ".join(
        f"({sql_literal(r['source_video_id'] or r['title'])}, {len(r['body'])})"
        for r in records
    )
    query = f"""with expected (key, chars) as (values
    {pairs}
)
select e.key,
       e.chars as expected_chars,
       length(x.body) as actual_chars,
       case when x.id is null then 'missing' else 'truncated or altered' end as problem
from expected e
left join exemplar_sermons x
  on coalesce(x.source_video_id, x.title) = e.key
 and x.preacher = {sql_literal(records[0]['preacher']) if records else "''"}
where x.id is null or length(x.body) <> e.chars
order by e.key;
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(query)
    print(f"Wrote a verification query for {len(records)} rows to {path}")
    print("It returns zero rows when every sermon landed whole.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True, help="path to the CSV")
    ap.add_argument("--preacher", help="set by the operator, never inferred")
    ap.add_argument("--ministry", default=None)
    ap.add_argument("--source-file", default=None, help="audit trail; defaults to the basename")
    ap.add_argument("--survey", action="store_true", help="report what the file holds, write nothing")
    ap.add_argument("--apply", action="store_true", help="write to Supabase (default is a dry run)")
    ap.add_argument("--sql-out", default=None, help="emit SQL instead of inserting")
    ap.add_argument("--verify-out", default=None,
                    help="emit a query that checks what landed against this CSV")
    args = ap.parse_args()

    if args.survey:
        survey(args.file)
        return

    if not args.preacher:
        raise SystemExit("ERROR: --preacher is required. It is set per file by the operator.")

    source_file = args.source_file or os.path.basename(args.file)
    kept, skipped, dupes, total = build_records(
        args.file, args.preacher, args.ministry, source_file
    )
    report(source_file, args.preacher, total, kept, skipped, dupes)

    if args.verify_out:
        write_verify_sql(kept, args.verify_out)
        return
    if args.sql_out:
        write_sql(kept, args.sql_out)
        return
    if not args.apply:
        print("\nDRY RUN. Nothing written. Pass --apply to write.")
        return
    written = write_rows(kept)
    print(f"\nWrote {written} rows.")


if __name__ == "__main__":
    main()
