# GC3 Sermon Library

A self-updating, full-text-searchable database of Pastor Donte Banks' sermons
(GodChasers Church). New sermons are pulled from the YouTube channel every week
and added automatically.

## What is here

- `supabase/schema.sql` : the database schema (sermons, word_studies, frameworks,
  plus weighted full-text search). Already applied to the live project.
- `backfill.py` : one-time loader for a local folder of cleaned `.txt` transcripts.
- `weekly_update.py` : the recurring job. Pulls recent uploads and adds new sermons.
- `.github/workflows/weekly.yml` : runs `weekly_update.py` every Monday, plus a
  manual trigger.

## Filtering rules (weekly job)

A new video is added only if it is:

- public,
- at least 20 minutes long (`MIN_DURATION_SECONDS = 1200`), and
- free of music or promo keywords in the title (official video, lyric, worship,
  cover, trailer, promo, behind the scenes).

Anything already in the database is skipped. New sermons are inserted with
`verified = false` and `speaker = 'PD'` so you can review and confirm them.
The supervised one-time backfill used a 10-minute floor; the weekly job uses 20
minutes because it runs unattended. Both values are one-line constants.

## Setup

The Supabase project and schema are already live. To turn on the weekly automation:

1. Create a private GitHub repo named `gc3-sermon-library` and push this folder
   (see "Push to GitHub" below).
2. In the repo: Settings > Secrets and variables > Actions > New repository secret.
   Add two secrets:
   - `SUPABASE_URL` = `https://eibrykdamgyoylnqknao.supabase.co`
   - `SUPABASE_SERVICE_KEY` = your service_role key (Supabase > Settings > API).
     Use a freshly rotated key.
3. The Action runs every Monday at 13:00 UTC. To run it on demand: Actions tab >
   Weekly sermon pull > Run workflow.

## Push to GitHub

From this folder:

```
git init
git add .
git commit -m "GC3 sermon library: schema, backfill, weekly auto-pull"
git branch -M main
git remote add origin https://github.com/dontebee/gc3-sermon-library.git
git push -u origin main
```

(Create the empty repo first at https://github.com/new, named `gc3-sermon-library`,
private, with no README or .gitignore so the push is clean.)

## Running the backfill manually

```
pip install -r requirements.txt
export SUPABASE_URL=https://eibrykdamgyoylnqknao.supabase.co
export SUPABASE_SERVICE_KEY=your_service_role_key
export TRANSCRIPT_FOLDER="/path/to/GC3-Sermon-Transcripts/ALL PD/Transcripts Only"
python backfill.py
```

On Windows PowerShell, use `$env:SUPABASE_URL = "..."` instead of `export`.

## Querying the library

Full-text search across whole sermon bodies, ranked:

```sql
select title, preached_date, series
from sermons
where fts @@ websearch_to_tsquery('english', 'spirit of jezebel')
order by ts_rank(fts, websearch_to_tsquery('english', 'spirit of jezebel')) desc
limit 10;
```

Find every sermon that taught a scripture or theme:

```sql
select title, preached_date from sermons where 'Romans 8:28' = any(scriptures);
select title, preached_date from sermons where 'purpose' = any(themes);
```

Word studies and frameworks, with their source sermons:

```sql
select w.term, w.gloss, s.title, s.preached_date
from word_studies w join sermons s on s.id = w.sermon_id
order by w.term;
```

## Conventions

- No em dashes in code or output text. Use commas, colons, or parentheses.
- "Lead Pastor", never "Senior Pastor".
- Gifts (spiritual, God-given) are kept distinct from talents (natural, developed).
- New auto-pulled sermons are unverified until reviewed. The `speaker` field is a
  default of `PD` and should be corrected for guest preachers.
