-- The Planning Center People roster, mirrored.
--
-- This is the table that takes Pursuit from hundreds to thousands. PD's
-- floor rule (L0) says a Planning Center record at all is Fellowship, and
-- until this mirror existed the resolver could not see the roster to apply
-- it. The People sync fills this table nightly; pursuit_resolve.py reads
-- it and never queries PCO directly, so a PCO outage can never stall the
-- board.
--
-- Raw mirror, one row per PCO person, resolver does the thinking:
-- membership strings stay as PCO spells them, children stay in the table
-- (the household roll-up will need them) but never board a ship.

create table if not exists pco_people (
  pco_person_id text primary key,
  first_name text,
  last_name text,
  name text,                       -- PCO's own display name
  email text,                      -- primary, else first on file
  phone text,                      -- primary, else first on file
  membership text,                 -- as PCO spells it: Member, Partner, Attender...
  pco_status text,                 -- active | inactive, PCO's flag not ours
  child boolean not null default false,
  avatar_url text,
  household_id text,               -- first household, for the kids roll-up
  pco_created_at timestamptz,      -- when the house entered them
  pco_updated_at timestamptz,
  synced_at timestamptz not null default now()
);
create index if not exists pco_people_email_idx on pco_people (lower(email));
create index if not exists pco_people_membership_idx on pco_people (membership);
create index if not exists pco_people_household_idx on pco_people (household_id);
alter table pco_people enable row level security;
