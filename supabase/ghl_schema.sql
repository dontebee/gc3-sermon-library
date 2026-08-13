-- ChurchFunnels (GoHighLevel) mirror schema. Applied to the live project;
-- kept here as the record, service-role only like everything else.
--
--   ghl_baseline_monthly : Plan Your Visit opportunities created per month,
--                          loaded once from the 2026-08-12 opportunities
--                          export. This is the Church Candy era baseline the
--                          ad account could not show (that account only
--                          starts January 2026). The zero months from
--                          October 2025 to February 2026 are real: nothing
--                          entered the funnel during the agency transition.
--   ghl_opportunities    : one row per pipeline opportunity, to be filled by
--                          a ChurchFunnels API sync (needs a Private
--                          Integration token) so show rates and lead matching
--                          run from the house's own database. Empty until
--                          that sync exists; the one-time CSV export stays
--                          with PD as the interim record.

create table if not exists ghl_baseline_monthly (
  month date primary key,
  opportunities integer not null,
  created_at timestamptz not null default now()
);
alter table ghl_baseline_monthly enable row level security;

create table if not exists ghl_opportunities (
  id bigint generated always as identity primary key,
  ghl_opportunity_id text unique not null,
  ghl_contact_id text,
  contact_name text,
  email text,
  phone text,
  pipeline text,
  stage text,
  source text,
  status text,
  created_on timestamptz,
  updated_on timestamptz,
  tags text,
  created_at timestamptz not null default now()
);
create index if not exists ghl_opportunities_created_idx on ghl_opportunities (created_on);
create index if not exists ghl_opportunities_email_idx on ghl_opportunities (lower(email));
create index if not exists ghl_opportunities_stage_idx on ghl_opportunities (stage);
alter table ghl_opportunities enable row level security;
