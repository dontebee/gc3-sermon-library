"""
GC3 Exemplar Reading Pass — Stage 1: mechanical extraction over both corpora.

Reads `exemplar_sermons` (outside preachers) and `sermons` (PD), runs every
extractor in reading_pass_extract.py over each body, and writes one row per
sermon to `sermon_reading_pass`. Writes nowhere else — `sermons` and
`exemplar_sermons` are read-only here, same as the hard rule in the spec.

No scores. No verdicts. Stage 2 (PD + Claude reading 20 sermons closely) is
where judgment happens; this only gathers evidence for that read.

    python3 sermon_reading_pass.py --survey
    python3 sermon_reading_pass.py --source exemplar --limit 5 --sql-out sample.sql
    python3 sermon_reading_pass.py --apply

Dry run is the default, same as exemplar_ingest.py. --apply writes over the
network, which this repo's sandbox does not have — see
.github/workflows/sermon_reading_pass.yml, which does.
"""
import argparse
import json
import sys

import gc3_env
import reading_pass_extract as X


def _rest_headers():
    key = gc3_env.service_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def fetch_exemplar_rows(limit=None):
    """[{id, preacher, title, preached_date, body, source_type}, ...]

    Only calibration_eligible rows: the spec's own corpus description groups
    "Multiple speakers" (26 rows) as unattributed and excluded from
    per-preacher rollups. calibration_eligible=false is exactly that flag —
    curated by a person for this same reason (panel/interview/co-preached),
    so this pass respects it rather than re-deriving it from the title.
    """
    import requests
    url = gc3_env.supabase_url() + "/rest/v1/exemplar_sermons"
    headers = _rest_headers()
    rows, offset, page = [], 0, 1000
    while True:
        # Offset pagination via the Range header (PostgREST convention).
        resp_headers = {**headers, "Range-Unit": "items", "Range": f"{offset}-{offset + page - 1}"}
        r = requests.get(url, headers=resp_headers, params={
            "select": "id,preacher,title,preached_date,body,source_type,calibration_eligible",
            "calibration_eligible": "eq.true",
            "order": "id.asc",
        }, timeout=120)
        if r.status_code >= 300:
            raise SystemExit(f"ERROR: could not read exemplar_sermons ({r.status_code}): {r.text[:400]}")
        chunk = r.json()
        rows.extend(chunk)
        if len(chunk) < page or (limit and len(rows) >= limit):
            break
        offset += page
    return rows[:limit] if limit else rows


def fetch_pd_rows(limit=None):
    """[{id, title, preached_date, speaker, body, source_type?}, ...]

    schema.sql in this repo (the checked-in copy) predates source_type and
    embedding on `sermons` — CLAUDE.md says both exist on the live table.
    Ask for source_type; if the live column set doesn't have it, retry
    without rather than failing the whole pass over one field.
    """
    import requests
    url = gc3_env.supabase_url() + "/rest/v1/sermons"
    headers = _rest_headers()
    select_with = "id,title,preached_date,speaker,body,source_type"
    select_without = "id,title,preached_date,speaker,body"
    select = select_with
    rows, offset, page = [], 0, 1000
    while True:
        r = requests.get(url, headers={**headers, "Range-Unit": "items",
                                        "Range": f"{offset}-{offset + page - 1}"},
                          params={"select": select, "order": "id.asc"}, timeout=120)
        if r.status_code == 400 and select == select_with:
            print("NOTE: sermons has no source_type column reachable via this key; "
                  "continuing without it.")
            select = select_without
            continue
        if r.status_code >= 300:
            raise SystemExit(f"ERROR: could not read sermons ({r.status_code}): {r.text[:400]}")
        chunk = r.json()
        rows.extend(chunk)
        if len(chunk) < page or (limit and len(rows) >= limit):
            break
        offset += page
    return rows[:limit] if limit else rows


def build_record(source, row):
    body = (row.get("body") or "").strip()
    extracted = X.extract(body)
    return {
        "source": source,
        "source_id": row["id"],
        "preacher": row.get("preacher") or row.get("speaker") or "PD",
        "source_type": row.get("source_type"),
        "sermon_date": row.get("preached_date"),
        "title": row.get("title"),
        **extracted,
    }


