# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today


def process_subscription_renewals():
    """
    Process subscriptions whose renewal date has arrived.

    This job is intended to run daily. It:
    1. Finds Active subscriptions due for renewal.
    2. Creates the invoice for the completed billing cycle.
    3. Applies a pending plan, if any.
    4. Resets usage counters.
    5. Moves the subscription to the next renewal date.

    Each subscription is processed independently so one failure does not
    stop the remaining subscriptions.
    """
    subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": "Active",
            "renewal_date": ["<=", today()],
        },
        pluck="name",
    )

    results = {
        "processed": 0,
        "failed": 0,
        "invoices": [],
        "errors": [],
    }

    for subscription_name in subscriptions:
        try:
            subscription = frappe.get_doc("Subscription", subscription_name)

            # Prevent duplicate processing if the job is retried while the
            # previous transaction has already moved the renewal date.
            if subscription.status != "Active":
                continue

            if not subscription.renewal_date:
                frappe.log_error(
                    title="Subscription Renewal: Missing Renewal Date",
                    message=f"Subscription {subscription.name} has no renewal date.",
                )
                results["failed"] += 1
                results["errors"].append({
                    "subscription": subscription.name,
                    "error": "Missing renewal date",
                })
                continue

            if getdate(subscription.renewal_date) > getdate(today()):
                continue

            invoice = subscription.renew()

            frappe.db.commit()

            results["processed"] += 1
            results["invoices"].append({
                "subscription": subscription.name,
                "invoice": invoice.name if invoice else None,
            })

        except Exception:
            frappe.db.rollback()

            error_message = frappe.get_traceback()

            frappe.log_error(
                title=f"Subscription Renewal Failed: {subscription_name}",
                message=error_message,
            )

            results["failed"] += 1
            results["errors"].append({
                "subscription": subscription_name,
                "error": error_message,
            })

    return results


def mark_overdue_invoices():
    """
    Mark unpaid invoices past their invoice date as Overdue.

    This is separate from subscription renewal because an invoice can become
    overdue after it is generated.
    """
    invoices = frappe.get_all(
        "Invoice",
        filters={
            "status": "Unpaid",
            "date": ["<", today()],
        },
        pluck="name",
    )

    updated = 0

    for invoice_name in invoices:
        try:
            invoice = frappe.get_doc("Invoice", invoice_name)
            invoice.update_payment_status()

            if invoice.status == "Overdue":
                updated += 1

        except Exception:
            frappe.log_error(
                title=f"Invoice Overdue Processing Failed: {invoice_name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()

    return {
        "checked": len(invoices),
        "updated": updated,
    }
