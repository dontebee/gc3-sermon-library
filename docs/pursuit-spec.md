# Pursuit: build specification

*This is the implementation spec for Pursuit, written to be handed to a
developer or an AI builder with no other context. The vision companion is
`docs/pursuit-plan.md`. Where they disagree, this file wins for
implementation detail and the plan wins for intent.*

> Pursuit is a status board for every person God sends, guiding each gift
> through their journey with God and with GodChasers.
> God pursues the ONE. We are stewards of the ninety-nine.
> Pursuit is our tool.

Pursuit is a staff-facing web app for GodChasers Community Church (GC3): a
mobile-first lead tracker and follow-up system that replaces the rented
ChurchFunnels (GoHighLevel) UI. It tracks every person from first ad click
through leadership, on data the church already owns.

## 1. The world you are building in

- **One Supabase project holds everything**: ref `eibrykdamgyoylnqknao`.
  All tables use RLS; existing app patterns use the service role on the
  server and role-scoped access in the app. Do not create a second
  database.
- **`gc3-intranet`** (separate repo): the church's Next.js intranet.
  Auth, user roles (`profiles`, `roles`, `user_roles`), admin pages, and
  the **Pathways engine** (`src/lib/pathways/`), which is the church's ONLY
  member-facing email sender: it has the on/off switch per pathway
  (`pathway_settings`, admin UI at `/admin/pathways`), suppression
  (`pathway_opt_outs`, `pathway_excluded_domains`,
  `pathway_excluded_people`), unsubscribe links, send log
  (`pathway_sends`), and click tracking (`email_clicks`). **Pursuit is
  built inside this repo** as routes and components.
- **`gc3-sermon-library`** (this repo): the data plane. Python jobs on
  GitHub Actions schedules. Already running or merged: weekly Meta ads
  insights sync (`meta_ad_insights`, `meta_ad_recommendations`), daily Meta
  instant-form lead mirror (`meta_leads`), Planning Center giving sync
  (`giving_gifts`), weekly sermon pull, Monday digest email to the Lead
  Pastor only. New scheduled syncs (PCO check-ins, PCO workflows,
  reconciliation) belong HERE, not in the app.
- **Existing tables Pursuit reads** (already populated or filling):
  `meta_leads` (every ad lead: name, email, phone, ad_id, campaign,
  form, field_data jsonb), `meta_ad_insights` (daily ad performance),
  `ghl_opportunities` + `ghl_baseline_monthly` (ChurchFunnels history),
  `gt_profiles`, `gt_progress`, `gt_modules` etc. (Growth Track),
  `pathway_sends`, `email_clicks` (what the house sent, opened, clicked),
  `pco_serving` (volunteer roster), `giving_gifts` (aggregates only, see
  rules), `live_broadcast`, `live_here` (online attendance),
  `profiles`, `roles`, `user_roles` (app users and permissions).
- **External systems**: Meta Marketing API (handled entirely by the data
  plane; the app never calls Meta), Planning Center API (People,
  Check-Ins, Workflows; HTTP basic auth with a personal access token,
  aggressive rate limits, retry-on-429 client exists in the data plane),
  ChurchFunnels/GoHighLevel (transition only; being replaced), Resend
  (used ONLY by the Pathways engine).

## 2. Non-negotiable rules

These are house law, learned from a real incident (an unswitched second
email system once mass-emailed donors). Violating them fails review.

1. **One sender.** Pursuit never sends member-facing email, SMS, or DM
   directly and never calls Resend or any messaging API. All member
   communication compiles down to the Pathways engine, which enforces
   switches, suppression, and unsubscribe. Pursuit may create pathway
   enrollments and rules; it may never bypass them.
2. **Giving stays invisible.** `giving_gifts` appears ONLY as aggregate
   vital signs (totals, giver counts, recurring share) visible to
   leadership roles. Never on a person card, never as a stage marker,
   never in a filter. No exceptions.
3. **No surveillance voice.** Any member-facing copy: 60 to 90 words,
   Scripture lands after the point (one line, usually KJV), God does the
   seeing (never "I noticed you..."), the body asks for nothing, the P.S.
   carries the next step.
4. **Vocabulary.** "Journeys" means Growth Track (the `gt_*` tables).
   "Pathways" means the member-messaging system. The five Ships (below)
   are the journey language. "Lead Pastor", never "Senior Pastor". No em
   dashes in code, comments, or output text.
