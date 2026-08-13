-- Pursuit: the second axis.
--
-- A ship is a high-water mark: how far a person got. It never comes back
-- down, because a person demoted for silence could be swept into a
-- plan-your-visit sequence, which is the 2026-08-05 failure wearing a new
-- coat. State is the other fact, the one the fleet was missing: whether
-- they are still here.
--
-- Additive only. pursuit_schema.sql is already applied and nothing here
-- rewrites it. Nothing reads these columns yet either; the rule engine
-- lands next.
--
-- See docs/pursuit-ship-rules.md for what sets each of these and why.

-- active   any signal in the last 6 months
-- dormant  no signal in 6 months
-- inactive no signal in 24 months, PD's rule
-- archived a human said why. A clock is never allowed to write this one.
alter table pursuit_people
  add column if not exists state text not null default 'active';

alter table pursuit_people
  drop constraint if exists pursuit_people_state_chk;
alter table pursuit_people
  add constraint pursuit_people_state_chk
  check (state in ('active', 'dormant', 'inactive', 'archived'));

-- The clock reads this one column, so every sync has to keep it fresh:
-- check-ins, giving, serving, registrations, Growth Track, a kid's check-in
-- rolled up to the household, and the livestream "I'm here" tap. Leave the
-- last two out and every online household and every parent who does not
-- badge in reads as gone.
alter table pursuit_people
  add column if not exists last_signal_at timestamptz;
alter table pursuit_people
  add column if not exists last_signal_source text;
  -- check_in | gift | serving | registration | growth_track | household | live_here

alter table pursuit_people
  add column if not exists dormant_since timestamptz;

-- Archive is a human act with a stated reason, and the reasons do not
-- behave alike: moved away and transferred to another church are good
-- outcomes that should never appear on a win-back list, opted_out has to
-- reach the shared suppression list in gc3-intranet, and not_a_person is
-- the bot form fill. Duplicates are not archived, they are merged through
-- pursuit_merge_candidates, because archiving one of a pair loses whatever
-- history sat on the wrong record.
alter table pursuit_people
  add column if not exists archived_reason text;
  -- moved | transferred | deceased | opted_out | not_a_person
alter table pursuit_people
  add column if not exists archived_at timestamptz;
alter table pursuit_people
  add column if not exists archived_by text;

-- Deceased is its own column rather than a value in archived_reason,
-- because it is checked before anything renders and must not depend on
-- anyone parsing a string correctly. The failure mode is small, quiet and
-- unforgivable: a "we miss you" list with a widow's late husband on it.
-- Every list, every count, every export filters on this first.
alter table pursuit_people
  add column if not exists deceased boolean not null default false;

-- Rides alongside Fellowship. A partner has given the house Time, Talent,
-- or Treasure; attendance is none of the three, so these people are named
-- rather than promoted or forgotten. faithful_unattached gives none of the
-- three, half_attached gives one but stays under every Partnership bar.
-- Changes no ship, triggers nothing outward, produces a list a campus
-- pastor can work down on a Tuesday.
alter table pursuit_people
  add column if not exists attach_flag text;
  -- faithful_unattached | half_attached | gave_once_stayed | kids_in_parents_out

create index if not exists pursuit_people_state_idx
  on pursuit_people (state);
create index if not exists pursuit_people_last_signal_idx
  on pursuit_people (last_signal_at desc nulls last);
create index if not exists pursuit_people_attach_flag_idx
  on pursuit_people (attach_flag) where attach_flag is not null;

-- The living, in ship order. Everything the board counts should come
-- through here rather than off the base table, so that no future query
-- forgets the deceased check.
create or replace view pursuit_people_visible as
  select * from pursuit_people
  where deceased = false
    and state <> 'archived';
