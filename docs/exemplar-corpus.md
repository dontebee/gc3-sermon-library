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

`--labels FILE` relabels listed titles in a file that holds more than one
preacher: a CSV of `title,preacher,ministry,notes`, exact titles. Anything not
listed takes `--preacher`. A labelled title that is not in the file stops the
run, because the row it meant to move would otherwise land under the wrong
name.

Re-running a load is safe. `--apply` reads which sermons are already in the
table and inserts only the rest. (It has to: the dedupe index is on an
expression, which PostgREST's `ignore-duplicates` cannot target, so one
existing row used to fail its whole batch.)

`--preacher` and `--ministry` are set by the operator on the command line.
They are never inferred from the transcript, and the survey below is why.

## What is actually in the Drive folder

`GC3-Sermon-Transcripts - Exemplar`, surveyed 2026-09-15. Thirteen CSVs.
Three of them hold usable outside preaching. The filenames are not reliable.

**Usable exemplars.** Loaded 2026-09-15; 629 rows in `exemplar_sermons`.

| file | loaded | preachers | principal |
|---|---|---|---|
| `bishop_td_jakes_sermons.csv` | 283 | 15 | T.D. Jakes (242) |
| `dharius_daniels_sermons.csv` | 222 | 5 | Dharius Daniels (218) |
| `elevation_church_sermons.csv` | 124 | 1 | Steven Furtick (124) |

Only the Elevation file turned out to hold a single preacher. The other two
are channel dumps: the Jakes file alone carries fifteen, among them Sarah
Jakes Roberts, Cora Jakes and a dozen guest preachers. A single per-file
`--preacher` label would have filed all of them under one name, which is the
whole reason the operator sets it per row when a survey shows a file is
mixed.

Every row was checked byte for byte against its CSV. The labels live in
`exemplar_labels/<file>.csv`:

- Guests go under their own name. `ministry` is where the sermon was preached
  or published, not their home church, because that is what the file shows.
- More than one voice goes under `Multiple speakers`, with the names in
  `notes`. Such a transcript is nobody's cadence, and filing the Furtick
  conversation under either man would skew both.
- `Rightfully Mine!` names no preacher, and the transcript never says who
  it is. It sits under `Unattributed`, with the evidence in `notes`.

The title skip rule also drops some real sermons with "Worship" in the name
(`Worship in the Wilderness: Part 2`, two Daniels Easter services). They are
left out, per the spec.

## What the grader should read

`calibration_eligible` decides it. 603 rows are true, 26 are false.

The 26 are the `Multiple speakers` rows, all in the Jakes file, averaging
about 60,000 characters: panels, interviews, master classes, co-preached
services, `Don't Drop The Mic` conversations. Correctly stored and correctly
attributed; just not one preacher preaching one sermon, which is the only
shape a rubric ceiling can be measured against. Each row's `notes` names the
voices in it.

    select * from exemplar_sermons where calibration_eligible;

The column is curated by a person. The ingest never sets it, because nothing
in a CSV row reliably says how many people are talking.

One row is filed `Unattributed` and is still eligible: `Rightfully Mine!`,
2021-04-11 on The Potter's House channel, one preacher whose name the title
and transcript never give. It is a single sermon, so it is the right shape,
but it cannot serve as a known-great benchmark while nobody knows whose it
is. Worth a decision of its own.

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

## Tolan Morgan: eleven sermons, not yet loaded

Pastor Tolan J. Morgan (Fellowship Bible Baptist Church, "The Ship", Warner
Robins GA) was studied in September 2026: eleven sermons transcribed and read
end to end to build "Tolan Morgan - Preaching Style Reference", which lives in
Drive. The analysis was saved. The transcripts were not.

They are in no Drive folder, no repo and no table. Searched by video id as a
filename, by sermon title, and by "Tolan", "Morgan", "fbbcwarnerrobins",
"Fellowship Bible" and "Warner Robins" in full text; checked `Guest-Speakers`,
`_staging`, `_pipeline-files` and the exemplar folder. Only the reference
comes back.

What survived is the eleven video ids, recorded inside that document.
`fetch_tolan_morgan.py` re-pulls them and writes a CSV in this ingest's own
column shape:

    python3 fetch_tolan_morgan.py
    python3 exemplar_ingest.py --file tolan_morgan_sermons.csv \
        --preacher "Tolan Morgan" --ministry "Fellowship Bible Baptist Church" \
        --apply

Two of the eleven are inside full-service videos and do not start at zero:
Signs of Life at 29:00, How to Stop the Bleeding at 1:38:00. The fetch trims
to the sermon, so neither arrives with an hour of worship in front of it.

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

**Writing through a database tool caps out at about 37,500 characters per
statement.** An agent loading rows that way has to retype each insert, and its
output is capped; past that the statement is cut off mid-text. Postgres
rejects the fragment, so nothing corrupt is stored, but nothing lands either.
Measured against this corpus, that ceiling passes 10 of 124 Furtick sermons.
Load these files from a machine that can reach the database instead.

## What this ingest deliberately does not do

No `sermon_extractions`, no `construct_instances`, no `brain_items`, no 10T
extraction, no embeddings, and nothing in `sermons` is read, written or
touched. Those are separate decisions, after PD sees the load.
