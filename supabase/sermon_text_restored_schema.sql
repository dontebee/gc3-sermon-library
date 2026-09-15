-- Punctuation restored onto transcripts that arrived without any.
--
-- WHY THIS IS A SEPARATE TABLE, AND NOT A COLUMN ON sermons/exemplar_sermons:
--
-- Both CLAUDE.md files say never write to `sermons` or `exemplar_sermons`,
-- and the exemplar ingest spec says "Leave the words alone. Do not
-- punctuate, do not capitalize, do not 'improve.'" Both still hold. This
-- table does not violate them: the source bodies are never touched. The
-- restored text lives beside them, clearly marked as derived, and anything
-- reading it knows it is a machine's reading of the transcript rather than
-- the transcript.
--
-- There is also a mechanical reason. `sermons.body` feeds a generated `fts`
-- tsvector and sits next to an `embedding`. Rewriting 392 bodies in place
-- would silently re-index a third of PD's corpus, and a polluted similarity
-- search cannot be un-run.
--
-- WHAT "VERIFIED" MEANS HERE:
--
-- Every chunk is checked mechanically after the model returns it: lowercase
-- both sides, drop apostrophes, replace every non-alphanumeric run with a
-- single space, and compare. If one word changed, was added, or was
-- dropped, the strings differ and the chunk is rejected. `verified` is true
-- only when every chunk of that sermon passed. A row that failed keeps the
-- original text for the chunks that failed, so nothing here can be a
-- paraphrase: it is the same words, with marks between them.
--
-- Applied to eibrykdamgyoylnqknao 2026-09-15.

create table if not exists sermon_text_restored (
  id                bigint generated always as identity primary key,

  -- Points at exemplar_sermons.id or sermons.id, per `source`. Same
  -- two-table join key as sermon_reading_pass, and no FK for the same
  -- reason: it targets one of two tables.
  source            text not null check (source in ('exemplar', 'pd')),
  source_id         bigint not null,

  body_restored     text not null,

  -- True only if every chunk round-tripped with not one word changed.
  -- The reading pass reads only verified rows.
  verified          boolean not null default false,
  chunks_total      integer not null,
  chunks_verified   integer not null,

  -- Provenance. Which model, which prompt, when — so a later run with a
  -- better model can be told apart from this one rather than guessed at.
  restored_by       text not null,
  restorer_version  text not null,

  -- Cheap sanity numbers for a human scanning the table: the restored text
  -- should be slightly longer (marks added) and never shorter.
  char_len_source   integer not null,
  char_len_restored integer not null,

  created_at        timestamptz not null default now(),

  unique (source, source_id)
);

create index if not exists sermon_text_restored_verified_idx
  on sermon_text_restored (source, verified) where verified;

comment on table sermon_text_restored is
  'Punctuation restored onto transcripts that arrived with none. Derived text, never a replacement: sermons.body and exemplar_sermons.body are never written to, because rewriting them would re-index a generated fts column and because the house rule forbids it. Every chunk is mechanically verified to contain exactly the same words as its source - same letters and digits, in the same order - so a row here can differ from its source only in punctuation, capitalization and whitespace.';

comment on column sermon_text_restored.verified is
  'True only when every chunk round-tripped with not one word changed, added or dropped. Consumers should read WHERE verified, never the raw column.';

-- Verification. The first should return zero rows: anything longer in words
-- than its source means the guarantee failed somewhere.
--
-- select count(*) from sermon_text_restored where not verified;
--
-- select r.source, count(*), round(avg(r.char_len_restored - r.char_len_source)) as avg_marks_added
-- from sermon_text_restored r where r.verified group by r.source;
