# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint


class Plan(Document):
    def validate(self):
        self.validate_values()

    def validate_values(self):
        if not self.plan_name:
            frappe.throw("Plan Name is required.")

        if flt(self.price) < 0:
            frappe.throw("Price cannot be negative.")

        numeric_fields = (
            "notice_cap",
            "draft_cap",
            "gstin_cap",
            "api_calls_cap",
            "user_cap",
        )

        for fieldname in numeric_fields:
            value = cint(self.get(fieldname) or 0)
            if value < 0:
                frappe.throw(f"{self.meta.get_label(fieldname)} cannot be negative.")

        if flt(self.storage_cap) < 0:
            frappe.throw("Storage Cap cannot be negative.")

        if flt(self.overage_rate_per_notice) < 0:
            frappe.throw("Overage Rate Per Notice cannot be negative.")

    def get_limits(self):
        return {
            "notice_cap": cint(self.notice_cap or 0),
            "draft_cap": cint(self.draft_cap or 0),
            "gstin_cap": cint(self.gstin_cap or 0),
            "storage_cap": flt(self.storage_cap or 0),
            "api_calls_cap": cint(self.api_calls_cap or 0),
            "user_cap": cint(self.user_cap or 0),
        }

    def get_pricing(self):
        return {
            "price": flt(self.price or 0),
            "overage_rate_per_notice": flt(self.overage_rate_per_notice or 0),
        }

    def as_dict_for_api(self):
        return {
            "name": self.name,
            "plan_name": self.plan_name,
            "price": flt(self.price or 0),
            "notice_cap": cint(self.notice_cap or 0),
            "draft_cap": cint(self.draft_cap or 0),
            "gstin_cap": cint(self.gstin_cap or 0),
            "storage_cap": flt(self.storage_cap or 0),
            "api_calls_cap": cint(self.api_calls_cap or 0),
            "user_cap": cint(self.user_cap or 0),
            "overage_rate_per_notice": flt(self.overage_rate_per_notice or 0),
        }
