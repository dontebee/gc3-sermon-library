"""
Turn a pasted transcript into one exemplar_sermons row.

Some sermons never come through a scrape. They arrive as text a person
pasted, from a transcript site, in markdown with a timestamp link in front of
every paragraph. That is a legitimate source and it needs the same treatment
as a CSV: the same cleanup, the same skip rules, the same audit trail.

    python3 load_pasted_transcript.py --file touch_me_again.md \
        --preacher "Tolan Morgan" --ministry "Fellowship Bible Baptist Church" \
        --title "Touch Me Again" --video-id rCrkqEeQ98w \
        --sql-out row.sql

Dry run prints the report and writes nothing. --sql-out emits the insert;
--apply writes over the network where there is one.

The operator sets preacher, ministry and title, exactly as in exemplar_ingest.
Nothing is inferred from the words.

A date is only ever what somebody can point to. Pass --preached-date when it
is known and put the evidence in --notes; leave it off otherwise. A null date
is honest, a guessed one is not.
"""
import argparse
import os
import re
import sys

import exemplar_ingest as X

# "* [00:00](https://www.youtube.com/watch?v=ID&t=0) " in front of a paragraph.
TIMESTAMP_LINK = re.compile(r"^\s*\*\s*\[\d{1,2}:\d{2}(?::\d{2})?\]\([^)]*\)\s*")
# The transcript site signs its work at the end; that is not the sermon.
FOOTER = re.compile(r"^\s*Summary for:\s*http", re.IGNORECASE)


def read_pasted(path):
    """Strip the markdown scaffolding, keep every word of the sermon."""
    kept = []
    for line in open(path, encoding="utf-8", errors="replace"):
        if FOOTER.match(line):
            break
        kept.append(TIMESTAMP_LINK.sub("", line))
    return X.clean_body(" ".join(kept))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--preacher", required=True)
    ap.add_argument("--ministry")
    ap.add_argument("--title", required=True)
    ap.add_argument("--video-id")
    ap.add_argument("--preached-date", help="YYYY-MM-DD, only when it is known")
    ap.add_argument("--duration-seconds", type=int)
    ap.add_argument("--notes")
    ap.add_argument("--source-file", help="audit trail; defaults to the basename")
    ap.add_argument("--sql-out")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    body = read_pasted(args.file)
    reason = X.skip_reason(args.title, body)
    if reason:
        sys.exit(f"ERROR: would be skipped ({reason}). Nothing written.")

    row = {
        "preacher": args.preacher,
        "ministry": args.ministry,
        "title": args.title.strip(),
        "preached_date": args.preached_date,
        "date_published": None,
        "duration_seconds": args.duration_seconds,
        "source_url": (f"https://www.youtube.com/watch?v={args.video_id}"
                       if args.video_id else None),
        "source_video_id": args.video_id,
        "source_type": "transcript",
        "source_file": args.source_file or os.path.basename(args.file),
        "body": body,
        "notes": args.notes,
    }

    print(f"Title: {row['title']}")
    print(f"Preacher: {row['preacher']}")
    print(f"Body: {len(body):,} chars")
    print(f"Date: {row['preached_date'] or 'unknown, left null'}")

    if args.sql_out:
        cols = ["preacher", "ministry", "title", "preached_date", "date_published",
                "duration_seconds", "source_url", "source_video_id", "source_type",
                "source_file", "body", "notes"]
        values = ", ".join(X.sql_literal(row[c]) for c in cols)
        with open(args.sql_out, "w", encoding="utf-8") as fh:
            fh.write(f"insert into exemplar_sermons ({', '.join(cols)}) values\n"
                     f"({values})\non conflict do nothing;\n")
        print(f"Wrote SQL to {args.sql_out} ({os.path.getsize(args.sql_out):,} bytes)")
        return
    if args.apply:
        X.write_rows([{k: v for k, v in row.items() if k != "notes"} | {"notes": row["notes"]}])
        print("Wrote 1 row.")
        return
    print("\nDRY RUN. Nothing written.")


if __name__ == "__main__":
    main()
