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

## Seeing and announcing are different things

PD's ruling: **nothing is untouchable. The system may see everything. It
just does not announce it.**

That settles a question this project had been answering too bluntly. The
2026-08-05 incident was never really about a job *reading* the giving
table. It was about a job that read it and then **acted outward**, mailing
30 donors an invitation triggered by their generosity, with no switch and no
unsubscribe. The sin was the announcement, not the sight.

So the line moves to where it always belonged:

- **The resolver sees everything.** Giving frequency, recency, consistency,
  attendance, serving, every signal the house has. It needs all of it to
  answer "who is who" honestly.
- **The interface is discreet.** Amounts never render on a card. A
  giving-derived reason reads as "gives consistently", not a number, and
  full detail is gated to leadership roles rather than shown to whoever is
  holding a phone at the welcome desk.
- **Nothing outward is ever triggered by giving.** No email, no text, no
  pathway enrolment keyed to what somebody put in the plate. That remains
  the Pathways engine's business, with its switch and its suppression list,
  and it is the one part of the old rule that stays absolute.

A useful test for any future feature: *would this embarrass the person if
they saw it over a shoulder?* Seeing that somebody is a faithful partner
passes. Seeing what they gave, in a lobby, does not.

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

### The line between the first two ships

PD's rule, and it is the cleanest boundary in the system: **a Planning
Center record is the border.**

- **Friendship** is everybody the house knows *about*. A name, a hand
  raised, no record in the church's system yet.
- **Fellowship** is everybody the house has *entered*. Once a person exists
  in Planning Center, they are aboard, whatever else is or is not true
  about them.

That boundary is worth keeping because it maps to a real moment somebody
performed: the house decided this person is a person, not a lead, and made
them a record. It also means the promotion from Friendship to Fellowship
happens on its own, the first time a guest checks in, gives, or gets typed
into PCO by a staff member.

### Friendship: known to the house, not yet in Planning Center

| # | Rule | Source | Status |
|---|---|---|---|
| F1 | Submitted a Plan My Visit form | `meta_leads`, `ghl_opportunities` | PD |
| F2 | Registered for one event | PCO Registrations | PD |
| F3 | Came in as an ad lead | `meta_leads` | built |
| F4 | Sent a prayer request or connect card | `wall_prayers`, PCO forms | proposed |
| F5 | Reached out by DM or chat | ManyChat, later | proposed |
| F6 | Was invited by a member (referral named) | PCO field | proposed |

Every one of these is Friendship **only while no PCO record exists**. The
moment one does, they board Fellowship.

### Fellowship: has a Planning Center record

| # | Rule | Source | Status |
|---|---|---|---|
| L0 | **Has a PCO record at all.** The floor. | PCO People | PD |
| L1 | A visitor or first-time guest | PCO People | PD |
| L2 | Gave, but under the Partnership bar | `giving_gifts` | PD |
| L3 | Checked in to any service | PCO Check-Ins | proposed |
| L4 | Came back within 30 days of a first visit | PCO Check-Ins | proposed |
| L5 | Tapped "I'm here" on a livestream | `live_here` | proposed |

L0 makes the other rules in this section descriptive rather than decisive:
they no longer have to earn Fellowship, because the record already did. They
still matter, because they are what the dormancy flag and the Partnership
rules read.

L4 is still worth naming on its own. The second visit is where a guest
becomes a person who comes here, and it is the number the house should watch
hardest even though it no longer changes a ship.

**What this does to the fleet.** Fellowship becomes the largest ship by far:
giving alone knows 3,340 people, and the full PCO roster is larger still.
That is the honest shape of a church, and it makes two things true at once.
The good: the board finally holds everybody, which is what PD asked for. The
demanding: **a number that large is meaningless without the dormancy flag
below.** "4,000 in Fellowship" says nothing. "4,000 in Fellowship, 1,100 of
them seen this year" is a report a pastor can actually act on.

### Partnership: planted and committed