5. **Mobile first.** Every screen is designed for a phone before a
   desktop. Staff live on phones; greeters only have phones.
6. **Data plane separation.** Scheduled syncs and mirrors are Python jobs
   in `gc3-sermon-library`. The app reads Supabase and calls PCO only for
   interactive writes (creating or promoting a workflow card).
7. **PCO boundary.** Pursuit replaces PCO *Workflows* (mirror, then
   native, then retire). PCO *People* remains the membership record and
   PCO *Check-Ins* remains the attendance source; Pursuit reads both and
   replaces neither.

## 3. Domain model: the five ships

A person's `ship` is a state machine. Congregation-facing names; staff
screens may show sub-stages.

| # | Ship | Meaning | Boarding marker |
|---|---|---|---|
| 1 | Friendship | first contact | lead captured (`meta_leads` row, PMV form, manual add) |
| 2 | Fellowship | showing up | first attendance recorded |
| 3 | Partnership | planted, committed | Growth Track complete OR covenant step OR joined a serving team (never a giving marker) |
| 4 | Discipleship | being formed | enrolled in formation track (Charisma Track), consistent serving, mentoring |
| 5 | Leadership | reproducing | Leader Track, leads a team or group |

- Sub-stages inside Friendship and Fellowship are the working board
  columns: `planned_visit`, `confirmed`, `attended`, `no_show`,
  `not_coming`, `returned`. These map 1:1 to the church's existing
  ChurchFunnels pipeline so staff relearn nothing.
- People can enter at any ship (a transfer member starts at Partnership).
- Ship moves are recorded as events, never destructive. Nobody is
  automated backward; demotion is a human action with a reason.
- Automation density decreases by ship: heavy at Friendship
  (confirmations, reminders), light at Fellowship, celebration-only at
  Partnership, human-task-only at Discipleship, none at Leadership.

## 4. New data model

All tables RLS-enabled. Sketches; refine types as needed but keep names.

```sql
-- The unification spine: one row per human being.
create table people (
  id uuid primary key default gen_random_uuid(),
  first_name text, last_name text, display_name text,
  email text, phone text,                  -- primary contact
  pco_person_id text unique,               -- Planning Center People
  ghl_contact_id text,                     -- ChurchFunnels (transition)
  gt_profile_id uuid,                      -- Growth Track profile
  auth_user_id uuid,                       -- intranet account if any
  ship text not null default 'friendship', -- current ship
  ship_boarded_at timestamptz,
  photo_url text,
  created_at timestamptz default now()
);

-- Cards on the Board (one live card per person in the chase).
create table cards (
  id uuid primary key default gen_random_uuid(),
  person_id uuid references people not null,
  stage text not null default 'planned_visit',
  planned_for date,                        -- the Sunday they picked
  source text,                             -- meta_form | landing | manychat | walk_in | manual
  meta_leadgen_id text,                    -- join to meta_leads
  campaign_id text, ad_id text,            -- attribution
  assigned_to uuid,                        -- user_id
  stage_changed_at timestamptz default now(),
  archived boolean default false,
  created_at timestamptz default now()
);

create table stage_events (               -- every move, forever
  id bigint generated always as identity primary key,
  card_id uuid references cards, person_id uuid references people,
  from_stage text, to_stage text, from_ship text, to_ship text,
  moved_by uuid, reason text, created_at timestamptz default now()
);

create table touches (                    -- human contact log, two-tap entry
  id bigint generated always as identity primary key,
  person_id uuid references people not null,
  kind text not null,                     -- called | texted | met | prayed | note
  note text, by_user uuid, created_at timestamptz default now()
);

create table tasks (
  id uuid primary key default gen_random_uuid(),
  person_id uuid references people,
  title text not null, detail text,
  assigned_to uuid, due_on date,
  source text,                            -- strategy | workflow | manual
  source_id uuid,
  done_at timestamptz, created_at timestamptz default now()
);

create table ship_goals (                 -- PD sets these per season
  id bigint generated always as identity primary key,
  ship text not null, metric text not null,   -- e.g. show_rate, planned_per_month
  target numeric not null, season text,       -- e.g. '2026-Q4'
  unique (ship, metric, season)
);

-- Strategies: member-facing sequences. They COMPILE to Pathways.
create table strategies (
  id uuid primary key default gen_random_uuid(),
  name text not null, ship text not null,
  trigger text not null,                  -- e.g. card_created, stage=no_show
  enabled boolean default false,
  created_at timestamptz default now()
);
create table strategy_steps (
  id uuid primary key default gen_random_uuid(),
  strategy_id uuid references strategies not null,
  position int not null,
  kind text not null,       -- pathway_email | human_task | wait | pco_workflow_card | branch
  config jsonb not null,    -- wait: {days}; email: {pathway_key, subject, body}; etc.
  enabled boolean default true
);

-- Native workflows (the PCO Workflows replacement).
create table wf_workflows (
  id uuid primary key default gen_random_uuid(),
  name text not null, description text,
  pco_workflow_id text,                   -- if imported from PCO
  active boolean default true
);
create table wf_steps (
  id uuid primary key default gen_random_uuid(),
  workflow_id uuid references wf_workflows not null,
  position int not null, name text not null,
  default_assignee uuid, sla_days int
);
create table wf_cards (
  id uuid primary key default gen_random_uuid(),
  workflow_id uuid references wf_workflows not null,
  step_id uuid references wf_steps,
  person_id uuid references people not null,
  assigned_to uuid, due_on date, status text default 'open',
  pco_card_id text,                       -- during mirror phase
  created_at timestamptz default now()
);

-- PCO mirrors (filled by the data plane).
create table pco_workflows_mirror (pco_id text primary key, name text, steps jsonb, synced_at timestamptz);
create table pco_workflow_cards_mirror (pco_card_id text primary key, pco_workflow_id text, pco_person_id text, step text, assignee text, synced_at timestamptz);
create table pco_checkins (pco_checkin_id text primary key, pco_person_id text, checked_in_at timestamptz, event_name text, one_time_guest boolean, synced_at timestamptz);
```

