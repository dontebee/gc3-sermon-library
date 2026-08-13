# Pursuit: how a person lands on a ship

*The rule book the resolver runs on. PD set the first twelve; the rest are
proposed and marked as such. Nothing here is settled until PD says so.*

> Pursuit is a status board for every person God sends, guiding each gift
> through their journey with God and with GodChasers.
> God pursues the ONE. We are stewards of the ninety-nine.

## Why the list is hundreds and not thousands

The resolver currently reads Growth Track and serving only: 410 rows, 299
people. The house actually knows far more:

| Source | People | In the spine today |
|---|---|---|
| Giving (distinct PCO ids) | **3,340** | no |
| Given 10+ times in 24 months | **458** | no |
| PCO People roster | not synced | no |
| PCO Check-Ins | not synced | no |
| Serving | 309 | yes |
| Growth Track | 101 | yes |

Two things have to be built before any rule below can fire at full strength:
a **PCO People sync** (the roster, membership status, partnership date,
households) and a **PCO Check-Ins sync** (attendance, the single most
important missing signal). Both belong in the data plane, next to the
giving sync that already runs.

## The giving question, stated plainly

PD's rule 3 places someone on Partnership after 10 gifts in 2 years. Every
other document in this system says giving never touches Pursuit. That rule
was written after 2026-08-05, when a job read the giving table and mailed 30
donors an invitation nobody approved.

The distinction worth keeping is not "giving is untouchable" but **what
giving is allowed to do**:

