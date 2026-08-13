# Pursuit: how a person lands on a ship

*The rule book the resolver runs on. Nothing here is settled until PD says
so.*

**Attribution, because a previous draft got this wrong.** Everything below
is tagged one of two ways:

- **PD** means PD said it, close to verbatim. Nothing else earns this tag.
- **proposed** means I inferred it, filled a gap, or picked a number PD has
  not picked. It is a suggestion wearing a rule's clothes.

An earlier draft took two of PD's questions, answered them itself, and
wrote the answers up as PD's rulings. That is the most expensive kind of
error a document like this can make, because the whole point of it is to be
the place where the house's actual decisions are recorded. Those two are
marked **proposed** now and are flagged in the open questions.

The structural fix is below: the rules move into a table PD can edit, so
this document stops being where the rules live and becomes only where the
reasoning lives.

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
demanding: **a number that large is meaningless without the state axis
below.** "4,000 in Fellowship" says nothing. "4,000 in Fellowship, 1,100 of
them active" is a report a pastor can actually act on.

### Partnership: Time, Talent, or Treasure

The house already had the words for this and I had been using five where
three would do. **A partner has given the house Time, Talent, or Treasure.**

Note the *or*. Any one of the three is enough. A widow who serves and cannot
give is a partner. A man who gives faithfully and travels for work is a
partner. The triad is deliberately generous about which one, and completely
unbending about whether there is one at all.

**Time** is showing up: registering kids, signing up for an event and
coming, saying "I will be there" and being there.
**Talent** is service to the house: serving teams.
**Treasure** is giving.

| # | Rule | Gives | Source | Status |
|---|---|---|---|---|
| P1 | PCO membership status is Member or Partner | the promise | PCO People | PD |
| P2 | Has a partnership date | the promise | PCO People | PD |
| P3 | Gave 10+ times in 24 months | **Treasure** | `giving_gifts` | PD |
| P4 | Their kids checked in 5+ times in 12 months | **Time** | PCO Check-Ins + households | PD |
| P5 | Served 2+ times in 90 days | **Talent** | PCO Serving | PD |
| P6 | Finished Growth Track | **Time** | `gt_progress` | built |
| P7 | Belongs to a small group | **Time** | PCO Groups | proposed |
| P8 | Was baptized here | the promise | PCO, `salvation_decisions` | proposed |
| P9 | Registered for and attended 3+ things in 12 months | **Time** | PCO Registrations + Check-Ins | proposed |

### Where Time and the attendance question collide, unresolved

**This section is `proposed`. PD has not ruled on it.** The previous draft
did rule on it, in PD's name, and that was wrong.

Here is the actual tension, stated without an answer attached.

PD said Time is showing up, and the examples given were: registering kids,
showing up to events, saying I will be there, **check-ins**. Check-ins were
on that list explicitly.

PD separately asked: *if people attend our church but do not give or serve,
we need to consider if they are a partner at all.* That was a question, and
the previous draft converted it into a ruling.

Both cannot stand unqualified. If a bare check-in is Time, and any one of
the three makes a partner, then attendance alone does make a partner, and
the question PD raised answers itself in the direction PD seemed to doubt.

Two ways out, and it is PD's call which:

**Option A, take the words literally.** Check-ins count as Time. Attendance
at a threshold is partnership. The question PD raised is then answered by
setting the bar high enough that a casual attender does not clear it, the
same way ten gifts in two years keeps a one-off giver out of Treasure.
Simple, consistent with the other two currencies, and it means a faithful
attender who gives nothing is a partner.

**Option B, narrow Time to committed showing up.** Time counts only where
something was promised in advance: a registration, an RSVP, a Growth Track
seat, a group that meets Tuesdays, your kids booked into a room week after
week. A walk-in check-in is presence but not a gift, because nobody was
counting on it. This keeps PD's doubt intact and keeps the withdrawn
twelve-visits rule withdrawn.

I lean to B, and I should say plainly that it is a lean and not a finding.
Three of PD's four examples happen to be commitments made in advance, which
is suggestive, but "check ins" was the fourth and it is right there in the
list. Reading it out because it spoils a tidy theory is exactly the move
that produced this section's correction.

