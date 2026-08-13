# Pursuit: the GC3 lead tracker

*The build PD asked for: "the ultimate lead tracker." Named Pursuit, because
GodChasers is a church named after pursuit, and the tool is where the house
chases people the way its people chase God. Cornerstone verse, Philippians
3:12: "I press on to take hold of that for which Christ Jesus took hold of
me." Tagline: because He chased us first. The kanban screen inside it is the
Board; in hallway speech, the Pursuit Board.*

*Status: plan only. The data plane it stands on (lead mirror, ads scoreboard,
attribution tables) is built or in PR #8; the app itself is not started.*

## What it is

A replacement for the ChurchFunnels UI, built into the house's own intranet:
the drag-and-drop leads board the team already likes, wrapped around the thing
ChurchFunnels can never have, **the whole person**. ChurchFunnels sees a form
fill. The house's database sees the ad that found them, the form they filled,
every email the Pathways engine sent and whether they opened it, the Sunday
they sat in a seat, their Growth Track steps, all of it, because it is all
already in one Supabase project.

Ground rules, from experience:

- **UI first, mobile first.** Staff live on phones. Every screen designs for
  a thumb before a mouse.
- **ChurchFunnels stays on until Pursuit reaches parity.** No gap like
  October 2025 ever again. The lead mirror feeds both during the transition.
- **Pursuit never sends member email itself.** Its automations orchestrate
  the Pathways engine, which already has the on and off switch, the shared
  suppression list, unsubscribe links, and the admin page. The 2026-08-05
  lesson is structural: one sender in the house, ever.
- **Giving data stays off lead cards entirely.** A guest's card shows their
  journey, never their money. God does the seeing.

## The spine: five ships, one fleet

The journey Pursuit tracks, named the way PD will preach it. Everyone is on
a ship; the house's job is to help them board the next one. Worship is not a
stage; it is the water the whole fleet sails on.

| Ship | Who is aboard | Boarding marker (data) | Automation posture |
|---|---|---|---|
| **Friendship** | First contact: the ad, the DM, the PMV form, the invited coworker | lead captured (`meta_leads` / `visit_plans`) | Heaviest: confirmations, reminders, re-invites. The machine's home turf. |
| **Fellowship** | Showing up, coming back | attended recorded (Sunday mode, PCO Check-Ins) | Light: after-visit thank you, a return nudge, then hands off to humans. |
| **Partnership** | Planted and committed to the house | Growth Track complete, covenant step taken, serving team joined. **Never a giving marker: a partner who gives quietly is seen by God, not by the software.** | Celebration sends only; enrollment into Discipleship invitations. |
| **Discipleship** | Being formed | Charisma Track, mentoring, serving consistently | Minimal: scheduling help and human tasks. Formation is hand to hand. |
| **Leadership** | Reproducing | Leader Track, leading a team or group | None toward the person; the system instead helps them start new Friendships. |

The fleet loops: Leadership's assignment is new Friendships, which turns the
journey from a pipe into an engine. People board at any ship (a transfer
member enters at Partnership without ever seeing an ad), stall without
falling off the map, and are never automated backward. The operational
sub-stages below (Planned a Visit, Attended, No Show) live inside Friendship
and Fellowship: the congregation hears ships, the staff screens keep the
precision. Philippians 1:5 anchors the third ship: "your partnership in the
gospel from the first day until now."

The design rule across the fleet: **the machine walks people to the door;
people walk people into the family.** Automation is dense at Friendship and
thins to nothing by Leadership.

### Three languages, one system

The fleet is one of three layers, each speaking to a different audience, and
the discipline is that each stays with its audience:

- **Ships** say where a person is. Congregation language; the only layer
  that gets preached.
- **Attract, Attach, Align, Adore** say what the house does to move people:
  Attract fills Friendship, Attach builds Fellowship, Align forges
  Partnership, and Adore is the deep water that carries Discipleship and
  Leadership. Staff language; each verb names a strategy playbook in
  Pursuit.
- **Attendance, Attention, Agreement, Allegiance** are the observable
  signals that someone may be ready for the next ship: they show up, they
  lean in, they buy the vision, they give their life to it. The software's
  language: Pursuit reads them from attendance records, opens and clicks,
  Growth Track enrollment, and serving commitment, and surfaces "may be
  ready" prompts to a human. Signals suggest; people invite.

