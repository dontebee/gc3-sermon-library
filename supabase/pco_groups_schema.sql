-- PCO Groups, mirrored: Charisma, life groups, every circle the house runs.
--
-- PD's Discipleship rules read from here: being in any group is formation
-- (D9), leading one is D2, and Charisma is named in D1. Until this mirror
-- existed the resolver could not see group life at all, which is why
-- Discipleship sat empty while real people sat in real living rooms.

create table if not exists pco_groups (
  group_id text primary key,
  name text,
  group_type text,
  archived boolean not null default false,
  memberships_count int,
  synced_at timestamptz not null default now()
);
alter table pco_groups enable row level security;

create table if not exists pco_group_memberships (
  membership_id text primary key,
  group_id text not null,
  group_name text,                -- denormalized so the resolver reads one table
  pco_person_id text,
  role text,                      -- member | leader, as PCO spells it
  joined_at timestamptz,
  synced_at timestamptz not null default now()
);
create index if not exists pco_group_memberships_person_idx
  on pco_group_memberships (pco_person_id);
create index if not exists pco_group_memberships_group_idx
  on pco_group_memberships (group_id);
alter table pco_group_memberships enable row level security;