Whichever wins, **each currency needs a bar, and that is a separate
question from which currency.** One gift of twenty dollars is not Treasure;
ten gifts in two years is. The triad names the ways in. The thresholds
separate a partner from a receiver, and every one of them belongs to PD.

**A public commitment is the promise of the three, which is why it counts
on its own.** A partnership date, a membership status, a baptism: none of
those is Time, Talent, or Treasure by itself. Each is a person saying "I am
in" before the evidence has had time to accumulate. The house takes people
at their word, so P1, P2 and P8 stand as rules rather than waiting for
proof. That is the right posture, and it is worth knowing it is a choice.

**On attendance alone.** `proposed`, not PD. What PD actually said was
*"if people attend our church but don't give or serve we need to consider
if they are a partner at all"*, which raises the question rather than
closing it. An earlier draft of this file wrote it up as a ruling, added
"the gift is not the body in the seat" as though PD had said that too, and
withdrew a rule on that authority. None of that was PD's.

Where it actually stands: the twelve-visits rule is **suspended pending the
Option A or B decision above**, not withdrawn by PD. The argument for
suspending it is that presence by itself only ever receives, and calling it
partnership flatters a number at the cost of the word. Philippians 1:5 is
*koinonia*, participation rather than attendance. That is an argument I
find good. It is not a decision anyone has made.

**A gap the previous draft invented, now closed.** That draft claimed
Talent had no signal of its own. That was an artefact of a wrong mapping,
not a real hole: **serving is the Talent signal**, cleanly, and the house
has it. All three are covered.

What remains is smaller and worth keeping in view. The house knows *who*
serves; it does not know *what they are good at*. PCO can hold skills on a
person's profile and nothing syncs them, so the resolver cannot tell
stacking chairs from running front of house. That is no longer a
classification problem, because both are Talent and both are partnership.
It is a deployment problem: nobody can ask "who has a gift we are not
using", which is the question a serving director actually needs.

### The list this creates either way

`proposed`. Useful under Option A or B, which is why it is worth having
before that decision lands: under B these people are not partners, and
under A most of them are partners the house has never spoken to. Either
way naming them beats losing them. A flag rides alongside Fellowship, and
the triad is what each flag counts:

| # | Flag | Meaning |
|---|---|---|
| A1 | **Faithful, unattached** | Comes most weeks. Never registered, never signed up, never served, never gave. **None of the three.** |
| A2 | **Half attached** | Gives **one of the three** but stays under its bar |
| A3 | **Gave once, stayed** | A single gift, still attending, never repeated |
| A4 | **Kids in, parents out** | Children check in regularly, no adult signal in the household |

A1 is the one PD actually asked for, and in the triad it reads sharply:
these are people who show up more faithfully than some partners and have
been asked for none of the three. On the old draft they would have been
quietly counted as partners and never spoken to again. Named honestly, they
are the shortest path the house has to more partners. They already come,
they already like it here, nobody has invited them into it.

A2 is the near miss, and it is the better list to work first. Somebody
already giving one of the three has answered the hard question. Asking for
a second is a smaller ask than asking a stranger for a first.

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

## State: the second axis

A ship says how far somebody got. It does not say whether they are still
here. Those are two different facts and the system has been carrying only
one of them.

**Ship is a high-water mark. State is a pulse.** A person keeps their ship
and carries a state alongside it. "An inactive partner" is a true and useful
sentence. "Demoted to Fellowship" is neither, and it is dangerous: a demoted
person could be swept back into a plan-your-visit sequence, which is the
2026-08-05 failure wearing a new coat.

### What counts as a signal

Everything downstream depends on this list, so it is written before the
states are.

| Signal | Source |
|---|---|
| Checked in to a service or event | PCO Check-Ins |
| Gave | `giving_gifts` |
| Served | PCO Serving |
| Registered for anything | PCO Registrations |
| Attended a Growth Track or Charisma session | `gt_activity` |
| Their kids checked in | PCO Check-Ins, rolled up to the household |
| Tapped "I'm here" on the livestream | `live_here` |