### The instrument panel: seven vital signs

Church-level health on the leadership dashboard, distinct from any person's
card. Nearly every sign already has a source in the one database:

| Vital sign | Source | Status |
|---|---|---|
| 1. Online attendance | live-stream poller and "I'm here" taps (intranet), YouTube | partially flowing |
| 2. In-person attendance | PCO Check-Ins, Sunday mode | lands with the PCO loop |
| 3. Financial engagement | `giving_gifts`, **aggregate only**: totals, giver counts, recurring share. Never person-level in Pursuit. | flowing now |
| 4. Reach strategy | ads scoreboard (`meta_ad_insights`, `meta_leads`) | flowing now |
| 5. Discipleship strategy | `gt_*`, future tracks, fleet movement | flowing now |
| 6. Volunteer engagement | `pco_serving` | flowing now |
| 7. Next step engagement | `pathway_sends`, `email_clicks`, Pursuit stage moves | flowing now |

Five of seven are measurable today; the dashboard's job is to put them on
one screen with trend lines and let the Monday digest flag whichever sign
moved most.

## The unfair advantage (why build instead of rent)

One Supabase project already holds, or will after PR #8:

| Data | Table(s) | What the card shows with it |
|---|---|---|
| Which ad found them | `meta_leads` (ad, campaign, form) | "Came through PYV 2026, Reel #3" |
| Ad performance | `meta_ad_insights` | cost per person in this stage |
| What the house sent them | `pathway_sends`, `email_clicks` | "Opened Saturday reminder" |
| Whether they came | PCO Check-Ins (Phase 3 read) | "Attended Aug 10, kids checked in" |
| What they did next | `gt_profiles`, `gt_progress` | "Started GATHER" |
| Funnel history | `ghl_baseline_monthly`, opportunities import | two years of context |

Renting GoHighLevel means paying monthly to look at one slice of this through
a clunky window. Building means the church's own roles, the church's own
language, and every slice on one card.

## The product, screen by screen

**1. The Board.** Columns are the working sub-stages of Friendship and
Fellowship (Planned a Visit, Confirmed, Attended, No Show, Not Coming,
Returned), same mental model the team already has from ChurchFunnels, so
there is nothing to relearn. Cards carry name, the Sunday
they planned, a source chip (which campaign), days in stage, and three
one-tap actions: call, text, note. Web: drag cards between columns. Phone:
one column at a time, swipe between stages, long-press to move a card via a
bottom sheet. Filters in one row: This Sunday, campaign, assigned to, gone
quiet. Realtime: two staffers see each other's moves live (Supabase
realtime).

**2. The Person card.** Tap a card, get the journey, newest first: ad click,
form fill, each Pathway email with opened or clicked, personal touches
logged (a "texted them" button that takes two seconds on a phone), attended
Sundays, Growth Track milestones. Plus notes and assignment. This is the
"ultimate" part and it is mostly a query, because the data is already home.

**3. Sunday mode.** A greeter-friendly list of everyone expected today, big
photo-less cards, one giant button: They Are Here. Marks attended, moves the
card, feeds the scoreboard. Later the same list reconciles against PCO
Check-Ins automatically, so even unmarked attends get caught by the nightly
job. This screen is how 4.3% recorded attendance becomes a real number.

**4. Strategies.** The Church Candy playbook as editable sequences, run
through Pathways. Ships with three templates:
- *Plan My Visit*: instant confirm, Saturday reminder, Sunday morning text
  task for a human, after-visit thank you, no-show warm re-invite, day-7
  last touch.
- *Event follow-up* (the FIRE CONFERENCE kind): confirm, event reminder,
  after-event bridge to a Sunday.
- *No-show revival*: the 1,031-person warm list, gentle, spaced, capped.
Each step is a card in a vertical sequence: toggle it, edit its copy (house
style enforced: 60 to 90 words, Scripture after the point, the P.S. carries
the ask), change its wait. Version one is this sequence editor, which covers
everything Church Candy actually did. Version two is the full drag-and-drop
canvas (triggers, branches, conditions as nodes) once the sequences prove
out; building the canvas first is how products spend six months shipping
nothing.

