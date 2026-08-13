-- Pursuit: the rules, as data PD can edit.
--
-- Why this table exists. The rules lived in a markdown file and in Python
-- constants, which meant the only way to change one was to ask an engineer,
-- and the only record of who decided what was prose. Prose drifts: a draft
-- of docs/pursuit-ship-rules.md answered two of PD's open questions on its
-- own and wrote the answers up as PD's rulings. Nobody could see that had
-- happened by looking at the system, because the system had no idea who had
-- decided anything.
--
-- So every rule is a row, every row records where it came from, and the
-- admin page at /pursuit/rules is where they change. The house rule about
-- the Pathways engine applies here too: editable rules and an admin page,
-- not logic buried in a job.
--
-- Additive. Nothing reads this yet; the rule engine lands next and will
-- read it instead of hardcoding.

create table if not exists pursuit_rules (
  code text primary key,                   -- F1, L0, P3, D6, E2, A1, Q1
  ship text not null,                       -- friendship..leadership, or 'flag'
  label text not null,                      -- what a human calls it
  currency text,                            -- time | talent | treasure | promise
  -- What the resolver counts, and how much of it.
  signal text not null,                     -- gift | serving | check_in | registration
                                            -- growth_track | group | household
                                            -- pco_status | baptism | role | live_here
  threshold int,                            -- how many times. null means "at all"
  window_days int,                          -- over what period. null means ever
  -- Where this rule came from, which is the whole point of the table.
  origin text not null default 'proposed',  -- pd | proposed
  enabled boolean not null default true,
  -- Provenance. Who last touched it, when, and what it said before.
  set_by text,
  set_at timestamptz,
  note text,
  is_default boolean not null default true, -- false once a human edits it
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists pursuit_rules_ship_idx on pursuit_rules (ship);
create index if not exists pursuit_rules_origin_idx on pursuit_rules (origin);
alter table pursuit_rules enable row level security;

-- Every edit, kept. "Reset to default" is a real button on the admin page
-- and it needs something to reset to, and a change of this kind should
-- never be silent.
create table if not exists pursuit_rule_history (
  id uuid primary key default gen_random_uuid(),
  code text not null,
  changed_by text not null,
  changed_at timestamptz not null default now(),
  action text not null,                     -- edit | enable | disable | reset
  before jsonb,
  after jsonb
);
create index if not exists pursuit_rule_history_code_idx
  on pursuit_rule_history (code, changed_at desc);
alter table pursuit_rule_history enable row level security;

-- Seeds. origin='pd' is reserved for rules PD stated close to verbatim.
-- Everything else is 'proposed' and shows up on the admin page as awaiting
-- a decision rather than as house policy.
insert into pursuit_rules
  (code, ship, label, currency, signal, threshold, window_days, origin, enabled, note)
values
  -- Friendship
  ('F1', 'friendship', 'Submitted a Plan My Visit form', null, 'registration', 1, null, 'pd', true, null),
  ('F2', 'friendship', 'Registered for one event', null, 'registration', 1, null, 'pd', true, null),
  ('F3', 'friendship', 'Came in as an ad lead', null, 'registration', 1, null, 'proposed', true, 'built and running'),

  -- Fellowship. PD: "if they have a planning center account at all they are
  -- in fellowship. Visitors, 1st time guests, givers that don't meet
  -- partner criteria."
  ('L0', 'fellowship', 'Has a Planning Center record at all', null, 'pco_status', null, null, 'pd', true, 'the floor'),
  ('L2', 'fellowship', 'Gave, but under the Partnership bar', null, 'gift', 1, null, 'pd', true, null),
  ('L3', 'fellowship', 'Checked in to any service', null, 'check_in', 1, null, 'proposed', true, null),

  -- Partnership. Time, Talent, or Treasure.
  ('P1', 'partnership', 'PCO status is Member or Partner', 'promise', 'pco_status', null, null, 'pd', true, null),
  ('P2', 'partnership', 'Has a partnership date', 'promise', 'pco_status', null, null, 'pd', true, null),
  ('P3', 'partnership', 'Gave 10+ times in 24 months', 'treasure', 'gift', 10, 730, 'pd', true, null),
  ('P4', 'partnership', 'Kids checked in 5+ times in 12 months', 'time', 'household', 5, 365, 'pd', true, null),
  ('P5', 'partnership', 'Served 2+ times in 90 days', 'talent', 'serving', 2, 90, 'pd', true, null),
  ('P6', 'partnership', 'Finished Growth Track', 'time', 'growth_track', null, null, 'proposed', true, 'built and running'),
  ('P7', 'partnership', 'Belongs to a small group', 'time', 'group', null, null, 'proposed', true, null),
  ('P8', 'partnership', 'Was baptized here', 'promise', 'baptism', null, null, 'proposed', true, null),
  -- Time, now that PD has chosen Option B. Seeded as proposed and then
  -- promoted by the update at the foot of this file, so that a reset to
  -- defaults replays the decision rather than losing it.
  ('P9', 'partnership', 'Registered for and attended 3+ things in 12 months', 'time', 'registration', 3, 365, 'proposed', false, 'threshold is a guess'),

  -- Discipleship
  ('D1', 'discipleship', 'Enrolled in Charisma Track', null, 'growth_track', null, null, 'pd', false, 'no data source exists yet'),
  ('D2', 'discipleship', 'Leads a small group', null, 'group', null, null, 'pd', true, null),
  ('D3', 'discipleship', 'Signed into Growth Track 10+ times', null, 'growth_track', 10, null, 'pd', true, null),
  ('D4', 'discipleship', 'Served 12+ times in 12 months', 'talent', 'serving', 12, 365, 'proposed', true, null),

  -- Leadership
  ('E1', 'leadership', 'Leads a team', null, 'role', null, null, 'pd', true, null),
  ('E2', 'leadership', 'GLT, staff, or director', null, 'role', null, null, 'pd', true, null),

  -- State. PD: "a person who hasn't given, served or registered for 2 years
  -- is inactive." The 6 month dormancy point is not PD's and is the one
  -- date still unset.
  ('Q1', 'flag', 'Dormant: no signal in 6 months', null, 'check_in', 0, 180, 'proposed', true, 'the window is a placeholder, not PD''s number'),
  ('Q2', 'flag', 'Inactive: no signal in 24 months', null, 'check_in', 0, 730, 'pd', true, null),

  -- Attachment flags. Change no ship, trigger nothing outward.
  ('A1', 'flag', 'Faithful, unattached: comes, gives none of the three', null, 'check_in', 12, 365, 'proposed', true, null),
  ('A2', 'flag', 'Half attached: gives one of the three, under its bar', null, 'check_in', 12, 365, 'proposed', true, null),
  ('A3', 'flag', 'Gave once, stayed', 'treasure', 'gift', 1, null, 'proposed', true, null),
  ('A4', 'flag', 'Kids in, parents out', 'time', 'household', 5, 365, 'proposed', true, null),

  -- L1 is PD's, said in the same breath as L0 ("Visitors, 1st time guests"),
  -- and the first version of this seed dropped it. The audit that caught it
  -- is the reason the table exists: a rule that is only in prose can go
  -- missing without anything noticing.
  ('L1', 'fellowship', 'A visitor or first-time guest', null, 'pco_status', null, null, 'pd', true, null),

  -- The rest were in docs/pursuit-ship-rules.md and never in the table, so
  -- the table was not actually the rule book it claimed to be.
  ('L4', 'fellowship', 'Came back within 30 days of a first visit', null, 'check_in', 2, 30, 'proposed', true, 'the number to watch even though it changes no ship'),
  ('L5', 'fellowship', 'Tapped "I''m here" on a livestream', null, 'live_here', 1, null, 'proposed', true, null),
  ('F4', 'friendship', 'Sent a prayer request or connect card', null, 'form', 1, null, 'proposed', true, null),
  ('F5', 'friendship', 'Reached out by DM or chat', null, 'message', 1, null, 'proposed', false, 'ManyChat not integrated'),
  ('F6', 'friendship', 'Was invited by a member', null, 'referral', 1, null, 'proposed', false, 'no PCO field confirmed'),
  ('D5', 'discipleship', 'Serves on two or more teams', 'talent', 'serving', 2, 365, 'proposed', true, 'threshold counts teams, not shifts'),
  ('D6', 'discipleship', 'Growth Track done, serving, and in a group', null, 'combined', 3, 365, 'proposed', true, 'the honest definition of formed until Charisma has a table'),
  ('D7', 'discipleship', 'In a mentoring or discipleship pair', null, 'mentoring', null, null, 'proposed', false, 'no data source exists yet'),
  ('D8', 'discipleship', 'Attended an equipping or leadership night', 'time', 'check_in', 1, 365, 'proposed', true, null),
  ('E3', 'leadership', 'Coaches other small group leaders', null, 'group', null, null, 'proposed', true, null),
  ('E4', 'leadership', 'Ordained or licensed', null, 'pco_status', null, null, 'proposed', true, null),
  ('E5', 'leadership', 'Elder, board, or campus pastor', null, 'role', null, null, 'proposed', true, null),
  ('E6', 'leadership', 'Owns a ministry in the Hub', null, 'role', null, null, 'proposed', true, null)
on conflict (code) do nothing;

-- PD chose Option B: Time is showing up where something was promised in
-- advance, not a bare check-in. That makes P9 a live rule rather than a
-- parked one. The kind of rule is PD's. The number 3 is still a guess.
update pursuit_rules
set origin = 'pd',
    enabled = true,
    is_default = false,
    set_by = 'PD',
    set_at = now(),
    note = 'PD chose Option B: Time is committed showing up, not a bare check-in. The threshold of 3 is still a guess and needs PD''s number.',
    updated_at = now()
where code = 'P9';