Two of those are easy to leave out and both would be a mistake. **Kids'
check-ins keep the parents active**, or every family whose adults do not
badge in reads as gone. **The livestream tap keeps online people active**,
or the household in another state who watches every week and gives nothing
gets filed as lapsed. Online Attendance is one of the seven vital signs; it
should not be invisible to the clock that decides who is still here.

**What PD said, and what I added.** PD's words were *"a person who hasn't
given, served or registered for 2 years is inactive"*: three signals.
Everything else in the table above is `proposed` by me, and the two worth
arguing for are the kids' check-in roll-up and the livestream tap, because
without them every family whose adults do not badge in, and every household
that watches from another state, reads as gone.

**The signal list and the triad are asking different questions**, which is
why they do not have to match. The signal list answers *are they still
here*. The triad answers *have they partnered*. Under Option B a person can
be fully Active and give none of the three, which is what makes the A1 flag
possible. Under Option A that gap mostly closes and the bare check-in is
the only thing left in one list and not the other.

### The four states

| State | Trigger | Set by |
|---|---|---|
| **Active** | any signal in the last 6 months | the clock |
| **Dormant** | no signal in 6 months | the clock, sets `dormant_since` |
| **Inactive** | no signal in 24 months | the clock, PD's rule |
| **Archived** | a known reason | **a human, always** |

Three rules protect the people underneath:

1. **A clock never archives.** Silence is not information about why. It
   could be a move, a hospital, a hurt, or a death. Inactive is the most a
   date arithmetic is allowed to conclude.
2. **Archiving never deletes.** The record, the history, and the reasons
   stay. Archive means "stop counting them and stop looking for them", not
   "pretend they were never here".
3. **A return is loud.** Any signal clears Dormant or Inactive immediately,
   and it should surface, not just quietly flip a field. Somebody coming
   home after two years is the best event this system can detect and it
   should not pass in silence.

### Archive reasons, because they do not behave alike

| Reason | Behaviour |
|---|---|
| Moved away | Keep the record. Never on a win-back list. Not a loss. |
| Went to another church | Same, and it is a good outcome, not a failure to fix. |
| **Deceased** | Never on any list, never in any count, ever. Flag the household for care. |
| Asked to be removed | Hard stop. This one propagates to the Pathways suppression list. |
| Not a real person | Test record, bot form fill, bad lead. |

Duplicates are not archived. They are merged, through
`pursuit_merge_candidates`, because archiving one of them loses whichever
history sat on the wrong record.

**Deceased is absolute and it needs checking before anything renders, not
after.** The failure mode is small, quiet, and unforgivable: a "we miss you"
list with a widow's late husband on it. Every list, every count, every
export checks this first.

### What this does to the numbers

Giving is the only source with real history today, so it is the honest test.
Of **3,340 people who have ever given**:

| Last gift | People |
|---|---|
| Within 6 months | **878** |
| Within 12 months | 1,254 |
| Within 24 months | 1,789 |
| **Silent more than 24 months** | **1,551** |

Forty-six percent of the giving roster is Inactive under PD's rule. The
oldest last gift on file is January 2016, a decade ago. Without the second
axis, all 3,340 of those people sit on Fellowship forever and the ship
count means nothing.

Two lists fall straight out of it, and they are not the same list:

- **191 lapsed partners.** Ten or more lifetime gifts, silent over two
  years. These are people who were genuinely planted here and are gone. It
  is the most sobering number in this document.
- **156 partners gone quiet.** Ten or more gifts, last one between six and
  twenty-four months ago. Dormant, not yet Inactive. **This is the
  recoverable list**, and it is the one worth working first, because the
  other one has had two years to settle.

For scale in the other direction: **1,435 people gave exactly once**, and
798 of those were more than two years ago. That is what Fellowship is mostly
made of, and it is fine, as long as the board says so plainly.

### How the board should read

No bare counts, anywhere. Every ship reads **"1,240 aboard, 380 active"**,
so the size of the house and the state of the house arrive in the same
glance. The default fleet view shows active only, with inactive one tap
away rather than hidden. Archived is off by default and findable by search,
never by browsing.

