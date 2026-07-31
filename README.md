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

## Engagement nudges and weekly digest

`engagement_nudges.py` (run by `.github/workflows/engagement.yml` every Monday,
plus a manual trigger with a dry-run option) watches the whole GC3 platform,
intranet and Growth Track, and sends:

- **Growth Track celebrations, from Pastor Donte.** When someone finishes a
  phase (GATHER, GROW, GO) or the whole track, they get a personal email.
  Logged to `gt_email_log` (kinds `celebrate_gather`, `celebrate_grow`,
  `celebrate_go`, `celebrate_course`) so nobody is emailed twice, and
  `email_optout` is honored. The existing in-app nudge system (nudge_3,
  checkin_7, etc.) is untouched.
- **First-time giver celebrations.** Donations are synced from Planning Center
  Giving into the `giving_gifts` table; a donor whose first-ever gift is recent
  gets a thank-you from Pastor Donte (kind `first_gift` in `giving_nudge_log`).
- **Monthly giving nudges.** Donors with 2+ gifts in 90 days who are not on a
  recurring schedule get a warm invitation to become monthly partners, at most
  once every 60 days (kind `monthly_nudge`).
- **A weekly digest to the Lead Pastor** (`DIGEST_TO`, default
  dontebee@gmail.com): who joined and moved through Growth Track, milestones,
  who has gone quiet, giving totals, first-time givers, new monthly partners,
  intranet activity, and everything the automation sent.

### Secrets to add (Settings > Secrets and variables > Actions)

- `RESEND_API_KEY` : from https://resend.com (the godchasers.church domain is
  already verified there). **Until this secret exists the job runs report-only
  and sends nothing**, so you can merge safely and turn on sending later.
- `PCO_APP_ID` and `PCO_SECRET` : a Planning Center **personal access token**
  (https://api.planningcenteronline.com/oauth/applications) from an account
  that can see Giving. Without these the giving features are skipped and the
  digest tells you how to connect them.

Optional repo *variables*: `DIGEST_TO`, `NUDGE_FROM` (default
`Pastor Donte <pastor@godchasers.church>`, must be on the verified domain),
`REPLY_TO` (default dontebee@gmail.com). Emails are capped at `MAX_EMAILS`
(30) per run as a safety valve; the digest is never capped.

The schema additions live in `supabase/engagement_schema.sql` (already applied
to the live project, service-role only like everything else here).

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

It checks both the uploads tab and the live-streams tab (Sunday sermons stream
live), and dedupes across them.

## Enrichment (the analysis is built in)

Every sermon is analyzed as it is pulled, not after. After cleaning the captions,
the job calls the Anthropic API to extract scriptures, a big idea, theme tags,
verbatim quotes, Greek/Hebrew word studies, named teaching frameworks, and the
series name, then inserts a complete row. This is the most important part: a raw
transcript with no analysis is just text.

This requires an `ANTHROPIC_API_KEY` (get one at https://console.claude.com, add a
little credit). Cost is roughly 2 to 4 cents per sermon with the default model
(`claude-sonnet-4-6`). Change `ENRICH_MODEL` in `weekly_update.py` to
`claude-haiku-4-5` for cheaper or `claude-opus-4-8` for maximum depth. If the key
is absent, the sermon is still saved (body and search work), just without the
analysis, and a warning is printed.

## Setup

The Supabase project and schema are already live. To turn on the weekly automation:

1. Create a private GitHub repo named `gc3-sermon-library` and push this folder
   (see "Push to GitHub" below).
2. In the repo: Settings > Secrets and variables > Actions > New repository secret.
   Add three secrets:
   - `SUPABASE_URL` = `https://eibrykdamgyoylnqknao.supabase.co`
   - `SUPABASE_SERVICE_KEY` = your service_role key (Supabase > Settings > API).
     Use a freshly rotated key.
   - `ANTHROPIC_API_KEY` = your Anthropic API key (https://console.claude.com),
     used to analyze each sermon on pull.
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
