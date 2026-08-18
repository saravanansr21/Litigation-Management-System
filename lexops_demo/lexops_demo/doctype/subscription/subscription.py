# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, getdate, today


GST_RATE = 18.0
USAGE_FIELDS = {
    "notices": ("notices_used", "notices_cap"),
    "drafts": ("drafts_used", "drafts_cap"),
    "gstins": ("gstins_connected", "gstins_cap"),
    "storage": ("storage_used", "storage_cap"),
    "api_calls": ("api_calls_used", "api_calls_cap"),
}


class Subscription(Document):
    def validate(self):
        self.validate_dates()
        self.validate_status()
        self.sync_plan_limits()

    def validate_dates(self):
        if self.start_date and self.renewal_date:
            if getdate(self.renewal_date) < getdate(self.start_date):
                frappe.throw("Renewal Date cannot be before Start Date.")

    def validate_status(self):
        allowed = {"Active", "Cancelled", "Past Due"}
        if self.status and self.status not in allowed:
            frappe.throw("Invalid Subscription Status.")

    def sync_plan_limits(self):
        if not self.plan:
            return

        plan = frappe.get_doc("Plan", self.plan)
        self.notices_cap = cint(plan.notice_cap or 0)
        self.drafts_cap = cint(plan.draft_cap or 0)
        self.gstins_cap = cint(plan.gstin_cap or 0)
        self.storage_cap = flt(plan.storage_cap or 0)
        self.api_calls_cap = cint(plan.api_calls_cap or 0)

    def get_plan_doc(self):
        if not self.plan:
            frappe.throw("Subscription does not have a Plan.")
        return frappe.get_doc("Plan", self.plan)

    def get_usage_summary(self):
        plan = self.get_plan_doc()

        usage = {
            "notices": {"used": cint(self.notices_used or 0), "cap": cint(self.notices_cap or 0)},
            "drafts": {"used": cint(self.drafts_used or 0), "cap": cint(self.drafts_cap or 0)},
            "gstins": {"used": cint(self.gstins_connected or 0), "cap": cint(self.gstins_cap or 0)},
            "storage": {"used": flt(self.storage_used or 0), "cap": flt(self.storage_cap or 0)},
            "api_calls": {"used": cint(self.api_calls_used or 0), "cap": cint(self.api_calls_cap or 0)},
        }

        for item in usage.values():
            cap = flt(item["cap"])
            used = flt(item["used"])
            item["remaining"] = max(cap - used, 0)
            item["over_limit"] = used > cap if cap > 0 else used > 0

        return {
            "subscription": self.name,
            "plan": plan.plan_name,
            "status": self.status,
            "start_date": self.start_date,
            "renewal_date": self.renewal_date,
            "usage": usage,
        }

    def increment_usage(self, metric, amount=1):
        if metric not in USAGE_FIELDS:
            frappe.throw(f"Unsupported subscription usage metric: {metric}")

        used_field, _ = USAGE_FIELDS[metric]
        current = flt(self.get(used_field) or 0)
        amount = flt(amount)

        if amount < 0:
            frappe.throw("Usage increment cannot be negative.")

        new_value = current + amount
        self.db_set(used_field, new_value, update_modified=False)
        self.set(used_field, new_value)

        return new_value

    def reset_usage(self):
        for used_field, _ in USAGE_FIELDS.values():
            self.db_set(used_field, 0, update_modified=False)
            self.set(used_field, 0)

    def get_notice_overage(self):
        plan = self.get_plan_doc()
        used = flt(self.notices_used or 0)
        cap = flt(self.notices_cap or 0)
        excess = max(used - cap, 0)
        rate = flt(plan.overage_rate_per_notice or 0)
        return {
            "used": used,
            "cap": cap,
            "quantity": excess,
            "rate": rate,
            "amount": excess * rate,
        }

    def calculate_invoice_amounts(self):
        plan = self.get_plan_doc()
        base_amount = flt(plan.price or 0)
        overage = self.get_notice_overage()
        taxable_amount = base_amount + flt(overage["amount"])
        gst = taxable_amount * GST_RATE / 100
        total = taxable_amount + gst

        return {
            "base_amount": base_amount,
            "overage_amount": flt(overage["amount"]),
            "gst_18": gst,
            "total": total,
            "overage_details": overage,
        }

    def create_invoice_for_current_cycle(self):
        from .invoice import create_invoice_from_subscription

        amounts = self.calculate_invoice_amounts()
        invoice = create_invoice_from_subscription(self, amounts)
        return invoice

    def request_plan_change(self, new_plan):
        if not new_plan:
            frappe.throw("New Plan is required.")

        if not frappe.db.exists("Plan", new_plan):
            frappe.throw("Selected Plan does not exist.")

        if new_plan == self.plan:
            self.db_set("pending_plan", None)
            self.set("pending_plan", None)
            return self

        self.db_set("pending_plan", new_plan)
        self.set("pending_plan", new_plan)
        return self

    def apply_pending_plan(self):
        if not self.pending_plan:
            return False

        if not frappe.db.exists("Plan", self.pending_plan):
            frappe.throw("Pending Plan does not exist.")

        self.db_set("plan", self.pending_plan, update_modified=False)
        self.db_set("pending_plan", None, update_modified=False)
        self.set("plan", self.pending_plan)
        self.set("pending_plan", None)
        self.sync_plan_limits()
        self.db_set("notices_cap", self.notices_cap, update_modified=False)
        self.db_set("drafts_cap", self.drafts_cap, update_modified=False)
        self.db_set("gstins_cap", self.gstins_cap, update_modified=False)
        self.db_set("storage_cap", self.storage_cap, update_modified=False)
        self.db_set("api_calls_cap", self.api_calls_cap, update_modified=False)
        return True

    def renew(self):
        if self.status == "Cancelled":
            frappe.throw("Cancelled subscriptions cannot be renewed.")

        invoice = self.create_invoice_for_current_cycle()

        if self.pending_plan:
            self.apply_pending_plan()

        self.reset_usage()

        renewal_base = getdate(self.renewal_date or today())
        next_renewal = add_months(renewal_base, 1)

        self.db_set("start_date", renewal_base, update_modified=False)
        self.db_set("renewal_date", next_renewal, update_modified=False)
        self.db_set("status", "Active", update_modified=False)

        self.set("start_date", renewal_base)
        self.set("renewal_date", next_renewal)
        self.set("status", "Active")

        return invoice

    def cancel(self):
        if self.status == "Cancelled":
            return self

        self.db_set("status", "Cancelled")
        self.set("status", "Cancelled")
        return self

    def as_dict_for_api(self):
        plan = self.get_plan_doc()
        return {
            "name": self.name,
            "firm_profile": self.firm_profile,
            "plan": {
                "name": plan.name,
                "plan_name": plan.plan_name,
                "price": flt(plan.price or 0),
            },
            "pending_plan": self.pending_plan,
            "start_date": self.start_date,
            "renewal_date": self.renewal_date,
            "status": self.status,
            "usage": self.get_usage_summary()["usage"],
        }
 