- **Allowed (PD's call):** giving *frequency* as one signal among several
  that a person is planted. Somebody who has given consistently for two
  years is committed to the house, and pretending the house cannot see that
  is its own kind of dishonesty.
- **Still forbidden:** amounts anywhere near a card, giving as a reason a
  staff member can read as money, ranking people by generosity, and any
  member-facing message triggered by giving. Those remain the Pathways
  engine's business, with its switch and its suppression list.

**The safeguard:** a giving-derived placement stores its reason as
`committed_giving` and the card renders it as "a committed partner". No
count, no amount, no date. A greeter reading a card learns that somebody is
planted, never what they put in the plate. If that is still too close, the
rule can be dropped and the other Partnership signals carry it: with the
PCO membership sync in place, most of those 458 will qualify anyway.

## Precedence and mechanics

These govern every rule below.

1. **Highest ship wins.** Every rule is evaluated; the furthest ship any of
   them reaches is the person's ship.
2. **Never automatically demote.** If the evidence for Partnership goes
   quiet, the person stays on Partnership and gains `dormant_since`. This is
   pastoral, and it is also a safety rule: a person demoted to Friendship
   could be swept back into a "plan your visit" sequence, which is the
   2026-08-05 failure wearing a new coat.
3. **Every placement records why.** The reasons are stored as a list, so a
   card can say "Partnership: serves on Production, finished Growth Track"
   rather than asking anyone to trust the machine.
4. **A human pin beats every rule.** When a leader sets somebody's ship by
   hand, the resolver never moves them again, and the pin records who and
   when.
5. **Every rule has a window.** Two years, twelve months, ninety days. The
   fleet is meant to show where people are *now*, not everyone who ever
   passed through.
6. **Households roll up.** A four year old does not board a ship. Kids'
   check-ins credit the adults in their PCO household, which is what PD's
   kids rule actually means.

## The rules

### Friendship: first contact, no attendance yet

| # | Rule | Source | Status |
|---|---|---|---|
| F1 | Submitted a Plan My Visit form | `meta_leads`, `ghl_opportunities` | PD |
| F2 | Registered for one event | PCO Registrations | PD |
| F3 | Came in as an ad lead | `meta_leads` | built |
| F4 | Sent a prayer request or connect card | `wall_prayers`, PCO forms | proposed |
| F5 | Reached out by DM or chat | ManyChat, later | proposed |
| F6 | Was invited by a member (referral named) | PCO field | proposed |

A bare PCO record with no activity of any kind is **not** Friendship. It
goes in People with no ship until something happens, so the board is not
padded with names nobody is chasing.

### Fellowship: showing up

| # | Rule | Source | Status |
|---|---|---|---|
| L1 | Checked in to any service, once | PCO Check-Ins | proposed |
| L2 | Two or more check-ins in 90 days | PCO Check-Ins | proposed |
| L3 | Came back within 30 days of a first visit | PCO Check-Ins | proposed |
| L4 | Tapped "I'm here" on a livestream | `live_here` | proposed |
| L5 | Actually attended an event they registered for | PCO Check-Ins | proposed |

L3 is worth naming on its own. The second visit is where a guest becomes a
person who comes here, and it is the number the house should watch hardest.

### Partnership: planted and committed

| # | Rule | Source | Status |
|---|---|---|---|
| P1 | PCO membership status is Member or Partner | PCO People | PD |
| P2 | Has a partnership date | PCO People | PD |
| P3 | Gave 10+ times in 24 months | `giving_gifts` | PD, see above |
| P4 | Their kids checked in 5+ times in 12 months | PCO Check-Ins + households | PD |
| P5 | Served 2+ times in 90 days | PCO Serving | PD |
| P6 | Finished Growth Track | `gt_progress` | built |
| P7 | Attended 12+ times in 12 months without formal membership | PCO Check-Ins | proposed |
| P8 | Belongs to a small group | PCO Groups | proposed |
| P9 | Was baptized here | PCO, `salvation_decisions` | proposed |

P7 is the one most churches miss: the family who has been in the third row
for a year and never signed anything. They are partners in everything but
paperwork, and the house should treat them that way.

### Discipleship: being formed

| # | Rule | Source | Status |
|---|---|---|---|
| D1 | Enrolled in Charisma Track | no table yet | PD |
| D2 | Leads a small group | PCO Groups | PD |
| D3 | Signed into Growth Track 10+ times | `gt_activity` | PD |
| D4 | Served 12+ times in 12 months | PCO Serving | proposed |
| D5 | Serves on two or more teams | PCO Serving | proposed |
| D6 | Growth Track done **and** serving **and** in a group | combined | proposed |
| D7 | In a mentoring or discipleship pair | no table yet | proposed |
| D8 | Attended an equipping or leadership night | PCO Check-Ins | proposed |

D6 is the honest definition of formed: not one box ticked, but the three
that only happen together when somebody has actually given the house their
life. It is the rule to lean on until Charisma Track has a table.

### Leadership: reproducing

| # | Rule | Source | Status |
|---|---|---|---|
| E1 | Leads a team | `pco_team_roles` | PD |
| E2 | GLT, staff, or director | `user_roles`, PCO | PD |
| E3 | Coaches other small group leaders | PCO Groups | proposed |
| E4 | Ordained or licensed | PCO People | proposed |
| E5 | Elder, board, or campus pastor | `user_roles` | proposed |
| E6 | Owns a ministry in the Hub | `team_lead_access` | proposed |

Leadership takes no automation aimed at the person. What the system does
instead is help them start new Friendships, which is what closes the loop
and turns the fleet into an engine rather than a pipe.

### Dormancy: the state that is missing

Not a ship. A flag that rides alongside one.

| # | Rule | Meaning |
|---|---|---|
| Q1 | No attendance, serving, or giving in 6 months | `dormant_since` set |
| Q2 | Quiet 12 months | surfaces on a "go find them" list |
| Q3 | Any signal returns | flag clears, nothing else changes |

This is how a fleet of thousands stays honest. Without it, Partnership
becomes a graveyard: everyone who was ever planted, forever, and the number
stops meaning anything. With it, PD can ask the only question that matters
about a big number: **how many of these people did we actually see this
year?**

## What has to be built

1. **PCO People sync**: the roster, membership status, partnership date,
   households, ordination. This alone takes the spine from hundreds to
   thousands.
2. **PCO Check-Ins sync**: attendance. Nine of the rules above are dark
   without it, including every Fellowship rule.
3. **PCO Groups sync**: membership and leadership of small groups.
4. **Giving frequency read**: counts only, never amounts, behind PD's
   decision above.
5. **Rule engine**: evaluate all rules per person, take the highest ship,
   store the reasons, respect manual pins, set dormancy.
6. **Charisma Track and mentoring**: no data source exists yet. Until one
   does, D1 and D7 need a manual flag, which is the honest answer rather
   than a guess.

## The open questions only PD can answer

1. Does the giving-frequency rule stand, with the never-display safeguard?
2. Is P7 (12+ visits, no membership) right at twelve, or should it be more?
3. Should a bare PCO record with no activity appear on the board at all?
4. Where does Charisma Track live, and can the resolver read it?
5. Who may pin a person's ship by hand?
