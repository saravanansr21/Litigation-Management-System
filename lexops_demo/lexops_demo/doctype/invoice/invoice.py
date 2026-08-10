# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Invoice(Document):
	def before_insert(self):
		if not self.invoice_number:
			self.invoice_number = self.name
