-- Stage 1 of the GC3 Exemplar Reading Pass: mechanical extraction only.
-- No scores, no verdicts. One row per sermon, across both corpora.
--
-- Reads from `sermons` (PD, source_type manuscript|transcript) and
-- `exemplar_sermons` (outside preachers). Writes to neither. This table is
-- new and separate on purpose, same reasoning as exemplar_sermons: a table
-- that already carries fts/embedding is not where you bolt an experimental
-- analysis column, and a reading-pass row is not a sermon.
--
-- (source, source_id) is the join key back to whichever table the row came
-- from. There is no real foreign key, because it points at one of two
-- tables depending on `source` — enforced in the extractor, not in SQL.
--
-- Applied to eibrykdamgyoylnqknao 2026-09-15, via Supabase MCP once it
-- reconnected (this sandbox still has no direct HTTP egress to Supabase —
-- see sermon_reading_pass.py's docstring for how the real run gets it).

create table if not exists sermon_reading_pass (
  id                  bigint generated always as identity primary key,

  -- Where this row came from.
  source              text not null check (source in ('exemplar', 'pd')),
  source_id           bigint not null,   -- exemplar_sermons.id or sermons.id, per `source`
  preacher            text not null,
  source_type         text,              -- manuscript | transcript (PD's distinction; carried through, never collapsed)
  sermon_date         date,
  title               text,
  char_len            integer not null,

  -- Proctor spine + the three continuous threads. Each of these is a
  -- best-effort candidate from surface markers (thesis-signaling phrases,
  -- contrast connectives, question marks) — not a judgment that this IS the
  -- governing claim or the tension. Stage 2 calibrates confidence; the
  -- fields exist so a human has evidence to look at, not a verdict to trust.
  governing_claim     jsonb not null default '{}'::jsonb,
  -- shape: {first_offset, first_pct, verbatim, confidence,
  --         restated_count, restated_offsets: [...]}

  tension             jsonb not null default '{}'::jsonb,
  -- shape: {first_offset, first_pct, verbatim, confidence,
  --         recurs_count, recurs_offsets: [...]}

  target_questions    jsonb not null default '[]'::jsonb,
  -- every interrogative sentence, verbatim + offset. Deliberately NOT
  -- filtered down to "the" relevant question — picking one from many would
  -- be the judgment call Stage 1 is not allowed to make.
  -- shape: [{offset, pct, verbatim}, ...]

  relief_points       jsonb not null default '[]'::jsonb,
  -- candidate points where tension appears to resolve, with the apparent
  -- source of the relief quoted. Sufficiency is explicitly NOT judged here.
  -- shape: [{offset, pct, verbatim, source_type, source_quote}, ...]
  -- source_type in ('scripture', 'story', 'slogan', 'assertion') — a
  -- heuristic guess, confirmed or corrected in Stage 2.

  scripture_refs      jsonb not null default '[]'::jsonb,
  -- the one field here that is genuinely mechanical: a citation pattern
  -- either matched or it didn't.
  -- shape: [{ref, offset, pct, surrounding_claim}, ...]

  devices             jsonb not null default '[]'::jsonb,
  -- shape: [{type, offset, pct, verbatim, nearest_claim_offset, nearest_claim_verbatim}, ...]
  -- type in ('alliteration','anaphora','epistrophe','echo','contrast','simile').
  -- Metaphor (not simile) is not attempted mechanically — see docs.

  repeated_lines       jsonb not null default '[]'::jsonb,
  -- shape: [{line, count, offsets: [...]}, ...] — lines (normalized) that
  -- recur 3+ times. Genuinely mechanical.

  ending               jsonb not null default '{}'::jsonb,
  -- shape: {verbatim, flags: {repetition, direct_address, cross_reference,
  --         imperative, benediction}}

  leak_candidates      jsonb not null default '[]'::jsonb,
  -- shape: [{type, offset, pct, verbatim, next_200_chars}, ...]
  -- type in ('talking_down','preachy','exacerbating'). Position and what
  -- follows are captured so the sarcasm discriminator can be applied later
  -- without touching the transcript again.

  orality_markers      jsonb not null default '{}'::jsonb,
  -- shape: {direct_address: {count, by_decile: [10 ints]},
  --         rhetorical_questions: {count, by_decile},
  --         short_clauses: {count, by_decile},
  --         parallelism: {count, by_decile},
  --         invitations_to_respond: {count, by_decile}}

  structural_map        jsonb not null default '[]'::jsonb,
  -- 10 entries, one per decile. Each entry is counts, not prose — a decile
  -- "summary" in English would be Stage 1 quietly grading. shape:
  -- [{decile, scripture_refs, questions, repeated_line_hits, devices,
  --   leak_candidates}, ...]

  -- Some sources have essentially no terminal punctuation at all (0-0.1
  -- marks per 1,000 characters vs 20+ for a normally punctuated transcript,
  -- measured against real exemplar_sermons rows during testing). Without
  -- this flag, the sentence splitter finds one "sentence" covering the
  -- entire body and every offset/decile/device field quietly degrades.
  -- 'sparse_punctuation' means a fixed-word-window fallback ran instead —
  -- every verbatim/offset field on that row is an approximation, not a real
  -- sentence boundary. Discount accordingly in Stage 2.
  punctuation_quality   text not null default 'normal',

  extractor_version     text not null,
  extracted_at          timestamptz not null default now(),

  -- Re-running the extractor (a fixed regex, a new heuristic) should update
  -- the row, not duplicate it.
  unique (source, source_id)
);

create index if not exists sermon_reading_pass_source_idx
  on sermon_reading_pass (source, preacher);

comment on table sermon_reading_pass is
  'Stage 1 of the GC3 Exemplar Reading Pass: mechanical/heuristic extraction over sermons and exemplar_sermons. No scores, no verdicts — a coach''s report needs evidence, and Stage 2 (PD + Claude, 20 sermons) is where judgment calls get calibrated. Never written to by anything that also writes sermons or exemplar_sermons.';

comment on column sermon_reading_pass.governing_claim is
  'Best-effort candidate for the sermon''s thesis, found by surface markers (thesis-signaling phrases) with a fallback to the first sentence. confidence names which. Not asserted as correct — Stage 2 checks it.';

comment on column sermon_reading_pass.relief_points is
  'Candidate points where tension resolves and what it was resolved BY. Whether that source actually counts (per the hard rule: relief must come from the word) is a Stage 2 judgment, not made here.';

alter table sermon_reading_pass enable row level security;

-- Verification: every row must trace to a real sermon in exactly one corpus,
-- and no source_id should ever collide across the two.
--
-- select source, count(*) from sermon_reading_pass group by source;
--
-- select count(*) from sermon_reading_pass rp
-- where source = 'exemplar'
--   and not exists (select 1 from exemplar_sermons s where s.id = rp.source_id);
--
-- select count(*) from sermon_reading_pass rp
-- where source = 'pd'
--   and not exists (select 1 from sermons s where s.id = rp.source_id);
