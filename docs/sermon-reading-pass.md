# GC3 Exemplar Reading Pass — Stage 1

Spec source: PD, 2026-09-15. This is the build, what it actually does
mechanically, and where it is weaker than the spec's own language
("extract only what is observable") would suggest.

## What this is not

Not a grading run. No scores, no verdicts, nothing that ranks PD against
Jakes or Daniels or Furtick or Tolan Morgan. Stage 1 gathers evidence.
Stage 2 — PD and Claude reading 20 sermons closely — is where anything gets
judged, and it stays a human judgment even then.

## What got built

- `supabase/sermon_reading_pass_schema.sql` — the new table. Never written
  to `sermons` or `exemplar_sermons`; both stay read-only inputs.
- `reading_pass_extract.py` — the extraction functions, pure Python, no
  network. Unit-testable against any string.
- `sermon_reading_pass.py` — the Supabase-facing driver: reads both
  corpora, runs the extractor, writes (or emits SQL for, or just reports).
  Same dry-run-by-default shape as `exemplar_ingest.py`.
- `.github/workflows/sermon_reading_pass.yml` — a `workflow_dispatch` job.
  This sandbox has no egress to Supabase and no service key, same as every
  earlier exemplar-corpus session; the workflow is how this actually runs
  against the live ~1,800 sermons, the same way the nightly jobs do.

## Corpus, as read

- `exemplar_sermons` filtered to `calibration_eligible = true`. That flag
  already excludes the 26 "Multiple speakers" rows and anything else
  curated as the wrong shape for a benchmark — that's what it's for, so
  this pass reads it rather than re-deriving the same exclusion from
  titles.
- `sermons`, all of it, `source_type` carried through unchanged.
  `schema.sql` as checked into this repo predates `source_type` on
  `sermons` (CLAUDE.md says it exists on the live table, alongside
  `embedding`). The reader asks for it and falls back to reading without it
  if the live table doesn't have it — this was written without a live
  connection to confirm the column, so that fallback is deliberate, not
  decorative.

## Applying the schema

Not yet applied to `eibrykdamgyoylnqknao` — this session's Supabase MCP
connection was down for the whole build. Apply
`supabase/sermon_reading_pass_schema.sql` by hand (SQL editor, or
`apply_migration` once MCP is reachable again) before the first
`workflow_dispatch` run. The workflow does not create the table itself.

## What's genuinely mechanical vs. what's a flagged candidate

The spec says Stage 1 is "extraction only... no judgment calls." Some of
what it asks for really is that:

- **Scripture references** — a citation pattern either matches or it
  doesn't. Solid.
- **Target questions** — every sentence ending in `?`, offset and verbatim.
  Deliberately *not* filtered down to "the" relevant question in the
  hearer's words — picking one from many would be exactly the judgment call
  Stage 1 isn't allowed to make. Stage 2 reads the list and picks.
- **Repeated lines** — three or more near-identical sentences. Solid.
- **Ending flags** (repetition, direct address, cross-reference, imperative,
  benediction) — each one is a marker match over the last 10% of the body.
  Solid, though the imperative/benediction word lists are a starting list,
  not exhaustive.

Some of what it asks for is not actually observable in that sense —
"which sentence is the governing claim" is a reading, however small one.
For those fields, the extractor surfaces a **candidate** from a surface
marker and says so with a `confidence` field, instead of quietly asserting
the candidate is correct:

- **`governing_claim`** — first sentence matching a thesis-signaling phrase
  ("here's what I want you to see," "the truth is," …). No marker found →
  falls back to the sermon's first sentence, `confidence:
  fallback_first_sentence`. On real transcripts (tested against two full
  Furtick sermons), the marker rarely fires early and the fallback is
  common — expect Stage 2 to reject a lot of these and pick a different
  sentence.
- **`tension`** — first sentence matching a contrast connective ("but,"
  "yet," "the problem is," …). **This is the weakest field in the build.**
  "But" is one of the most common words in spoken English, so on both test
  sermons `tension.recurs_offsets` ran into the dozens — it is not finding
  80 real tension beats, it's finding 80 sentences with the word "but" in
  them. Treat `tension.first_offset`/`verbatim` as a rough starting point
  and `recurs_count` as close to meaningless until Stage 2 tightens the
  marker list or replaces it with something better.
- **`relief_points`** — sentences matching a resolution phrase ("but God,"
  "here's the good news," …), with `source_type` guessed as `scripture`
  (a citation within 300 characters), `story`, `slogan` (a short quoted
  line), or `assertion` (none of the above). This guess is exactly what
  the one hard rule needs checked — relief must come from the word — and
  it is a guess. Confirm every one of these before trusting it.
- **`devices`** — alliteration, anaphora, epistrophe, contrast, and simile
  are pattern-based and reasonably precise. **`echo` is not**: it fires on
  any content word (6+ letters) repeated within the same sentence, which on
  real transcripts fires dozens of times per sermon. It is the loudest,
  least trustworthy device type here — expect Stage 2 to throw most of
  these out. True metaphor (not simile) is not attempted at all; nothing
  mechanical distinguishes a real metaphor from an ordinary copula
  sentence with acceptable precision, so that gap is left for the human
  read rather than faked.
  `nearest_claim_offset/verbatim` is the nearest preceding
  `governing_claim`/`tension` candidate — a proxy for "nearest Truth,"
  since Truths themselves aren't identified in Stage 1.
- **`leak_candidates`** — marker lists straight from the spec's own
  examples (talking down, preachy, exacerbating). Position and the
  following 200 characters are captured so the sarcasm discriminator (what
  follows: rebuild = joke, more of the same = leak) can be applied later
  without re-reading the transcript, but the discrimination itself is not
  done here.
- **`structural_map`** — deliberately counts, not prose. A decile
  "summary" in English would be Stage 1 quietly grading; a tally of how
  many scripture refs/questions/devices/leak candidates fell in each tenth
  of the sermon stays inside "observable."

## Validated against

No DB egress from this sandbox, so nothing ran against the live corpus.
The full pipeline (`build_record` → `write_sql`) was run offline against
two complete Furtick sermons pulled from this session's own scratch files
(44,987 and 54,336 characters) and against short synthetic text, to check
that offsets, deciles, and every field shape actually hold up against real
spoken-transcript punctuation — not just against clean prose. Output looked
sane: scripture refs matched correctly (`Acts 1:4`, `Genesis 12:1-4`,
`John 11`), ending flags picked up real direct address and benedictions,
and the two known-noisy fields above (`tension`, `echo`) were noisy in
exactly the way described.

## What Stage 1 does not do

- Does not decide whether relief is text-funded — flags the source, leaves
  the call to Stage 2.
- Does not place a leap on the four-stop funding spectrum.
- Does not identify a Turn, or its mode.
- Does not judge device attachment or portability.
- Does not decide whether the hearer left lighter.
- Does not know delivery, timing, musicality, or whether the room actually
  responded — none of that is in a transcript.

All of that is Stage 2, or later.

## Running it

```
# report corpus sizes, read-only
python3 sermon_reading_pass.py --survey

# try it on a handful of sermons before the full corpus
python3 sermon_reading_pass.py --source exemplar --limit 5 --sql-out sample.sql

# the real run — needs the workflow (or a machine with Supabase egress
# and the service key), not this sandbox
python3 sermon_reading_pass.py --apply
```

Or trigger `.github/workflows/sermon_reading_pass.yml` from the Actions
tab: pick `source` and an optional `limit` for a cheap first pass, dry run
stays on until unticked.
