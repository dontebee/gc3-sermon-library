# Exemplar corpus: finishing the load locally

Hand this to a local Claude Code session, or just run the commands yourself.
Everything here is on branch `claude/gc3-exemplar-corpus-ingest-quw6bt`
(draft PR #36).

## Why this is a handoff

Two limits stop the remote session finishing the job:

1. **The Drive connector refuses files over 10 MB** and times out somewhere
   above ~5.5 MB. `bishop_td_jakes_sermons.csv` (14 MB) is a hard refusal.
   `dharius_daniels_sermons.csv` (8.4 MB) timed out on ten attempts. Neither
   file ever reached the session, so neither could be parsed or loaded.
2. **The sandbox has no network route to Supabase.** `--apply` needs one.
3. **A single tool call cannot carry a whole sermon.** Writing through the
   database tool means the model retypes the insert, and output is capped.
   Measured on this corpus: statements up to ~37,500 characters go through,
   anything larger is silently cut off mid-statement. Postgres rejects the
   fragment, so nothing corrupt is written, but nothing lands either. The
   median Furtick sermon is 42,500 characters, so most of the corpus cannot
   be loaded this way at any batch size. This is not worth retrying.

Locally you have all three. The whole job is three commands.

## State right now

- `exemplar_sermons` exists in `eibrykdamgyoylnqknao`, already migrated.
  Schema and reasoning: `supabase/exemplar_schema.sql`.
- Steven Furtick is **partially loaded** from `elevation_church_sermons.csv`:
  **10 of 124** usable rows (338 rows read). Those 10 are the shortest
  sermons, 26,727 to 37,487 characters, and each has been checked against the
  CSV and is byte-for-byte whole. The other 114 run 37,980 to 62,135
  characters, every one above the ceiling described above, which is why they
  did not land.
- Dharius Daniels: nothing loaded.
- T.D. Jakes: nothing loaded.

**Re-running Furtick is safe and is the intended fix.** The unique index
`exemplar_sermons_dedupe_idx` on `(preacher, coalesce(source_video_id, title))`
plus `on conflict do nothing` makes the load idempotent, so a full local run
fills in whatever is missing and duplicates nothing.

## Before you start

Get the three CSVs onto disk from the Drive folder
`GC3-Sermon-Transcripts - Exemplar`:

- `elevation_church_sermons.csv`
- `dharius_daniels_sermons.csv`
- `bishop_td_jakes_sermons.csv`

Ignore the other ten files in that folder. Four are PD's own preaching and
must never enter this table; six are failed scrapes with no transcripts.
`docs/exemplar-corpus.md` lists them by name.

Export the service key (Doppler project `gc3-intranet`, config `prd`):

    export SUPABASE_SERVICE_ROLE_KEY=...

`requirements.txt` already covers the one dependency (`requests`).

## Step 1 — look before you write

Dry run is the default, so these write nothing. Run each and read the skip
list.

    python3 exemplar_ingest.py --file elevation_church_sermons.csv \
        --preacher "Steven Furtick" --ministry "Elevation Church"

    python3 exemplar_ingest.py --survey --file dharius_daniels_sermons.csv
    python3 exemplar_ingest.py --survey --file bishop_td_jakes_sermons.csv

`--survey` reports how many rows hold a usable transcript and which preacher
each title names. Run it on the two unopened files first — that is how you
find out whether a file holds one preacher or several before you label it.

## Step 2 — decide the labels

The spec is explicit that the operator sets `preacher` and `ministry`, never
the transcript. From video titles these look right, but confirm them:

| file | preacher | ministry |
|---|---|---|
| `elevation_church_sermons.csv` | Steven Furtick | Elevation Church |
| `dharius_daniels_sermons.csv` | Dharius Daniels | Change Church |
| `bishop_td_jakes_sermons.csv` | T.D. Jakes | The Potter's House |

**One open question.** A related Jakes CSV in the same folder mixed in Sarah
Jakes Roberts sermons. If `--survey` shows the same in the big file, a single
`--preacher "T.D. Jakes"` will file her sermons under his name. Either split
the file and load hers as `"Sarah Jakes Roberts"`, or drop those rows. Do not
let one label cover both.

## Step 3 — load

    python3 exemplar_ingest.py --file elevation_church_sermons.csv \
        --preacher "Steven Furtick" --ministry "Elevation Church" --apply

    python3 exemplar_ingest.py --file dharius_daniels_sermons.csv \
        --preacher "Dharius Daniels" --ministry "Change Church" --apply

    python3 exemplar_ingest.py --file bishop_td_jakes_sermons.csv \
        --preacher "T.D. Jakes" --ministry "The Potter's House" --apply

Each prints the report the spec asks for: rows read, inserted, skipped with
reasons grouped, duplicates blocked, date range, median body length.

## Step 4 — prove it landed whole

A transcript that arrives truncated still looks like a sermon. Length is the
only thing that catches it, so check every file you loaded:

    python3 exemplar_ingest.py --file elevation_church_sermons.csv \
        --preacher "Steven Furtick" --verify-out verify_furtick.sql

Run that SQL. **Zero rows is the pass.** Any row it returns is missing or
short, and re-running Step 3 for that file will repair it.

## Step 5 — the contamination check

This is the one that matters. It must return zero.

```sql
select preacher, count(*) as sermons,
       min(preached_date)::text as earliest,
       max(preached_date)::text as latest,
       round(avg(length(body))) as avg_chars
from exemplar_sermons
group by preacher order by sermons desc;

-- must be 0
select count(*) as contamination
from sermons
where speaker in (select distinct preacher from exemplar_sermons);
```

Anything other than zero means an exemplar reached PD's corpus. Stop and say
so.

## Deliberately out of scope

No `sermon_extractions`, no `construct_instances`, no `brain_items`, no 10T
extraction, no embeddings, and nothing in `sermons` read or written. Those are
separate decisions after PD sees the load.

## Worth raising separately

`sermon_desk_rules` has 0 rows, so the grading rubric lives in application
code and is unversioned. The whole point of this corpus is to test that rubric
against known-great preaching, which is harder when the rubric is not a thing
you can version or diff.
