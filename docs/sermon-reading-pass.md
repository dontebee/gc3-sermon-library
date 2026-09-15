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
  This sandbox has no direct egress to Supabase and no service key, same
  as every earlier exemplar-corpus session; the workflow is how this
  actually runs against the live ~1,800 sermons, the same way the nightly
  jobs do. (Supabase MCP did reconnect mid-session and was used to apply
  the schema and hand-verify two rows — see "Validated against" below —
  but that's not the same as the REST path the real run takes.)

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

Applied to `eibrykdamgyoylnqknao` 2026-09-15, once Supabase MCP reconnected
mid-session. `punctuation_quality` was added in a second migration after
live testing found the gap described below — see that section.

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

## `punctuation_quality` — a real bug the live test caught

Some sources — mostly auto-caption scrapes — carry **no terminal
punctuation at all**: not "light," zero. Pulling five real rows (three
`exemplar_sermons`, two `sermons`) once Supabase MCP reconnected, three of
the five had 0–0.1 periods/question marks per 1,000 characters in a
19,000–21,000 character body, against 20+ per 1,000 for a normally
punctuated one. `split_sentences` originally found exactly **one
"sentence" covering the entire body** for those — every offset, decile,
and device field on that row quietly collapsed to `pct: 0.0`.

Fixed with a density check: below 2 terminal marks per 1,000 characters,
the splitter falls back to fixed 22-word pseudo-sentences instead of real
sentence boundaries, and the row is stamped `punctuation_quality:
'sparse_punctuation'` (vs `'normal'`) so Stage 2 knows every verbatim/
offset on that row is a window approximation, not a spoken sentence. This
was live-verified, not just unit-tested: before the fix, a Dharius
Daniels row's devices all landed in decile 0; after, they spread
realistically across all ten deciles (12, 17, 9, 6, 13, 6, 8, 6, 12, 1).

One side effect worth knowing: on a `sparse_punctuation` row,
`target_questions` will usually be empty even though the sermon is full of
rhetorical questions — there's no `?` in the source to find. That's an
accurate absence (nothing to mechanically detect), not a bug.

## Validated against

Live-tested against `eibrykdamgyoylnqknao`, not just offline. Two rows
were pulled, extracted, and written through to `sermon_reading_pass` by
hand (this sandbox still has no direct Supabase egress, so this went
through Supabase MCP rather than the REST path the real run uses):

- Tolan Morgan, "Moving On From Your Mistakes" (19,468 chars,
  `sparse_punctuation`, 8 scripture refs, 59 devices)
- PD, "STAINED..." (15,622 chars, `normal`, 21 scripture refs — every
  citation in the sermon's own outline correctly matched, including the
  repeated ones in the header block)

Both landed clean; a follow-up query confirmed zero orphaned rows (every
`source_id` traces to a live row in the corpus it claims). A third row
(Dharius Daniels, ~20K chars) failed to insert this way — not a data
problem, a **measured ceiling on how much SQL text a single hand-run
`execute_sql` call can carry: somewhere around 37,500 characters**, past
which the statement truncates mid-value and Postgres rejects the whole
thing atomically (nothing corrupt lands). This matches a limit found in
an earlier exemplar-corpus session. It does not apply to the real run:
`write_rows` posts one row at a time as an actual HTTP request from
Python, not text retyped through a tool call, so the workflow is not
subject to it.

Before the punctuation fix, the pipeline was also run offline against two
complete Furtick sermons pulled from this session's own scratch files
(44,987 and 54,336 characters) and short synthetic text, to check field
shapes against real spoken-transcript punctuation. Both of those happened
to be normally punctuated, which is exactly why the sparse-punctuation gap
wasn't caught until real `exemplar_sermons`/`sermons` rows were pulled.

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
