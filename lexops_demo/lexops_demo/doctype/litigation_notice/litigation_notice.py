# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LitigationNotice(Document):
	def before_insert(self):
		"""Compose the composite Notice ID: state code + financial year + form + sequence.
		Example: MH2024DRC01001 (matches the government reference where one exists).
		"""
		if not self.notice_id:
			self.notice_id = self._generate_notice_id()

	def _generate_notice_id(self):
		import frappe

		state_code = ""
		if self.gst_registration:
			state = frappe.db.get_value("GST Registration", self.gst_registration, "state")
			if state:
				state_code = (frappe.db.get_value("State", state, "state_name") or state)[:2].upper()

		fy = (self.financial_year or "").split("-")[0] or frappe.utils.nowdate()[:4]
		form = ""
		if self.notice_type:
			form = self.notice_type.replace("-", "")

		prefix = f"{state_code}{fy}{form}"
		last = frappe.db.sql(
			"select name from `tabLitigation Notice` where name like %s order by name desc limit 1",
			(prefix + "%",),
		)
		seq = 1
		if last:
			try:
				seq = int(last[0][0][len(prefix):]) + 1
			except ValueError:
				seq = 1
		return f"{prefix}{seq:03d}"
