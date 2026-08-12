# GC3 Visit Module: filling and owning the funnel

*Status: the weekly ads scoreboard (`meta_ads_report.py`) and the era
diagnostic (`meta_ads_history.py`) are built and sit in PR #7 waiting on
the two META_ secrets. Everything else here is planned, not built.*

## The situation, stated plainly

GC3 pays for ChurchFunnels independently. The funnel, its workflows, and
every contact in it are already the house's, and they survived the agency
switch. What did not survive is **volume**: with Church Candy running the
ads, a lot more people were being funneled into it than are arriving now
under Creative Church Marketing.

So this is not a rebuild-the-funnel problem. It is two problems, in order:

1. **Top of funnel: the ads are not filling it the way they used to.**
   Diagnose why, then fix it, whether that means directing the new agency or
   running the plays ourselves.
2. **Ownership of the measurement: nobody on our side can currently see, in
   one place, which ad produced which lead, what each seat cost, and whether
   the new agency is earning its fee.** That layer is what we build, and it
   is agency-proof: it keeps working no matter who runs the ads.

And one more fact that shapes the whole design: **a recent Sunday brought 36
first-time guests.** Guests arrive through more doors than the ad funnel
(friends, drive-bys, Instagram, God's own scheduling), and most of them
never fill out a Plan Your Visit form. A module that only sees form-fillers
would miss most of the harvest. So the attendance side of this plan reads
from where the house already records people on Sunday: Planning Center.

**The principle stands: agencies rent us reach. The funnel, the data, and
the scoreboard are the house's, permanently.**

## Why the volume probably dropped (ranked, from the research)

Church Candy's system, deconstructed: personalized invitation ads built from
the church's own photos and video, targeted a few miles around the building,
pointed at a **Meta instant form** (Plan Your Visit, prefilled by Facebook,
filled without leaving the app), feeding an automated
confirmation-and-reminder sequence in ChurchFunnels, with a retargeting
layer warming everyone who watched the videos. ChurchFunnels itself is a
white-labeled GoHighLevel CRM, and Church Candy built its whole model on
that integration working end to end.

The likely causes of the drop, most probable first:

1. **Objective and form type.** Lead-objective campaigns with instant forms
   produce several times the lead volume of traffic campaigns pointed at a
   landing page. If Creative Church Marketing is running traffic, awareness,
   or engagement objectives, or sending clicks to a page with a form on it,
   volume falls off a cliff even at identical spend.
2. **The Meta-to-ChurchFunnels connection may have broken at handoff.**
   Checked with PD: new Facebook leads still land in ChurchFunnels today,
   just not many. The pipe is alive; the drop is upstream, in what the ads
   are buying. This cause is downgraded, which concentrates the diagnosis
   on the causes above and below.
3. **Spend and campaign mix.** Same dollars split across more objectives
   (video views, brand awareness) means fewer dollars buying leads.
4. **Creative style.** The personal-invite look (real faces, phone-shot
   video, "we saved you a seat") out-pulls polished brand creative for this
   job.
5. **No retargeting layer.** Cold audiences only, with no warm middle, makes
   every lead a first-touch lead, and first-touch leads cost more.

Industry calibration: $3 to $20 per lead; $500 to $1,000 a month typically
produces 30 to 90 planned visits a month. If current numbers are far off
that, the cause is on the list above.

## Diagnosis before prescriptions (Phase 0, mostly reading data we already own)

1. **The ChurchFunnels contact timeline.** Contacts in GoHighLevel carry
   created-at dates and sources. Chart monthly new contacts from Facebook
   for the last 18 to 24 months and mark the agency transition. That is the
   ground-truth volume curve, and it tells us the size of the gap we are
   closing.
2. **Ad account history.** Confirmed: the Church Candy era ads ran in OUR
   ad account, so Meta's roughly 37 months of insights cover both eras.
   **Built:** `meta_ads_history.py` (Actions tab > Meta ads history
   diagnostic) pulls monthly campaign history and renders spend, leads,
   cost per lead, and objective mix by era; give it the handoff date and it
   compares before and after directly. It needs only the same two META_
   secrets as the weekly report.
3. **The lead-flow audit.** Confirmed with PD: leads still arrive in
   ChurchFunnels, at low volume. Remaining check, worth five minutes: is
   the arriving trickle everything Meta captures, or a subset? The
   history report's monthly lead counts against ChurchFunnels' contact
   timeline settles it.
4. **What is Creative Church Marketing actually running?** The weekly ads
   report built in this repo already answers this from the API: objectives,
   spend, results by type. Its first live run is the audit.

## The map

```mermaid
flowchart TD
    subgraph DOORS ["Front doors"]
        A["Meta ad: personal invitation,<br/>lead objective"]
        B["Instant form: Plan Your Visit"]
        R["Sermon clips and reels<br/>(the library already makes the raw material)"]
        M["ManyChat: comment VISIT,<br/>DM flow collects contact<br/>(optional, later phase)"]
        A --> B
        R --> M
    end

    subgraph FLOW ["Lead flow (owned by GC3)"]
        C["ChurchFunnels (our GoHighLevel)<br/>workflow: confirm, remind, follow up"]
        D["Edge Function mirror<br/>lead + attribution"]
        E[("visit_plans table<br/>Supabase")]
        B -- "GHL Facebook integration<br/>(audit and rewire if broken)" --> C
        B -- "leadgen webhook" --> D
        M -- "External Request webhook" --> D
        M --> C
        D --> E
    end

    subgraph SUNDAY ["Sunday: attendance truth"]
        P["Planning Center<br/>Check-Ins + People:<br/>every FTG, planned or walk-in"]
    end

    subgraph MEASURE ["Scoreboard (this repo, weekly)"]
        F[("meta_ad_insights<br/>already collecting")]
        G["PCO read: FTG count, matched<br/>to planned visits, walk-in share"]
        H["Cost per lead, show rate,<br/>cost per guest in a seat, PER AD"]
        I["Monday digest: FTG source mix,<br/>volume vs the Church Candy baseline,<br/>who is coming Sunday, PD's texts"]
        P --> G
        F --> H
        E --> H
        G --> H
        H --> I
        E --> I
    end

    C --> P
    P --> L["Bridge to GATHER<br/>(Growth Track / Journeys)"]
```

ChurchFunnels keeps its job: it is paid for, it works, and the staff knows
it. What gets added around it is the attribution mirror (so every lead is
also in our Supabase, stamped with the ad that produced it) and the
scoreboard (so ad spend and seats connect in one weekly view). If the house
ever wants follow-up moved into the Pathways engine in gc3-intranet, that
becomes a clean migration later, because the leads already land in our
table; it is an option in Phase 4, not a prerequisite for anything.

## The data model

One new table, `visit_plans`, in the same Supabase project. Sketch:

```sql
create table visit_plans (
  id uuid primary key default gen_random_uuid(),
  -- who
  first_name text, last_name text, email text, phone text,
  party_notes text,
  -- what they planned
  planned_for date,
  -- where they came from (the attribution that makes ads measurable)
  source text not null,                -- meta_form | landing_page | manychat | manual
  leadgen_id text unique,              -- Meta's lead id, dedupe key
  ad_id text, adset_id text, campaign_id text,
  utm_source text, utm_medium text, utm_campaign text, utm_content text,
  -- consent, captured at the form
  email_consent boolean not null default false,
  sms_consent boolean not null default false,
  -- lifecycle
  status text not null default 'planned',
     -- planned -> confirmed -> attended | no_show -> returned
  attended_on date,
  ghl_contact_id text,                 -- the same person in ChurchFunnels
  pco_person_id text,                  -- the same person in Planning Center
  notes text,
  created_at timestamptz not null default now()
);
```

`ad_id` joins to `meta_ad_insights` (already collecting weekly). That join
produces the number no agency report shows: **dollars per person actually
in a seat, per ad**. `ghl_contact_id` ties the Supabase row to the
ChurchFunnels contact, and `pco_person_id` ties it to Planning Center, so a
person is one person across all three systems. This repo already does
exactly this kind of matching for donors (Giving hands back a person id,
People fills in the name and email); the visit module reuses the same
client, the same credentials, and the same rate-limit handling.

## What lives where (the house rules, applied)

| Piece | Lives in | Why |
|---|---|---|
| Ads, creative, targeting | Creative Church Marketing, in OUR ad account | Their craft, our account. Partner access, revocable. |
| Visitor follow-up workflow | ChurchFunnels (our GoHighLevel) | Already paid for, already working. Nothing to rebuild today. |
| Lead mirror + `visit_plans` | Supabase (Edge Function + table) | Real-time endpoint; this repo is scheduled jobs only. |
| Attendance truth (who actually came) | Planning Center (Check-Ins + People) | Where the house already records people on Sunday. Read-only from this repo, with the credentials and client the giving sync already uses. |
| Comment and DM capture (optional, later) | ManyChat | Capture only. Its External Request webhook hands every contact to the mirror and to ChurchFunnels. It does not run follow-up sequences: the house does not need a fourth thing that messages people. |
| Weekly scoreboard, digest, history pulls | This repo | Scheduled, read-and-report, emails only PD. Its lane. |
| PD's personal text to each planner | A human | Prompted by the digest. Not automated, on purpose. |
| Follow-up via Pathways engine | gc3-intranet, **only if migrated later** | If ChurchFunnels is ever dropped, member-facing email goes there and nowhere else. Nothing in this repo sends to a member. |

## Phases

**Phase 0: diagnose (days, not weeks)**
- ChurchFunnels contact timeline: the volume curve, before and after the
  switch.
- Ad account history pull (if the history is in our account): a one-time
  era-comparison script alongside the weekly ads report.
- Lead-flow audit: test lead in, confirm it reaches ChurchFunnels and
  enters the workflow; fix or rewire the GHL Facebook integration if it
  broke at handoff.
- Read Creative Church Marketing's current campaigns from the API (the
  weekly ads report's first live run).

**Phase 1: restore volume (the playbook, run by CCM or by us)**
- Lead objective, instant forms, one custom question for intent.
- Personal-invite creative from real congregation photos and phone video,
  refreshed on the fatigue signals the ads report already flags.
- Tight radius targeting; a retargeting layer on video viewers.
- Budget concentrated on lead campaigns, calibrated against the $3 to $20
  per-lead benchmark and our own baseline from Phase 0.
- Weekly: hold results against the Church Candy baseline in the digest.

**Phase 2: the attribution mirror**
- `visit_plans` table plus the Meta leadgen webhook Edge Function, stamping
  every lead with its ad. ChurchFunnels keeps receiving leads exactly as it
  does today; the mirror is additive.
- Daily backstop poller in this repo (webhooks fail quietly; the poller is
  the net).
- Digest gains: visits planned this week, and which ad produced each.

**Phase 3: close the loop with Planning Center**
- Weekly read of PCO Check-Ins (the API marks each check-in with a
  `one_time_guest` flag and links it to a person) plus new People profiles,
  using the credentials and rate-limited client the giving sync already
  runs on. First-time guests are derived from the house's own records, not
  hand-counted: the digest reports the FTG number every Monday.
- Match FTGs to `visit_plans` by email and phone: matched means attended
  (show rate, per ad); unmatched planned visitors mean no-shows (the warm
  re-invite in ChurchFunnels); unmatched FTGs mean walk-ins, which the
  digest reports as the source mix ("36 FTGs: 9 from ads, 27 walk-ins").
  The walk-in share is a number worth watching on its own: it says how much
  of the harvest the ads can and cannot claim.
- Optionally, a read-only pull from the GoHighLevel API (new contacts,
  workflow stage movement) to confirm the funnel side of the same story.
- The digest and ads report gain cost per planned visit, show rate, and
  cost per attended guest, per ad. This is the scoreboard the agency is
  held to.
- Attended guests surface as GATHER candidates (Journeys). Walk-in FTGs
  captured in PCO get the same bridge: nobody's next step depends on which
  door they came through.

**Phase 4: options, each a deliberate PD decision, none required**
- ManyChat as a second front door. Sermon clips and reels (this repo
  already produces the raw material weekly) post with "comment VISIT" and a
  ManyChat flow answers the comment, collects name and contact in the DM,
  then hands off: its External Request webhook (a Pro-plan feature) posts
  the contact to our Edge Function mirror and into ChurchFunnels. Capture
  only; follow-up stays where follow-up lives. This earns its subscription
  only once clips are posting consistently and Phases 0 to 2 are done, and
  it works with organic reach before a dollar of ad spend touches it.
- Migrate follow-up from ChurchFunnels into a `plan_my_visit` Pathway in
  gc3-intranet (drops a subscription, gains the house switch, suppression
  list, unsubscribe, and house-style copy). The mirror makes this a clean
  cutover whenever it is wanted.
- Automated SMS under our own number (A2P 10DLC, express consent on the
  form, replies routed to a person).
- Conversions API: send "attended" back to Meta, hashed, only for people
  who came through an ad, so Meta optimizes for people who show up rather
  than people who fill forms.
- Lookalike seed audiences: hand-approved list or not at all.

## The scoreboard (what we will finally be able to see)

| Stage | Metric | Today | After Phase 3 |
|---|---|---|---|
| Ad seen | impressions, CTR, spend | in `meta_ad_insights` now | same |
| Hand raised | cost per lead, volume vs baseline | agency reports it | ours, per ad, era-compared |
| Visit planned | planned visits per week | in ChurchFunnels only | mirrored in `visit_plans` |
| Seat filled | show rate, cost per guest | nobody joins it to spend | **the headline number** |
| FTG source mix | ads vs walk-ins vs DMs, weekly | hand-counted ("36 on Sunday") | derived from PCO, every Monday |
| Came back | return rate | unknown | `status = returned` |
| Growing | GATHER starts from ads | unknown | joined to `gt_*` |

## Risks and their answers

- **The volume gap has more than one cause.** Phase 0 measures each lever
  separately (objective mix, integration health, spend, creative) instead
  of guessing.
- **Webhooks miss.** The daily poller backstops them.
- **Tokens expire.** System User token, same rule as the ads report.
- **Instant-form leads can be low intent.** One custom question adds
  friction; the show-rate metric settles the instant-form versus
  landing-page argument with our own data.
- **A second emailing system grows here by accident.** It will not: the
  rule stands, follow-up lives in ChurchFunnels (or someday the Pathways
  engine), and this repo's `send_email` still refuses every address but
  PD's.
- **Agency churn, again.** After Phase 2, switching agencies means changing
  partner access on the ad account. The leads, the history, and the
  scoreboard do not move.

## What this needs from PD (decisions, not work)

1. ~~Confirm where the Church Candy era ads ran.~~ Answered: ours, no
   doubt. The history diagnostic is built on the strength of it.
2. ~~Confirm ChurchFunnels still receives new Facebook leads.~~ Answered:
   yes, but not a lot. The pipe is alive; the diagnosis moves upstream.
3. How the 36 FTGs got recorded: Check-Ins, connect cards, People entries,
   or a headcount. If they are in Planning Center in any form, Phase 3
   reads them as is; if they are on paper, the fix is getting them entered
   (kids Check-Ins alone usually catches most families).
4. A yes to the phase order, or a reorder.
5. Phase 4 calls (ManyChat, Pathways migration, SMS, Conversions API) when
   we get there, not before.

## Sources

- [ChurchCandy: church funnels service page](https://churchcandy.com/services/grow-your-church-with-proven-church-funnels/)
- [ChurchCandy: Facebook ads for churches strategy](https://churchcandy.com/facebook-ads-for-churches-your-outreach-strategy/)
- [GoHighLevel case study: ChurchCandy built on white-label HighLevel](https://www.gohighlevel.com/case-study-brady-sticker)
- [Creative Church Marketing](https://creativechurchmarketing.com/)
- [Meta: retrieving leads](https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/lead-ads/retrieving)
- [Meta: webhooks for lead ads](https://developers.facebook.com/documentation/ads-commerce/marketing-api/guides/lead-ads/quickstart/webhooks-integration)
- [Meta: leadgen webhooks setup](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-leadgen/)
- [Planning Center Check-Ins API: the CheckIn resource and its one_time_guest flag](https://api.planningcenteronline.com/docs/apps/check-ins/versions/2025-05-28/vertices/check_in)
- [ManyChat External Request webhook for sending lead data out](https://leadsbridge.com/documentation/manychat/webhook/)
- [Adrize: Facebook lead ads for churches, benchmarks](https://adrizedigital.com/blog/facebook-lead-ads-for-churches/)
- [Text In Church: guest follow-up timing](https://textinchurch.com/blog-posts/church-guest-follow-up-plan)
- [Vers Creative: first month of church ads expectations](https://www.verscreative.com/post/what-to-expect-from-your-first-month-running-church-ads)