And the interaction that will tempt somebody to "fix" the resolver, stated
so nobody does: a person with twelve gifts whose last one was three years
ago no longer satisfies P3, whose window is twenty-four months. **They stay
on Partnership anyway**, flagged Inactive. That is rule 2 doing its job.
They did not stop having been a partner. They stopped being here.

### Handoff to the Pathways engine

Pursuit publishes state. It does not act on it. No suppression, no send, no
enrolment, no exception. The Pathways engine reads `state` the same way it
reads anything else here, and its own switch, suppression list, and rate
limits decide what happens next. The one hard edge is "asked to be
removed", which has to reach the shared suppression list rather than living
only in Pursuit.

## The admin page, and why it is the real fix

PD asked for a page to set and reset these rules, and it is the answer to
the attribution problem above rather than a convenience. While the rules
live in prose and Python constants, the only way to change one is to ask an
engineer, and the only record of who decided what is a paragraph somebody
wrote. Paragraphs drift. This one did.

So the rules are now rows. `pursuit_rules` is applied and seeded: **15 from
PD, 12 proposed.** Every row carries `origin`, so the page can show at a
glance which rules the house actually set and which are still my
suggestions waiting on a decision.

**`/pursuit/rules`, what it does:**

- **Lists every rule grouped by ship**, each showing its threshold, its
  window, and its currency where it has one.
- **Marks origin plainly.** PD rules read as house policy. Proposed rules
  read as awaiting a decision, with an Accept button that flips origin to
  `pd` and puts a name and a date on it.
- **Edits the numbers.** Ten gifts, two serves, ninety days, six months:
  every one of them is a field, because every one of them is a pastoral
  judgement rather than a technical constant.
- **Enables and disables** without deleting, for rules like Charisma Track
  that have no data source yet.
- **Resets to default**, per rule or wholesale, which is why the seed
  values stay in `supabase/pursuit_rules.sql` and why `is_default` exists.
- **Shows what a change would do before it is saved.** Dropping P3 from ten
  gifts to six moves a knowable number of people onto Partnership, and the
  page should say how many before the button is pressed rather than after.
- **Writes `pursuit_rule_history` on every change**, so the answer to "who
  decided this and when" is a query and not a memory.

Access sits with the same roles that can open Pursuit at all. Editing who
counts as a partner is not a thing to leave on an unlocked page.

**Nothing about this page sends anything to anybody.** It changes how the
house counts. What the house then does about a count belongs to the
Pathways engine, with its switch and its suppression list.

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
   store the reasons, respect manual pins, set state, set the A flags.
6. **State and archive**: a `state` column, a `last_signal_at` column that
   every sync updates, an `archived_reason` a human sets and a clock never
   does, and the deceased check that runs before any list renders.
   *Applied.*
7. **The rules admin page** at `/pursuit/rules`, per the section above. The
   tables are applied and seeded; the page itself is not built yet.
8. **Charisma Track and mentoring**: no data source exists yet. Until one
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
4. ~~Should silence archive somebody?~~ **Answered: no.** Twenty-four
   months of nothing makes a person Inactive. Archived is always a human
   act, because a clock cannot know why somebody went quiet.
5. Is six months the right point to call somebody dormant, or is a church
   year (say ten months, which survives a summer away) truer? This is now
   the one date left unset, and it decides the size of the recoverable list.
6. Where does Charisma Track live, and can the resolver read it?
7. Who may pin a person's ship by hand, and who may archive?
8. What counts as "regular" for the A1 flag: twelve check-ins in a year, or
   something stricter like two a month for three months running?
9. Where does the house record a death today? Nothing in this system is
   trustworthy on that point until there is one source it can read.
10. **What is the bar for Time?** Treasure has one (10 gifts in 24 months)
    and Talent has one (2 serves in 90 days). Time has none yet. P9
    proposes three registered-and-attended things in twelve months, which
    is a guess and should be PD's number.
11. Does the house want gifts and skills recorded in PCO? Not needed to
    classify anybody, since serving already proves Talent. Needed to ask
    who has a gift the house is not using.
