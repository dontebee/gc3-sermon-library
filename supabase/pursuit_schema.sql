-- Pursuit, Phase A schema. Applied to the live project.
--
-- Every table is prefixed pursuit_, matching the house convention in this
-- shared database (gt_, fin_, pathway_, meta_, ghl_). The intranet already
-- owns a bare `tasks` table; prefixes keep one project legible to everyone.
--
-- Pursuit is a status board for every person God sends, guiding each gift
-- through their journey with God and with GodChasers. See
-- docs/pursuit-plan.md for the vision and docs/pursuit-spec.md for the
-- build spec. This file is the data plane's half of Phase A: the spine
-- every screen reads from.
--
-- Service-role only (RLS enabled, no policies), matching every other table
-- in this project. The intranet app adds role-scoped policies when the UI
-- lands; until then only the service key and the dashboard can read these.
--
-- Two rules are enforced by the shape of this schema, not just by prose:
--
--   1. No giving column exists anywhere in Pursuit. A person's card shows
--      their journey, never their money. Aggregates live in the vital
--      signs, read straight from giving_gifts, and never join to people.
--   2. Nothing here sends anything. There is no template, no queue, no
--      recipient list. Member-facing sending belongs to the Pathways
--      engine in gc3-intranet, which owns the switch, the suppression
--      list and unsubscribe.

-- The unification spine: one row per human being, however many systems
-- know them. Populated by pursuit_resolve.py.
create table if not exists pursuit_people (
  id uuid primary key default gen_random_uuid(),
  first_name text,
  last_name text,
  display_name text,
  email text,
  phone text,                              -- E.164 where known
  -- identity across the systems the house already runs
  pco_person_id text unique,               -- Planning Center People
  ghl_contact_id text,                     -- ChurchFunnels, transition only
  gt_profile_id uuid,                      -- Growth Track profile
  auth_user_id uuid,                       -- intranet login, if any
  meta_leadgen_id text,                    -- the ad lead that started it
  -- where they are in the fleet
  ship text not null default 'friendship',
  ship_boarded_at timestamptz default now(),
  first_seen_at timestamptz,               -- earliest evidence of contact
  -- housekeeping
  source text,                             -- meta_form | churchfunnels | growth_track | serving | walk_in | manual
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists pursuit_people_email_idx on pursuit_people (lower(email));
create index if not exists pursuit_people_phone_idx on pursuit_people (phone);
create index if not exists pursuit_people_ship_idx on pursuit_people (ship);
create index if not exists pursuit_people_pco_idx on pursuit_people (pco_person_id);
alter table pursuit_people enable row level security;

-- Cards on the Board: the working sub-stages inside Friendship and
-- Fellowship. One live card per person in the chase; archived when the
-- chase resolves. Stage vocabulary matches the church's existing
-- ChurchFunnels pipeline on purpose, so staff relearn nothing.
create table if not exists pursuit_cards (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references pursuit_people (id) on delete cascade,
  stage text not null default 'planned_visit',
     -- planned_visit | confirmed | attended | no_show | not_coming | returned
  planned_for date,
  source text,
  meta_leadgen_id text,
  campaign_id text,
  campaign_name text,
  ad_id text,
  assigned_to uuid,                        -- intranet user id
  stage_changed_at timestamptz not null default now(),
  archived boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists pursuit_cards_stage_idx on pursuit_cards (stage) where archived = false;
create index if not exists pursuit_cards_person_idx on pursuit_cards (person_id);
create index if not exists pursuit_cards_planned_idx on pursuit_cards (planned_for);
alter table pursuit_cards enable row level security;

-- Every move, forever. The funnel math and the audit trail both come free
-- from this table, and nothing is ever overwritten.
create table if not exists pursuit_stage_events (
  id bigint generated always as identity primary key,
  person_id uuid references pursuit_people (id) on delete cascade,
  card_id uuid references pursuit_cards (id) on delete set null,
  from_stage text,
  to_stage text,
  from_ship text,
  to_ship text,
  moved_by uuid,                           -- null means a job moved it
  reason text,
  created_at timestamptz not null default now()
);
create index if not exists pursuit_stage_events_person_idx on pursuit_stage_events (person_id);
create index if not exists pursuit_stage_events_created_idx on pursuit_stage_events (created_at);
alter table pursuit_stage_events enable row level security;

-- Human contact, logged in two taps. The personal touches are the point of
-- the whole system: the machine walks people to the door, people walk
-- people into the family.
create table if not exists pursuit_touches (
  id bigint generated always as identity primary key,
  person_id uuid not null references pursuit_people (id) on delete cascade,
  kind text not null,                      -- called | texted | met | prayed | note
  note text,
  by_user uuid,
  created_at timestamptz not null default now()
);
create index if not exists pursuit_touches_person_idx on pursuit_touches (person_id);
alter table pursuit_touches enable row level security;

create table if not exists pursuit_tasks (
  id uuid primary key default gen_random_uuid(),
  person_id uuid references pursuit_people (id) on delete cascade,
  title text not null,
  detail text,
  assigned_to uuid,
  due_on date,
  source text,                             -- strategy | workflow | manual
  source_id uuid,
  done_at timestamptz,
  done_by uuid,
  created_at timestamptz not null default now()
);
create index if not exists pursuit_tasks_assigned_idx on pursuit_tasks (assigned_to) where done_at is null;
alter table pursuit_tasks enable row level security;

-- Ambiguous identity matches wait here for a human. Never auto-merge on a
-- name: two Michael Browns are two people until someone who knows them
-- says otherwise.
create table if not exists pursuit_merge_candidates (
  id bigint generated always as identity primary key,
  person_id uuid not null references pursuit_people (id) on delete cascade,
  other_person_id uuid references pursuit_people (id) on delete cascade,
  evidence jsonb,                          -- what matched, and how strongly
  confidence numeric(3,2),
  resolved_at timestamptz,
  resolved_by uuid,
  resolution text,                         -- merged | distinct
  created_at timestamptz not null default now(),
  unique (person_id, other_person_id)
);
alter table pursuit_merge_candidates enable row level security;

-- What PD expects of each ship this season. The ship rooms read these.
create table if not exists pursuit_ship_goals (
  id bigint generated always as identity primary key,
  ship text not null,
  metric text not null,                    -- planned_per_month | show_rate | first_touch_hours | ...
  target numeric not null,
  season text,                             -- e.g. 2026-Q4
  created_at timestamptz not null default now(),
  unique (ship, metric, season)
);
alter table pursuit_ship_goals enable row level security;
