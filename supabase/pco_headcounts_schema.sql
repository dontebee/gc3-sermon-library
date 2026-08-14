-- The room counts: Planning Center Headcounts, mirrored.
--
-- One row per headcount: a service time, an attendance type (In Person,
-- Online-Views, West), and a total. Aggregates only; there are no person
-- ids in this table by construction. pco_headcounts_sync.py fills it, the
-- Pulse reads it.

create table if not exists public.pco_headcounts (
  headcount_id       text primary key,
  total              integer,
  attendance_type_id text,
  attendance_type    text,
  event_time_id      text,
  starts_at          timestamptz,
  synced_at          timestamptz not null default now()
);

create index if not exists pco_headcounts_starts_at on public.pco_headcounts (starts_at);

-- Service-role only, like every other mirror: RLS on, no policies.
alter table public.pco_headcounts enable row level security;
