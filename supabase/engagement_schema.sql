-- Engagement automation schema (already applied to the live project).
--
-- Two additions, both service-role only (RLS enabled, no policies), matching
-- the sermon library pattern:
--
--   giving_gifts     : donations synced from Planning Center Giving, so the
--                      weekly job can spot first-time givers and repeat givers.
--   giving_nudge_log : which giver emails have been sent, keyed by donor
--                      (email or PCO person id) because givers are not always
--                      platform users. Growth track member emails keep using
--                      the existing gt_email_log table.

create table if not exists giving_gifts (
  id uuid primary key default gen_random_uuid(),
  pco_donation_id text unique not null,
  pco_person_id text,
  donor_name text,
  donor_email text,
  amount_cents integer not null default 0,
  fund text,
  received_at timestamptz,
  recurring boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists giving_gifts_email_idx on giving_gifts (lower(donor_email));
create index if not exists giving_gifts_person_idx on giving_gifts (pco_person_id);
create index if not exists giving_gifts_received_idx on giving_gifts (received_at);
alter table giving_gifts enable row level security;

create table if not exists giving_nudge_log (
  id uuid primary key default gen_random_uuid(),
  donor_key text not null,
  kind text not null,
  sent_on date not null default ((now() at time zone 'America/Chicago'))::date,
  created_at timestamptz not null default now(),
  unique (donor_key, kind, sent_on)
);
create index if not exists giving_nudge_log_key_idx on giving_nudge_log (donor_key, kind);
alter table giving_nudge_log enable row level security;
