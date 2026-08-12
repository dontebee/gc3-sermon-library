"""One-time diagnostic: what changed in the ad account, month by month.

The Church Candy era ads ran in OUR ad account (PD confirmed), and Meta
keeps about 37 months of insights. This script pulls monthly campaign-level
history and lays the eras side by side: spend, leads, cost per lead, and,
most tellingly, WHICH OBJECTIVES the money bought each month. The usual
smoking gun for a volume drop is right there: lead-objective campaigns with
instant forms in the old era, traffic or awareness campaigns in the new.

Read-only against Meta and writes nothing anywhere: no Supabase, no email.
The report prints to the Action log and is saved to
meta_ads_history_report.md, which the workflow uploads as a downloadable
artifact.

Env vars:
  META_ACCESS_TOKEN, META_AD_ACCOUNT_ID   same secrets as the weekly report
Optional:
  HISTORY_MONTHS   how far back to look (default 36; Meta caps around 37)
  SWITCH_DATE      YYYY-MM-DD of the agency handoff. When set, months are
                   era-tagged and the report adds a before/after comparison.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

from meta_api import AD_ACCOUNT, account_info, connected, meta_get_all

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPORT_PATH = "meta_ads_history_report.md"

HISTORY_FIELDS = ",".join([
    "campaign_id", "campaign_name", "objective",
    "spend", "impressions", "clicks", "inline_link_clicks", "actions",
])


def _i(v):
    return int(float(v or 0))


def _f(v):
    return float(v or 0)


def _months_back(n):
    """First day of the month, n months before this one."""
    today = datetime.now(timezone.utc).date()
    year, month = today.year, today.month - n
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _parse_switch():
    raw = (os.environ.get("SWITCH_DATE") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        print(f"NOTE: SWITCH_DATE={raw!r} is not YYYY-MM-DD; running without era tagging.")
        return None


def fetch_history(months):
    since = _months_back(months)
    until = datetime.now(timezone.utc).date() - timedelta(days=1)
    print(f"Pulling monthly campaign history {since} to {until}...")
    return meta_get_all(f"{AD_ACCOUNT}/insights", {
        "level": "campaign",
        "fields": HISTORY_FIELDS,
        "time_range": json.dumps({"since": str(since), "until": str(until)}),
        "time_increment": "monthly",
        "limit": 500,
    })


def lead_count(actions):
    """Leads specifically, not the broader result heuristic the weekly report
    uses. 'lead' is the instant-form (and website lead) action; it is the
    number ChurchFunnels would have received."""
    return sum(_i(a.get("value")) for a in (actions or []) if a.get("action_type") == "lead")


def shape(rows):
    """Roll campaign-month rows into per-month and per-campaign summaries."""
    months, campaigns = {}, {}
    for r in rows:
        month = (r.get("date_start") or "")[:7]
        if not month:
            continue
        spend, imps = _f(r.get("spend")), _i(r.get("impressions"))
        leads = lead_count(r.get("actions"))
        links = _i(r.get("inline_link_clicks"))
        obj = r.get("objective") or "UNKNOWN"

        m = months.setdefault(month, {"spend": 0.0, "impressions": 0, "leads": 0,
                                      "link_clicks": 0, "objectives": {}})
        m["spend"] += spend
        m["impressions"] += imps
        m["leads"] += leads
        m["link_clicks"] += links
        m["objectives"][obj] = m["objectives"].get(obj, 0.0) + spend

        c = campaigns.setdefault(r.get("campaign_id"), {
            "name": r.get("campaign_name"), "objective": obj,
            "spend": 0.0, "leads": 0, "first_month": month, "last_month": month})
        c["spend"] += spend
        c["leads"] += leads
        c["first_month"] = min(c["first_month"], month)
        c["last_month"] = max(c["last_month"], month)
    return months, campaigns


def era_of(month, switch):
    return "before" if month < str(switch)[:7] else "after"


def summarize_era(months, keys):
    n = len(keys)
    spend = sum(months[k]["spend"] for k in keys)
    leads = sum(months[k]["leads"] for k in keys)
    objectives = {}
    for k in keys:
        for obj, s in months[k]["objectives"].items():
            objectives[obj] = objectives.get(obj, 0.0) + s
    return {
        "months": n,
        "spend_per_month": spend / n if n else 0,
        "leads_per_month": leads / n if n else 0,
        "cpl": spend / leads if leads else None,
        "objectives": objectives,
        "spend": spend,
    }


def obj_share_lines(objectives, total):
    lines = []
    for obj, s in sorted(objectives.items(), key=lambda x: -x[1]):
        share = (s / total * 100) if total else 0
        lines.append(f"  {obj}: ${s:,.2f} ({share:.0f}% of spend)")
    return lines


def render(months, campaigns, switch):
    out = ["# Meta ads history: month by month", ""]
    out.append(f"Generated {datetime.now(timezone.utc):%Y-%m-%d}. Leads here means the "
               f"'lead' action (instant forms and website leads): the number that "
               f"would have reached ChurchFunnels.")
    out.append("")
    out.append("| Month | Spend | Leads | Cost/lead | Link clicks | Impressions |" +
               (" Era |" if switch else ""))
    out.append("|---|---|---|---|---|---|" + ("---|" if switch else ""))
    for month in sorted(months):
        m = months[month]
        cpl = f"${m['spend'] / m['leads']:,.2f}" if m["leads"] else "-"
        line = (f"| {month} | ${m['spend']:,.2f} | {m['leads']} | {cpl} "
                f"| {m['link_clicks']:,} | {m['impressions']:,} |")
        if switch:
            line += f" {era_of(month, switch)} |"
        out.append(line)
    out.append("")

    if switch:
        before = [k for k in months if era_of(k, switch) == "before"]
        after = [k for k in months if era_of(k, switch) == "after"]
        if before and after:
            b, a = summarize_era(months, before), summarize_era(months, after)
            out.append(f"## Before vs after the switch ({switch})")
            out.append("")
            out.append("| | Before | After |")
            out.append("|---|---|---|")
            out.append(f"| Months | {b['months']} | {a['months']} |")
            out.append(f"| Spend per month | ${b['spend_per_month']:,.2f} | ${a['spend_per_month']:,.2f} |")
            out.append(f"| Leads per month | {b['leads_per_month']:.1f} | {a['leads_per_month']:.1f} |")
            out.append(f"| Cost per lead | "
                       f"{'$' + format(b['cpl'], ',.2f') if b['cpl'] else '-'} | "
                       f"{'$' + format(a['cpl'], ',.2f') if a['cpl'] else '-'} |")
            out.append("")
            out.append("Where the money went, before:")
            out.extend(obj_share_lines(b["objectives"], b["spend"]))
            out.append("")
            out.append("Where the money goes, after:")
            out.extend(obj_share_lines(a["objectives"], a["spend"]))
            out.append("")

    out.append("## Campaigns by leads produced (top 15)")
    out.append("")
    out.append("| Campaign | Objective | Active | Spend | Leads | Cost/lead |")
    out.append("|---|---|---|---|---|---|")
    ranked = sorted(campaigns.values(), key=lambda c: (-c["leads"], -c["spend"]))[:15]
    for c in ranked:
        cpl = f"${c['spend'] / c['leads']:,.2f}" if c["leads"] else "-"
        active = c["first_month"] if c["first_month"] == c["last_month"] else \
            f"{c['first_month']} to {c['last_month']}"
        out.append(f"| {c['name']} | {c['objective']} | {active} "
                   f"| ${c['spend']:,.2f} | {c['leads']} | {cpl} |")
    out.append("")
    out.append("Reading it: the lead-volume months and the objectives that bought them "
               "are the playbook to copy. Campaigns with leads and a sane cost per "
               "lead are the ones whose structure (objective, form, creative style) "
               "the current agency should be asked to reproduce.")
    return "\n".join(out)


def main():
    print(f"Meta ads history diagnostic, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    if not connected():
        print("Not connected: add the META_ACCESS_TOKEN and META_AD_ACCOUNT_ID secrets")
        print("(same two the weekly ads report uses; see the README) and rerun.")
        return
    account_info()

    raw_months = (os.environ.get("HISTORY_MONTHS") or "").strip()
    try:
        history_months = max(1, min(37, int(raw_months))) if raw_months else 36
    except ValueError:
        print(f"NOTE: HISTORY_MONTHS={raw_months!r} is not a number; using 36.")
        history_months = 36
    switch = _parse_switch()

    rows = fetch_history(history_months)
    print(f"  {len(rows)} campaign-month row(s) returned")
    if not rows:
        print("No history returned. Either the account is newer than the window or")
        print("the ads ran in a different ad account after all.")
        return

    months, campaigns = shape(rows)
    report = render(months, campaigns, switch)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print()
    print(report)
    print()
    print(f"Report saved to {REPORT_PATH} (uploaded as a workflow artifact).")


if __name__ == "__main__":
    main()
