-- Meta ads performance schema. NOT yet applied: paste into the Supabase SQL
-- editor (Project > SQL Editor > New query) before enabling the meta ads
-- workflow.
--
-- Two tables, both service-role only (RLS enabled, no policies), matching the
-- sermon library pattern:
--
--   meta_ad_insights         : one row per ad per day, pulled weekly from the
--                              Meta Marketing API. The daily grain is the
--                              history; the analysis windows are computed at
--                              report time.
--   meta_ad_recommendations  : what the analysis concluded on each run, so
--                              the Monday digest (engagement_nudges.py) can
--                              show recommendations without holding Meta
--                              credentials.

create table if not exists meta_ad_insights (
  id bigint generated always as identity primary key,
  day date not null,
  campaign_id text not null,
  campaign_name text,
  objective text,
  adset_id text,
  adset_name text,
  ad_id text not null,
  ad_name text,
  impressions integer not null default 0,
  reach integer not null default 0,
  frequency numeric(8,3),
  clicks integer not null default 0,
  link_clicks integer not null default 0,
  spend numeric(12,2) not null default 0,
  results integer not null default 0,
  result_type text,
  actions jsonb,
  created_at timestamptz not null default now(),
  unique (ad_id, day)
);
create index if not exists meta_ad_insights_day_idx on meta_ad_insights (day);
create index if not exists meta_ad_insights_campaign_idx on meta_ad_insights (campaign_id);
alter table meta_ad_insights enable row level security;

create table if not exists meta_ad_recommendations (
  id bigint generated always as identity primary key,
  run_on date not null,
  level text not null,          -- account, campaign, adset, ad
  entity_id text not null,
  entity_name text,
  kind text not null,           -- fatigue, low_ctr, scale_winner, cost_spike,
                                -- no_delivery, needs_attention, strategy
  recommendation text not null,
  metrics jsonb,
  created_at timestamptz not null default now(),
  unique (run_on, level, entity_id, kind)
);
create index if not exists meta_ad_recommendations_run_idx on meta_ad_recommendations (run_on);
alter table meta_ad_recommendations enable row level security;