**5. The Dashboard.** The Ads to Seats page, live: spend to leads to arrived
to seated to returned, per campaign, against the two-year baseline. Plus the
fleet view: how many aboard each ship, and who moved up this month, the
discipleship funnel no church software shows. The
artifact built on 2026-08-12 is the prototype; here it reads the tables
directly and updates itself.

**6. Tasks.** The personal-touch queue: who needs a text from PD today, who
a greeter should watch for, what fell out of a strategy for a human to
catch. Assignable, phone-first, tap-to-call.

## Where it lives and how it is built

```mermaid
flowchart LR
    subgraph JOBS ["gc3-sermon-library (data plane, scheduled)"]
        A["meta_leads mirror (daily)"]
        B["meta_ad_insights (weekly)"]
        C["PCO check-ins reconciler (Phase 3)"]
        D["Monday digest"]
    end
    subgraph DB ["Supabase (one project)"]
        E[("people + visit_plans<br/>stages, journeys")]
        F[("pathway_* tables")]
    end
    subgraph APP ["gc3-intranet (Pursuit UI + Pathways engine)"]
        G["Board / Person card / Sunday mode"]
        H["Strategies editor"]
        I["Live dashboard"]
        J["Pathways engine (the ONE sender)"]
    end
    A --> E
    B --> E
    C --> E
    E <--> G
    E --> I
    H --> F
    F --> J
    J --> E
    E --> D
```

- **App:** a section of gc3-intranet (Next.js), because auth, roles
  (`roles`, `user_roles`), profiles, and the Pathways engine already live
  there. Pursuit is routes and components, not a new deployment.
- **Drag and drop:** dnd-kit for the board (small, accessible, touch-solid).
  React Flow for the version-two canvas.
- **Realtime:** Supabase realtime on the cards table.
- **Roles:** staff see the board; greeters see Sunday mode only; giving data
  appears nowhere in Pursuit.
- **This repo stays the data plane:** mirrors, scoreboard, reconciler,
  digest. No UI here, no email to members here, same as always.

## Data model additions (sketch)

- `people`: the unification spine. One row per human, matched across
  `meta_leads` (email and phone), PCO person id, `gt_profiles`, ChurchFunnels
  contact id. Created by the ingest path and a nightly reconciler in this
  repo; merge tool in the UI for the inevitable duplicates.
- `visit_plans` (from the Visit Module plan): becomes the card table, gains
  `stage`, `assigned_to`, `stage_changed_at`.
- `lt_stage_events`: every stage move, who and when, so the funnel math and
  the audit trail are free.
- `lt_touches`: logged human touches (called, texted, met), two-tap entry.
- `strategy_*`: strategies and steps, compiled into `pathway_rules` and new
  pathway sequences so the Pathways engine executes everything member-facing.

## Phases (each one ships something the team uses)

**Phase A, see everything (fast):** the `people` spine, the Board and Person
card read-only over existing data (mirror, opportunities import, pathway
sends), plus the live dashboard route. No writes yet: the team looks at
Pursuit next to ChurchFunnels and feels the difference.

**Phase B, work the board:** drag to move stages, notes, touches, tasks,
Sunday mode with the big button. ChurchFunnels becomes the backup nobody
opens.

**Phase C, strategies:** the sequence editor compiling to Pathways, the
three templates live, the no-show revival run as its first campaign (with
PD's copy approval, per house style).

**Phase D, the canvas and the extras:** React Flow drag-and-drop workflow
builder, SMS steps (A2P registration and consent, a deliberate decision),
PCO auto-reconcile if not already landed, ManyChat front door if wanted.

**Cutover:** when B is stable and C covers the active sequences, export the
final ChurchFunnels state, import, point the lead mirror's downstream at
Pursuit alone, and the subscription ends. Not before.

## What this needs decided (PD)

1. A yes to the shape. The name is settled: Pursuit.
2. Who the users are for Phase A (PD plus who else, and what a greeter may
   see).
3. Attach the gc3-intranet repository to a working session so Phase A can
   start; that is where the app must be built.
4. Copy approval checkpoints for Phase C sequences (house style review).

## What deliberately does not change

Creative Church Marketing keeps running ads into the same instant forms. The
mirror keeps catching every lead daily. The Monday digest keeps arriving.
ChurchFunnels keeps working the whole time. Pursuit replaces the window, not
the plumbing, and the plumbing is already the house's.
