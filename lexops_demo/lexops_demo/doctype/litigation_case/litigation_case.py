# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LitigationCase(Document):
	def on_update(self):
		"""A Final Closure row flips this case's Status to Closed."""
		if self.get("final_closure"):
			if self.status != "Closed":
				self.db_set("status", "Closed")
