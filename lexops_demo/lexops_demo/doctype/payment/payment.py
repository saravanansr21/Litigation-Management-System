# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class Payment(Document):
    def validate(self):
        self.validate_invoice()
        self.validate_amount()

    def after_insert(self):
        self.update_invoice_status()

    def validate_invoice(self):
        if not self.invoice:
            frappe.throw("Invoice is required.")

        if not frappe.db.exists("Invoice", self.invoice):
            frappe.throw("Selected Invoice does not exist.")

    def validate_amount(self):
        amount = flt(self.amount or 0)

        if amount <= 0:
            frappe.throw("Payment Amount must be greater than zero.")

        invoice = frappe.get_doc("Invoice", self.invoice)
        balance = invoice.get_balance_amount()

        if amount > balance + 0.01:
            frappe.throw(
                f"Payment Amount ({amount:.2f}) cannot exceed the outstanding "
                f"Invoice balance ({balance:.2f})."
            )

    def update_invoice_status(self):
        invoice = frappe.get_doc("Invoice", self.invoice)
        invoice.update_payment_status()

    def as_dict_for_api(self):
        return {
            "name": self.name,
            "invoice": self.invoice,
            "paid_on": self.paid_on,
            "amount": flt(self.amount or 0),
            "payment_method": self.payment_method,
            "reference_transaction_id": self.reference_transaction_id,
        }