**Identity resolution** (a data-plane job plus in-app merge): match
`meta_leads`, `ghl_opportunities`, `gt_profiles`, PCO people, and check-ins
into `people` by (1) `pco_person_id`, (2) exact email, (3) normalized
phone, (4) name + planned date proximity as a suggestion only. Ambiguous
matches surface in an admin merge queue; the merge tool rewrites foreign
keys and keeps an audit trail. Never auto-merge on name alone.

## 5. The app: fifteen rooms

Roles come from the existing `roles` / `user_roles`. Define at minimum:
`pursuit_admin`, `ship_captain` (scoped to a ship), `ministry_leader`
(scoped to workflows), `greeter`. Lead Pastor holds admin.

**Daily wing**
1. **Home (My Day)**: role-aware landing. My tasks due, my people who
   moved or went quiet, this Sunday's expected count. PD's home adds the
   personal-touch queue and vital-sign deltas.
2. **The Board**: kanban of `cards` by stage. Desktop: dnd-kit drag
   between columns. Phone: one column at a time, horizontal stage swipe,
   long-press opens a move sheet. Supabase realtime keeps two staffers in
   sync. Saved filters (smart lists), bulk assign, search.
3. **People**: directory over `people` with search. Person page = the
   Person Card: journey timeline assembled from `meta_leads` (the ad and
   form), `pathway_sends` + `email_clicks` (what the house sent, opened),
   `touches`, `stage_events`, `pco_checkins` (Sundays), `gt_progress`
   (Growth Track), `wf_cards`. Notes, tags, assignment, merge suggestion
   banner. NO giving data, ever.
4. **Sunday**: list of cards with `planned_for` = today plus recent
   no-shows. One giant "They Are Here" button writes attendance
   (stage to `attended`, event logged) optimistically and offline-tolerant
   (queue writes, flush on reconnect). Ten-second walk-in add: name +
   phone, creates person + card with `source = 'walk_in'`. The nightly
   data-plane job reconciles against `pco_checkins` and catches misses.
5. **Tasks**: my queue across strategies, workflows, and manual tasks.
   Tap-to-call and tap-to-text open the phone's dialer and SMS composer
   (no automated sending).

**Fleet wing**
6-10. **Ship rooms** (one route per ship): the goal vs actual
   (`ship_goals` against computed metrics), that ship's board slice, its
   strategies, its crew and their queues. Captains land here.

