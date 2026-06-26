-- GC3 Sermon Library schema.
-- Apply once: paste into the Supabase SQL editor (Project > SQL Editor > New query),
-- or run with the Supabase CLI. Already applied to project gc3-sermon-library.

create table if not exists sermons (
  id bigint generated always as identity primary key,
  youtube_video_id text unique not null,
  title text not null,
  preached_date date,
  series text,
  youtube_url text,
  duration_seconds int,
  speaker text default 'PD',
  verified boolean default false,
  body text,
  big_idea text,
  scriptures text[] default '{}',
  themes text[] default '{}',
  quotes text[] default '{}',
  created_at timestamptz default now(),
  fts tsvector generated always as (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(big_idea, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'C')
  ) stored
);

create index if not exists sermons_fts_idx on sermons using gin (fts);
create index if not exists sermons_preached_date_idx on sermons (preached_date);
create index if not exists sermons_series_idx on sermons (series);
create index if not exists sermons_speaker_idx on sermons (speaker);
create index if not exists sermons_themes_idx on sermons using gin (themes);
create index if not exists sermons_scriptures_idx on sermons using gin (scriptures);

create table if not exists word_studies (
  id bigint generated always as identity primary key,
  sermon_id bigint references sermons (id) on delete cascade,
  term text not null,
  language text,
  gloss text,
  usage text,
  quote text,
  created_at timestamptz default now()
);
create index if not exists word_studies_sermon_idx on word_studies (sermon_id);
create index if not exists word_studies_term_idx on word_studies (lower(term));

create table if not exists frameworks (
  id bigint generated always as identity primary key,
  sermon_id bigint references sermons (id) on delete cascade,
  name text not null,
  description text,
  quote text,
  created_at timestamptz default now()
);
create index if not exists frameworks_sermon_idx on frameworks (sermon_id);

-- Private library: lock out anon and public roles. The service key and the
-- Supabase dashboard bypass row level security, so loads and queries still work.
alter table sermons enable row level security;
alter table word_studies enable row level security;
alter table frameworks enable row level security;
