-- Outside preachers, held as litmus-test exemplars for the sermon grading
-- engine. Not PD's material, and never mixed into it.
--
-- `sermons` carries an fts tsvector and an embedding, and every ranked and
-- semantic search over the corpus walks that table. Adding a thousand
-- outside sermons to it pollutes every future full-text rank and every
-- nearest-neighbour result, and no `where speaker = 'PD'` bolted on later
-- un-pollutes a similarity search that already ran. Separate table,
-- separate index, no contamination possible.
--
-- Applied to eibrykdamgyoylnqknao 2026-09-15.

create table if not exists exemplar_sermons (
  id                bigint generated always as identity primary key,
  -- Deliberately not `speaker`. A query copy-pasted from a `sermons` query
  -- fails loudly here instead of quietly answering about the wrong corpus.
  preacher          text not null,
  ministry          text,
  title             text not null,
  preached_date     date,
  date_published    timestamptz,             -- often the only date the CSV has
  duration_seconds  integer,
  source_url        text,
  source_video_id   text,
  source_type       text not null default 'transcript',
  source_file       text not null,           -- which CSV this row came from
  body              text not null,
  notes             text,
  -- May the grader use this row as a benchmark? See the comment below.
  calibration_eligible boolean not null default true,
  created_at        timestamptz not null default now(),
  fts               tsvector generated always as
                      (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,''))) stored
);

-- No embedding column. Add one only if semantic search over exemplars is
-- actually needed, and give it its own index when you do.

create index if not exists exemplar_sermons_fts_idx on exemplar_sermons using gin (fts);
create index if not exists exemplar_sermons_preacher_idx on exemplar_sermons (preacher);

-- The CSVs overlap: several were scraped in the same session. This is what
-- stops the same sermon landing twice.
create unique index if not exists exemplar_sermons_dedupe_idx
  on exemplar_sermons (preacher, coalesce(source_video_id, title));

comment on table exemplar_sermons is
  'Outside preachers, held as litmus-test exemplars for the sermon grading engine. NOT PD''s corpus and never joined to it: sermons has its own fts and embedding, and mixing the two pollutes every ranked and semantic search. Column is named preacher, not speaker, so a query copy-pasted from sermons fails loudly.';

comment on column exemplar_sermons.calibration_eligible is
  'May the grading engine use this row as a benchmark? False means the row is correctly stored and correctly attributed, but is the wrong shape for a rubric ceiling - a panel, interview, master class or co-preached service rather than one preacher preaching one sermon. A limit on use, not a defect. notes says which. Curated by a person, never set by the ingest.';

-- The grader reads the eligible rows, so that is the side worth indexing.
create index if not exists exemplar_sermons_calibration_idx
  on exemplar_sermons (calibration_eligible) where calibration_eligible;

alter table exemplar_sermons enable row level security;

-- Verification. The second must return zero: anything else means an
-- exemplar leaked into PD's corpus.
--
-- select preacher, count(*) as sermons,
--        min(preached_date)::text as earliest,
--        max(preached_date)::text as latest,
--        round(avg(length(body))) as avg_chars
-- from exemplar_sermons
-- group by preacher order by sermons desc;
--
-- select count(*) as contamination
-- from sermons
-- where speaker in (select distinct preacher from exemplar_sermons);
