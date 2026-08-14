-- The Pulse: every aggregate the health board reads, in one call.
--
-- /pursuit/pulse in the intranet is a page full of charts about the health
-- of the house. Its numbers come from here, not from a dozen PostgREST
-- round trips: one function, one JSON, so the page and the data can never
-- drift apart mid-render.
--
-- Discretion, restated where the data lives: giving appears ONLY as
-- participation (distinct givers). No amounts leave this function, and
-- nothing outward is ever triggered by any of it.
--
-- Vocabulary: ship is the high-water mark of the voyage; state is the
-- pulse. Active is Time, Talent or Treasure inside six months, dormant is
-- six to twenty-four, inactive is off the board. Archived and deceased are
-- human words and are excluded everywhere here.

create or replace function public.pursuit_pulse()
returns jsonb
language sql
stable
set search_path = public
as $$
with months as (
  select date_trunc('month', now()) - (interval '1 month' * n) as m
  from generate_series(23, 0, -1) as n
),
living as (
  select id, ship, state, pco_person_id, last_signal_at
  from pursuit_people
  where coalesce(deceased, false) = false and state <> 'archived'
),
onboard as (
  select * from living where state in ('active', 'dormant')
),

-- ---------- the heartbeat: month by month, 24 months ----------
new_people as (
  select date_trunc('month', pco_created_at) m, count(*) n
  from pco_people where not child and pco_created_at is not null
  group by 1
),
givers as (
  -- participation, never amounts
  select date_trunc('month', received_at) m, count(distinct pco_person_id) n
  from giving_gifts where pco_person_id is not null
  group by 1
),
joins as (
  select date_trunc('month', joined_at) m, count(*) n
  from pco_group_memberships where joined_at is not null
  group by 1
),
hands as (
  select date_trunc('month', t) m, count(*) n
  from (
    select created_on as t from ghl_opportunities
    where created_on is not null
      and lower(coalesce(stage, '')) in
        ('planned a visit', 'attended a service', 'pyv no show',
         'pyv not coming this week', 'attended - no check in')
    union all
    select created_time from meta_leads where created_time is not null
  ) h
  group by 1
),
fell as (
  -- The back door: the month a 24-month clock ran out, for people now off
  -- the board. Honest and computable from the signal we keep.
  select date_trunc('month', last_signal_at + interval '24 months') m, count(*) n
  from living
  where state = 'inactive' and last_signal_at is not null
  group by 1
),
series as (
  select jsonb_agg(jsonb_build_object(
    'month',       to_char(months.m, 'YYYY-MM'),
    'new_people',  coalesce(np.n, 0),
    'givers',      coalesce(gv.n, 0),
    'group_joins', coalesce(jn.n, 0),
    'hands',       coalesce(hd.n, 0),
    'fell_off',    coalesce(fl.n, 0)
  ) order by months.m) as j
  from months
  left join new_people np on np.m = months.m
  left join givers     gv on gv.m = months.m
  left join joins      jn on jn.m = months.m
  left join hands      hd on hd.m = months.m
  left join fell       fl on fl.m = months.m
),

-- ---------- the fleet, split by pulse ----------
fleet as (
  select jsonb_agg(jsonb_build_object(
           'ship', ship, 'active', act, 'dormant', dor)) as j
  from (
    select ship,
           count(*) filter (where state = 'active')  act,
           count(*) filter (where state = 'dormant') dor
    from onboard group by ship
  ) f
),

-- ---------- the clock: how fresh is everyone's last signal ----------
clock as (
  select jsonb_agg(jsonb_build_object('bucket', bucket, 'n', n) order by ord) as j
  from (
    select bucket, ord, count(*) n from (
      select case
        when last_signal_at is null then 7
        when last_signal_at > now() - interval '1 month'   then 1
        when last_signal_at > now() - interval '3 months'  then 2
        when last_signal_at > now() - interval '6 months'  then 3
        when last_signal_at > now() - interval '12 months' then 4
        when last_signal_at > now() - interval '24 months' then 5
        else 6 end ord,
      case
        when last_signal_at is null then 'no signal ever'
        when last_signal_at > now() - interval '1 month'   then 'this month'
        when last_signal_at > now() - interval '3 months'  then '1 to 3 months'
        when last_signal_at > now() - interval '6 months'  then '3 to 6 months'
        when last_signal_at > now() - interval '12 months' then '6 to 12 months'
        when last_signal_at > now() - interval '24 months' then '12 to 24 months'
        else 'past 24 months' end bucket
      from living
    ) b group by 1, 2
  ) c
),

