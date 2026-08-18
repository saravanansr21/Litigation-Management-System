# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class Invoice(Document):
    def before_insert(self):
        if not self.invoice_number:
            self.invoice_number = self.name

    def validate(self):
        self.validate_amounts()
        self.validate_status()

    def validate_amounts(self):
        for fieldname in ("base_amount", "overage_amount", "gst_18", "total"):
            if flt(self.get(fieldname) or 0) < 0:
                frappe.throw(f"{self.meta.get_label(fieldname)} cannot be negative.")

        calculated_total = (
            flt(self.base_amount or 0)
            + flt(self.overage_amount or 0)
            + flt(self.gst_18 or 0)
        )

        if abs(flt(self.total or 0) - calculated_total) > 0.01:
            frappe.throw(
                f"Invoice Total must equal Base Amount + Overage Amount + GST. "
                f"Expected {calculated_total:.2f}."
            )

    def validate_status(self):
        allowed = {"Paid", "Unpaid", "Overdue"}
        if self.status not in allowed:
            frappe.throw("Invalid Invoice Status.")

    def get_paid_amount(self):
        if self.is_new():
            return 0

        return flt(
            frappe.db.sql(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM `tabPayment`
                WHERE invoice = %s
                """,
                self.name,
            )[0][0]
        )

    def get_balance_amount(self):
        return max(flt(self.total or 0) - self.get_paid_amount(), 0)

    def update_payment_status(self):
        paid = self.get_paid_amount()
        total = flt(self.total or 0)

        if paid >= total and total > 0:
            status = "Paid"
        elif self.date and getdate(self.date) < getdate(today()) and paid < total:
            status = "Overdue"
        else:
            status = "Unpaid"

        self.db_set("status", status, update_modified=False)
        self.set("status", status)
        return status

    def as_dict_for_api(self):
        return {
            "name": self.name,
            "invoice_number": self.invoice_number,
            "subscription": self.subscription,
            "date": self.date,
            "billing_period": self.billing_period,
            "base_amount": flt(self.base_amount or 0),
            "overage_amount": flt(self.overage_amount or 0),
            "gst_18": flt(self.gst_18 or 0),
            "total": flt(self.total or 0),
            "paid_amount": self.get_paid_amount(),
            "balance_amount": self.get_balance_amount(),
            "status": self.status,
            "pdf": self.pdf,
        }


def create_invoice_from_subscription(subscription, amounts):
    invoice = frappe.new_doc("Invoice")
    invoice.subscription = subscription.name
    invoice.date = today()
    invoice.billing_period = getdate(subscription.start_date or today()).strftime("%b %Y")
    invoice.base_amount = flt(amounts["base_amount"])
    invoice.overage_amount = flt(amounts["overage_amount"])
    invoice.gst_18 = flt(amounts["gst_18"])
    invoice.total = flt(amounts["total"])
    invoice.status = "Unpaid"
    invoice.insert(ignore_permissions=True)
    return invoice