| # | Rule | Source | Status |
|---|---|---|---|
| P1 | PCO membership status is Member or Partner | PCO People | PD |
| P2 | Has a partnership date | PCO People | PD |
| P3 | Gave 10+ times in 24 months | `giving_gifts` | PD, see above |
| P4 | Their kids checked in 5+ times in 12 months | PCO Check-Ins + households | PD |
| P5 | Served 2+ times in 90 days | PCO Serving | PD |
| P6 | Finished Growth Track | `gt_progress` | built |
| P7 | Belongs to a small group | PCO Groups | proposed |
| P8 | Was baptized here | PCO, `salvation_decisions` | proposed |

**Attendance alone is not partnership.** PD's ruling, and it is the right
one: somebody who attends and never gives, never serves, never commits has
not partnered with the house. They have received from it. An earlier draft
of this document proposed making twelve visits a year enough on its own.
That rule is withdrawn.

The principle underneath every rule in this section: **a partner has given
the house something.** Money, time, a public commitment, their own
formation, or their children's. Presence by itself only ever receives, and
calling that partnership would flatter a number at the cost of the word.
Philippians 1:5 is *koinonia*, participation, not attendance.

### The list that ruling creates

Withdrawing the attendance rule does not throw those people away. It names
them, which is the more useful thing. A flag rides alongside Fellowship:

| # | Flag | Meaning |
|---|---|---|
| A1 | **Faithful, unattached** | 12+ check-ins in 12 months, no giving, no serving, no group, no Growth Track |
| A2 | **Half attached** | Regular attendance plus exactly one of giving, serving, or a group, but under every Partnership bar |
| A3 | **Gave once, stayed** | A single gift, still attending, never repeated |
| A4 | **Kids in, parents out** | Children check in regularly, no adult signal in the household |

A1 is the one PD actually asked for. These are the people who show up more
faithfully than most partners and have never been asked for anything. On the
old draft they would have been quietly counted as partners and never spoken
to again. Named honestly, they are the shortest path the house has to more
partners: they already come, they already like it here, nobody has invited
them into it.

A4 is worth its own line because it is the most common quiet miss in a
church with a strong kids ministry. The household is attending. The adults
are invisible to every rule the house has.

These flags never change a ship and never trigger anything outward. They
produce a list a campus pastor can work down on a Tuesday, which is the
whole point.

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

This is how a fleet of thousands stays honest, and with a PCO record now
being enough to board Fellowship, it stops being a nicety and becomes
load-bearing. Without it, both of the big ships turn into graveyards:
everyone who ever gave once or got typed into Planning Center, forever, and
the numbers stop meaning anything. With it, PD can ask the only question
that matters about a big number: **how many of these people did we actually
see this year?**

The fleet view should therefore never show a bare count. Every ship reads
"1,240 aboard, 380 seen this year", so the size of the house and the state
of the house arrive in the same glance.

## What has to be built

1. **PCO People sync**: the roster, membership status, partnership date,
   households, ordination. This alone takes the spine from hundreds to
   thousands.
2. **PCO Check-Ins sync**: attendance. Nine of the rules above are dark
   without it, including every Fellowship rule.
3. **PCO Groups sync**: membership and leadership of small groups.
4. **Giving frequency read**: the resolver reads it all; the card renders
   "gives consistently" and never a number.
5. **Rule engine**: evaluate all rules per person, take the highest ship,
   store the reasons, respect manual pins, set dormancy, set the A flags.
6. **Charisma Track and mentoring**: no data source exists yet. Until one
   does, D1 and D7 need a manual flag, which is the honest answer rather
   than a guess.

## The open questions only PD can answer

1. ~~Does the giving-frequency rule stand?~~ **Answered: yes.** The resolver
   sees everything; the interface stays discreet; nothing outward is ever
   triggered by giving.
2. ~~Is attendance alone enough for Partnership?~~ **Answered: no.** A
   partner has given the house something. Attendance without it becomes the
   A1 flag, not a ship.
3. ~~Should a bare PCO record appear on the board?~~ **Answered: yes, and it
   is Fellowship.** A Planning Center record is the border between the first
   two ships.
4. Is six months the right point to call somebody dormant, or is a church
   year (say ten months, which survives a summer away) truer?
5. Where does Charisma Track live, and can the resolver read it?
6. Who may pin a person's ship by hand?
7. What counts as "regular" for the A1 flag: twelve check-ins in a year, or
   something stricter like two a month for three months running?
