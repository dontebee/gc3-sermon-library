-- Meta lead mirror schema. Applied to the live project when the mirror job
-- was built; kept here as the record, service-role only like everything else.
--
-- One table: every lead Meta's instant forms have collected, mirrored into
-- the house's own database. Two reasons it exists:
--
--   1. Rescue. Meta deletes instant-form submissions 90 days after they are
--      submitted. Anything not downloaded or synced by then is gone. The
--      mirror pulls everything still alive and keeps it.
--   2. Independence. ChurchFunnels ingests leads through its own Facebook
--      integration, which can silently break (it apparently has). The mirror
--      is a second pipe straight from Meta into the house's Supabase, so no
--      third party outage can lose a person who raised a hand.
--
-- The raw field_data jsonb is the source of truth (form fields vary);
-- full_name, email and phone are parsed conveniences for matching. This
-- table feeds visit_plans (the Visit Module plan, Phase 2) and the leak
-- measurement against ChurchFunnels.

create table if not exists meta_leads (
  id bigint generated always as identity primary key,
  leadgen_id text unique not null,
  page_id text,
  page_name text,
  form_id text,
  form_name text,
  created_time timestamptz,
  is_organic boolean not null default false,
  ad_id text,
  ad_name text,
  adset_id text,
  adset_name text,
  campaign_id text,
  campaign_name text,
  full_name text,
  email text,
  phone text,
  field_data jsonb,
  created_at timestamptz not null default now()
);
create index if not exists meta_leads_created_idx on meta_leads (created_time);
create index if not exists meta_leads_form_idx on meta_leads (form_id);
create index if not exists meta_leads_email_idx on meta_leads (lower(email));
alter table meta_leads enable row level security;
