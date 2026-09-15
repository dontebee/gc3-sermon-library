# The exemplar corpus

CSV transcripts of outside preachers, held as litmus tests for the sermon
grading engine. If the grader scores an acknowledged great sermon poorly, the
rubric is wrong, not the sermon.

They are not PD's material and they live in `exemplar_sermons`, never in
`sermons`. Schema and the reason why: `supabase/exemplar_schema.sql`.

## Running it

Dry run is the default. It reads the file, applies the skip rules and prints
the report. Nothing is written.

    python3 exemplar_ingest.py --file elevation_church_sermons.csv \
        --preacher "Steven Furtick" --ministry "Elevation Church"

Add `--apply` to write. `--survey` prints what a file holds without needing a
preacher, which is the thing to run first on a file nobody has looked at.

`--verify-out FILE` writes a query that checks what landed against the CSV it
came from. Run it after any load. It returns nothing when every sermon is
whole, and names the row when one is missing or short. Worth the habit: a
transcript that arrives truncated still looks like a sermon, so length is the
only thing that catches it.

`--preacher` and `--ministry` are set by the operator on the command line.
They are never inferred from the transcript, and the survey below is why.

## What is actually in the Drive folder

`GC3-Sermon-Transcripts - Exemplar`, surveyed 2026-09-15. Thirteen CSVs.
Three of them hold usable outside preaching. The filenames are not reliable.

**Usable exemplars**

| file | rows | usable | preacher |
|---|---|---|---|
| `elevation_church_sermons.csv` | 338 | 124 | Steven Furtick, Elevation Church |
| `dharius_daniels_sermons.csv` | — | — | Dharius Daniels, Change Church |
| `bishop_td_jakes_sermons.csv` | — | — | T.D. Jakes, The Potter's House |

**PD's own preaching. Never goes in this table.**

- `long_videos_with_transcripts.csv` — PD's sermons, despite being cited in
  the ingest spec as the exemplar column shape. The first row is
  "Pastor Donte Banks". This is the trap the operator-sets-the-preacher rule
  exists to catch.
- `all_transcripts.csv` — GodChasers Church
- `godchasers_sermons.csv` — GodChasers, and has no transcript column at all
- `growthtrack_master.csv` — GrowthTrack lessons

**Failed scrapes. Zero usable transcripts; the transcript column holds the
scraper's error text.**

- `elevation_steven_furtick_sermons.csv` — "An unexpected error occurred: ..."
- `fetch_furtick_sermons.csv` — "Error fetching transcript: ..."
- `fetch_elevation_church.csv` — "yt-dlp not installed"
- `fetch_bishop_td_jakes.csv` — "yt-dlp not installed"
- `fetch_bishop_td_jakes_sermons.csv` — header only, no rows
- `fetch_long_sermons.csv` — transcript column empty, and it mixes three
  preachers plus GodChasers in one file

The ingest skips these with the reason "scraper error, not a transcript"
rather than "too short", so the skip list says something useful.

## Skip rules

A row is not inserted if the body is empty, is under 2,000 characters, is a
scraper error, or the title contains `Worship`, `Live Stream`, `Full Service`,
`(Official` or `Music Video`. Every skip is logged with its title and reason.

## Body cleanup

Light touch. `[Music]`, `[Applause]` and `[Laughter]` come out, runs of
whitespace collapse, and the words are left exactly as delivered. No
punctuation, no capitalisation, no improving: the grader scores repetition and
cadence, so it needs the real thing, warts included.

## Two limits worth knowing before you start

**The Drive connector will not download a file over 10 MB.**
`bishop_td_jakes_sermons.csv` is 14 MB, so it cannot be pulled through an
agent session. Run the ingest somewhere the file is local, or split it.

**A sandboxed session has no egress to the Supabase REST endpoint.** `--apply`
needs a network route to the project URL. A GitHub Actions run has one; a
sandbox may not. `--sql-out FILE` is the fallback: it emits the inserts as SQL
to run wherever a connection exists.

## What this ingest deliberately does not do

No `sermon_extractions`, no `construct_instances`, no `brain_items`, no 10T
extraction, no embeddings, and nothing in `sermons` is read, written or
touched. Those are separate decisions, after PD sees the load.