def build_all(sources, limit=None):
    records, skipped_empty = [], 0
    if "exemplar" in sources:
        for row in fetch_exemplar_rows(limit):
            if not (row.get("body") or "").strip():
                skipped_empty += 1
                continue
            records.append(build_record("exemplar", row))
    if "pd" in sources:
        for row in fetch_pd_rows(limit):
            if not (row.get("body") or "").strip():
                skipped_empty += 1
                continue
            records.append(build_record("pd", row))
    return records, skipped_empty


def survey(sources):
    for src in sources:
        rows = fetch_exemplar_rows() if src == "exemplar" else fetch_pd_rows()
        with_body = [r for r in rows if (r.get("body") or "").strip()]
        lens = [len(r["body"]) for r in with_body]
        print(f"{src}: {len(rows)} rows, {len(with_body)} with a body, "
              f"{len(rows) - len(with_body)} empty. "
              f"avg {round(sum(lens) / len(lens)) if lens else 0} chars, "
              f"min {min(lens) if lens else 0}, max {max(lens) if lens else 0}.")


def report(records, skipped_empty):
    by_source = {}
    for r in records:
        by_source.setdefault(r["source"], []).append(r)
    print(f"\n{len(records)} sermons extracted, {skipped_empty} skipped (empty body).")
    for src, rs in by_source.items():
        n_claim_marker = sum(1 for r in rs if r["governing_claim"].get("confidence") == "marker")
        n_tension_found = sum(1 for r in rs if r["tension"].get("confidence") == "marker")
        avg_scripture = sum(len(r["scripture_refs"]) for r in rs) / len(rs)
        avg_devices = sum(len(r["devices"]) for r in rs) / len(rs)
        print(f"  {src}: {len(rs)} sermons. governing claim found by marker in "
              f"{n_claim_marker}/{len(rs)}; tension marker found in {n_tension_found}/{len(rs)}; "
              f"avg {avg_scripture:.1f} scripture refs, avg {avg_devices:.1f} devices/sermon.")


def sql_literal(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def write_sql(records, path):
    cols = ["source", "source_id", "preacher", "source_type", "sermon_date", "title",
            "char_len", "governing_claim", "tension", "target_questions", "relief_points",
            "scripture_refs", "devices", "repeated_lines", "ending", "leak_candidates",
            "orality_markers", "structural_map", "extractor_version"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"-- {len(records)} rows for sermon_reading_pass. Idempotent: re-running\n")
        f.write("-- the extractor and re-applying just updates these rows in place.\n")
        for r in records:
            values = ", ".join(sql_literal(r[c]) for c in cols)
            f.write(f"insert into sermon_reading_pass ({', '.join(cols)}) values ({values})\n")
            f.write("  on conflict (source, source_id) do update set\n")
            f.write("    " + ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("source", "source_id")))
            f.write(";\n")
    print(f"Wrote {len(records)} rows to {path}.")


def write_rows(records, batch_size=10):
    import requests
    url = gc3_env.supabase_url() + "/rest/v1/sermon_reading_pass"
    headers = {**_rest_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    written = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        resp = requests.post(url, headers=headers, params={"on_conflict": "source,source_id"},
                              data=json.dumps(batch), timeout=180)
        if resp.status_code >= 300:
            raise SystemExit(f"ERROR: insert failed ({resp.status_code}): {resp.text[:400]}")
        written += len(batch)
        print(f"  ... {written}/{len(records)}", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["exemplar", "pd", "both"], default="both")
    ap.add_argument("--limit", type=int, default=None, help="cap rows per corpus, for testing")
    ap.add_argument("--survey", action="store_true", help="report corpus sizes, write nothing")
    ap.add_argument("--sql-out", default=None, help="emit SQL instead of inserting")
    ap.add_argument("--apply", action="store_true", help="write to Supabase (default is a dry run)")
    args = ap.parse_args()

    sources = ["exemplar", "pd"] if args.source == "both" else [args.source]

    if args.survey:
        survey(sources)
        return

    records, skipped_empty = build_all(sources, args.limit)
    report(records, skipped_empty)

    if args.sql_out:
        write_sql(records, args.sql_out)
        return
    if not args.apply:
        print("\nDRY RUN. Nothing written. Pass --apply to write, or --sql-out to emit SQL.")
        return
    written = write_rows(records)
    print(f"\nWrote {written} rows.")


if __name__ == "__main__":
    main()