**Engine wing**
11. **Strategies**: list per ship; sequence editor (vertical step list,
    v1) with step kinds: pathway email (edited against house style),
    wait N days, human task, create PCO/native workflow card, branch on
    signal (attended or not). Enabling a strategy writes the pathway
    rules and templates the Pathways engine executes; Pursuit stores the
    definition, the engine owns delivery. Ship with three templates: Plan
    My Visit, Event follow-up, No-show revival. Test mode sends only to a
    staff address through the engine's existing test facility. A React
    Flow canvas replaces the vertical editor in Phase D.
12. **Workflows**: mirror view of PCO workflows first (read-only cards on
    people), then native `wf_*` CRUD with per-step assignees and SLAs,
    then a PCO import (definitions to `wf_workflows`) and retirement.
13. **Reach**: read-only analytics over `meta_ad_insights`, `meta_leads`,
    `cards`: cost per lead, cost per attended person by campaign, form
    health (leads collected vs cards created per form per week, alarm on
    gaps), weekly agency scorecard.

**Leadership wing**
14. **Vital Signs**: seven tiles with 8-week trends and a fleet view
    (count per ship, moved-up this month). Definitions:
    online attendance = distinct `live_here` + stream stats;
    in-person = `pco_checkins` weekly distinct; financial = aggregates
    from `giving_gifts` (leadership-only); reach = leads and cost from
    `meta_*`; discipleship = `gt_progress` completions + ship moves up;
    volunteering = active in `pco_serving`; next steps = pathway sends,
    opens, clicks, stage moves. Show rate = cards reaching `attended`
    within 21 days of `planned_for`, per campaign and overall.
15. **Admin**: role grants, stage and ship config, goals editor,
    integration health (last sync times per source), audit log
    (`stage_events` + merges), link to `/admin/pathways` for switches.

**Everywhere**: global search, quick-log touch, notes, CSV export,
push notifications (reuse the intranet's `push_subscriptions`) for "task
assigned", "your person attended", "strategy stalled".

## 6. Tech directives

- Next.js App Router inside `gc3-intranet`; follow that repo's existing
  conventions (styling, auth helpers, component patterns) over anything
  in this spec.
- dnd-kit for the board; React Flow only in Phase D; Supabase realtime
  channels on `cards`; optimistic UI with server reconciliation.
- All writes through server actions or API routes using the service role;
  client gets role-filtered reads via RLS policies keyed on `user_roles`.
- PWA manifest + offline queue for the Sunday screen.
- Seed/migration SQL lives in the repo and is applied to the one project.

## 7. Phases and acceptance

**Phase A, see everything.** `people` spine + identity resolution job;
Board and Person Card read-only; Reach; Vital Signs v1. Accept: a staffer
finds any real person from `meta_leads`/`ghl_opportunities` and sees their
ad source, sends, and history on one card; the board shows live cards by
stage; no writes yet.

**Phase B, work the board.** Drag moves stages (events logged), notes,
touches, tasks, Sunday mode with walk-in add, assignments, realtime.
Accept: a greeter with only the `greeter` role can mark arrivals on a
phone with airplane-mode tolerance; a captain can work a full Sunday
without opening ChurchFunnels.

**Phase C, strategies.** Sequence editor compiling to Pathways; the three
templates live behind the engine's switches; per-strategy results.
Accept: enabling Plan My Visit sends the confirm email through the
Pathways engine (visible in `pathway_sends` with unsubscribe), and
disabling it at `/admin/pathways` stops it without touching Pursuit.

**Phase D, replace and extend.** Native workflows + PCO import + PCO
Workflows retired; ship goals and captain rooms complete; React Flow
canvas; ChurchFunnels cutover (final export, cancel subscription).
Accept: every live process runs in exactly one system and that system is
the house's.

## 8. Do not build

- Any direct email/SMS/DM sending, or any second sending system.
- Any giving display outside leadership aggregates.
- Member-facing UI (Pursuit is staff-only; members never log into it).
- A replacement for PCO People, PCO Check-Ins, or PCO Services.
- Automated ship demotion, automated discipleship or leadership nudges.
- Custom Audience export or any transfer of person data to ad platforms.

## 9. Open items for the builder to confirm with PD

- Charisma Track and Leader Track data sources (tables do not exist yet;
  Discipleship and Leadership boarding markers will need them or a manual
  flag in the interim).
- The exact covenant-step record for Partnership boarding.
- Which staff hold which roles at launch, and the captain per ship.
- SMS (A2P registration, consent capture) is explicitly out of scope
  until PD approves it as a separate decision.