-- ---------- Time, Talent, Treasure: who carries what, today ----------
ttt_base as (
  select o.id,
    exists (select 1 from pco_group_memberships g
            where g.pco_person_id = o.pco_person_id)                  as t_time,
    exists (select 1 from pco_serving s
            where s.person_id = o.pco_person_id)                      as t_talent,
    exists (select 1 from giving_gifts gg
            where gg.pco_person_id = o.pco_person_id
              and gg.received_at > now() - interval '90 days')        as t_treasure
  from onboard o
),
ttt as (
  select jsonb_build_object(
    'time',     count(*) filter (where t_time),
    'talent',   count(*) filter (where t_talent),
    'treasure', count(*) filter (where t_treasure),
    'braid3',   count(*) filter (where (t_time::int + t_talent::int + t_treasure::int) = 3),
    'braid2',   count(*) filter (where (t_time::int + t_talent::int + t_treasure::int) = 2),
    'braid1',   count(*) filter (where (t_time::int + t_talent::int + t_treasure::int) = 1),
    'braid0',   count(*) filter (where (t_time::int + t_talent::int + t_treasure::int) = 0)
  ) as j
  from ttt_base
),

-- ---------- group life and serving, by name ----------
groups_top as (
  select jsonb_agg(jsonb_build_object('name', group_name, 'n', n) order by n desc) j
  from (
    select group_name, count(*) n
    from pco_group_memberships group by 1 order by n desc limit 8
  ) g
),
serve_top as (
  select jsonb_agg(jsonb_build_object('name', team, 'n', n) order by n desc) j
  from (
    select team, count(distinct person_id) n
    from pco_serving, unnest(teams) as team
    group by 1 order by n desc limit 8
  ) s
)

select jsonb_build_object(
  'months',  (select j from series),
  'fleet',   (select j from fleet),
  'clock',   (select j from clock),
  'ttt',     (select j from ttt),
  'groups',  jsonb_build_object(
     'top',      (select j from groups_top),
     'n_groups', (select count(*) from pco_groups where not archived),
     'members',  (select count(*) from pco_group_memberships),
     'charisma', (select count(*) from pco_group_memberships where group_name ilike 'charisma%')),
  'serving', jsonb_build_object(
     'top',    (select j from serve_top),
     'people', (select count(distinct person_id) from pco_serving)),
  'gt',      jsonb_build_object(
     'enrolled', (select count(*) from gt_profiles),
     'active30', (select count(distinct user_id) from gt_activity
                  where day > now() - interval '30 days'),
     'tenday',   (select count(*) from (
                    select user_id from gt_activity
                    group by user_id having count(distinct day) >= 10) t)),
  'work',    jsonb_build_object(
     'dormant_partners', (select count(*) from living where state = 'dormant'
                          and ship in ('partnership', 'discipleship', 'leadership')),
     'lapsed_partners',  (select count(*) from living where state = 'inactive'
                          and ship in ('partnership', 'discipleship', 'leadership')),
     'merge_open',       (select count(*) from pursuit_merge_candidates
                          where resolved_at is null)),
  'today',   jsonb_build_object(
     'active',   (select count(*) from living where state = 'active'),
     'dormant',  (select count(*) from living where state = 'dormant'),
     'inactive', (select count(*) from living where state = 'inactive'),
     'children', (select count(*) from pco_people where child))
);
$$;

-- The aggregates are for leadership eyes behind the intranet's role check.
-- Nothing anonymous reads the health of the house.
revoke execute on function public.pursuit_pulse() from public;
revoke execute on function public.pursuit_pulse() from anon;
revoke execute on function public.pursuit_pulse() from authenticated;
grant execute on function public.pursuit_pulse() to service_role;

-- The hero field: every living soul as one compact point, so the board can
-- open on a heat chart of the whole house. Each entry is [f, s, a]:
--   f  months since the house first knew them (first_seen_at, else created_at)
--   s  ship as a rank, 0 friendship .. 4 leadership
--   a  days since their last Time, Talent or Treasure signal; -1 for never
-- No names, no ids, no contact: the dot is anonymous by construction. The
-- deceased and the archived are excluded; a human took those off the water.
create or replace function public.pursuit_pulse_points()
returns jsonb
language sql
stable
set search_path = public
as $$
select coalesce(jsonb_agg(jsonb_build_array(f, s, a)), '[]'::jsonb)
from (
  select
    round((extract(epoch from (now() - coalesce(first_seen_at, created_at, now())))
           / 2629800.0)::numeric, 1) as f,
    case ship
      when 'friendship'   then 0
      when 'fellowship'   then 1
      when 'partnership'  then 2
      when 'discipleship' then 3
      when 'leadership'   then 4
      else 0 end as s,
    coalesce(round(extract(epoch from (now() - last_signal_at)) / 86400.0)::int, -1) as a
  from pursuit_people
  where coalesce(deceased, false) = false and state <> 'archived'
) p;
$$;

revoke execute on function public.pursuit_pulse_points() from public;
revoke execute on function public.pursuit_pulse_points() from anon;
revoke execute on function public.pursuit_pulse_points() from authenticated;
grant execute on function public.pursuit_pulse_points() to service_role;
