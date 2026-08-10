"""One-shot backfill: attach Amazon Business order summaries to card charges.

PD bulk-downloaded the Business account's "printable order summary" PDFs
(one per order, 2026-01-01 onward) and every 2026 Amazon charge in
fin_transactions has already been stamped with its amazon_order_id from the
Business Reconciliation report. This job walks that mapping and files each
PDF the way the intranet's /api/finance/ingest route would have:

    storage: finance-receipts/<admin>/<uuid>-drive-amazon-<order>.pdf
    fin_requests: one card_receipt row filed under the finance admin,
        source_ref 'drive:zipbulk0810:<order>:<txn8>' for idempotency
    fin_transactions: has_receipt = true + receipt_request_id (deterministic
        link -- the order id already proved the pairing, no fuzzy matching)
    fin_audit_log: one row per filing, actor_email 'drive-backfill'

Charges are re-checked at run time: a charge that gained a receipt since the
plan was cut is skipped, and a source_ref that already exists is never filed
twice, so re-running is safe.

Inputs (committed alongside, under data/amazon_backfill/):
    amazon_invoices.zip   the bulk download, PDF names carry the order id
    picks.txt             txn_id;order_id;amount;posted_on;buyer;po per line

Env: Supabase URL + service key (any of the four names gc3_env accepts),
DRY_RUN=1 to print the plan without writing anything.
"""
import io
import os
import re
import sys
import uuid
import zipfile

from supabase import create_client

import gc3_env

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "amazon_backfill")
DRY = bool(os.environ.get("DRY_RUN"))

sb = create_client(gc3_env.supabase_url(), gc3_env.service_key())


def load_pdfs(z):
    """order id -> (zip entry name, order date) from the download's filenames."""
    out = {}
    for n in z.namelist():
        m = re.match(r"(\d{8})_Printable Order Summary_(\d{3}-\d{7}-\d{7})\.pdf$", n)
        if m:
            out[m.group(2)] = (n, f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}")
    return out


def load_picks():
    picks = []
    for line in open(os.path.join(DATA, "picks.txt"), encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        txn, order, amt, posted, buyer, po = line.split(";", 5)
        picks.append({"txn": txn, "order": order, "amt": float(amt),
                      "posted": posted, "buyer": buyer, "po": po})
    return picks


def main():
    admin = sb.table("profiles").select("id, email").ilike("email", "pd@godchasers.church").single().execute().data
    z = zipfile.ZipFile(os.path.join(DATA, "amazon_invoices.zip"))
    pdfs = load_pdfs(z)
    picks = load_picks()

    have = [p for p in picks if p["order"] in pdfs]
    print(f"{len(picks)} planned, {len(have)} with a PDF, {len(picks) - len(have)} without")
    for p in picks:
        if p["order"] not in pdfs:
            print(f"  no PDF in zip: {p['order']} ${p['amt']:.2f} ({p['buyer']})")

    filed = linked = skipped = failed = 0
    for p in have:
        ref = f"drive:zipbulk0810:{p['order']}:{p['txn'][:8]}"

        already = sb.table("fin_requests").select("id").eq("source_ref", ref).execute().data
        if already:
            skipped += 1
            continue

        txn = sb.table("fin_transactions").select(
            "id, has_receipt, status, vendor, posted_on").eq("id", p["txn"]).single().execute().data
        if not txn or txn["has_receipt"] or txn["status"] == "ignored":
            print(f"  skip (charge changed since planning): {p['order']} ${p['amt']:.2f}")
            skipped += 1
            continue

        entry, order_date = pdfs[p["order"]]
        po_note = f" — {p['po']}" if p["po"] and not p["po"].startswith("Amazon order") else ""
        summary = f"Amazon Business order {p['order']}{po_note}"

        if DRY:
            print(f"  would file: {p['order']} ${p['amt']:.2f} {p['buyer']} -> charge {p['txn'][:8]}")
            filed += 1
            continue

        path = f"{admin['id']}/{uuid.uuid4()}-drive-amazon-{p['order']}.pdf"
        try:
            sb.storage.from_("finance-receipts").upload(
                path, z.read(entry), {"content-type": "application/pdf"})
        except Exception as e:
            print(f"  UPLOAD FAILED {p['order']}: {e}")
            failed += 1
            continue

        ai = {"merchant": "Amazon Business", "total": p["amt"], "date": order_date,
              "card_last4": None, "summary": summary, "subtotal": None, "tax": None,
              "tip": None, "currency": "USD", "suggested_primary": None,
              "suggested_sub": None, "suggestion_reason": None}
        try:
            req = sb.table("fin_requests").insert({
                "kind": "card_receipt",
                "user_id": admin["id"],
                "user_email": admin["email"],
                "amount": p["amt"],
                "vendor": "Amazon Business",
                "description": summary + (f" — submitted by {p['buyer']}" if p["buyer"] else ""),
                "purchased_on": order_date,
                "receipt_path": path,
                "ai_extract": ai,
                "source_ref": ref,
            }).execute().data[0]
        except Exception as e:
            print(f"  INSERT FAILED {p['order']}: {e}")
            sb.storage.from_("finance-receipts").remove([path])
            failed += 1
            continue
        filed += 1

        sb.table("fin_transactions").update({
            "has_receipt": True, "receipt_request_id": req["id"],
            "suggested_receipt_id": None, "suggested_receipt_note": None,
        }).eq("id", p["txn"]).execute()
        linked += 1

        sb.table("fin_audit_log").insert({
            "actor": admin["id"],
            "actor_email": "drive-backfill",
            "action": "inbound_receipt.filed",
            "target": req["id"],
            "detail": {"source": "amazon-zip", "filename": entry,
                       "submitter": p["buyer"] or None, "order_id": p["order"],
                       "matched": True},
        }).execute()
        print(f"  filed: {p['order']} ${p['amt']:.2f} {p['buyer']} -> charge {p['txn'][:8]}")

    print(f"\n{'DRY RUN — ' if DRY else ''}filed {filed}, linked {linked}, "
          f"skipped {skipped}, failed {failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
