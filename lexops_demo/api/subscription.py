# Copyright (c) 2026, 6Force and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate, today

from lexops_demo.subscription.plan import Plan
from lexops_demo.subscription.subscription import Subscription
from lexops_demo.subscription.invoice import Invoice
from lexops_demo.subscription.payment import Payment


def _success(data=None, message=None):
    response = {"success": True}
    if message:
        response["message"] = message
    if data is not None:
        response["data"] = data
    return response


def _get_current_user():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."), frappe.AuthenticationError)
    return frappe.session.user


def _get_firm_profile():
    """
    Firm Profile is the tenant root and is a Single DocType.
    """
    user = _get_current_user()

    firm_profile = frappe.get_single("Firm Profile")

    # The supplied design does not define a User -> Firm Profile Link field.
    # Therefore the tenant is resolved from the single Firm Profile record.
    if not firm_profile:
        frappe.throw(_("Firm Profile is not configured."))

    if getattr(firm_profile, "status", None) == "Cancelled":
        frappe.throw(_("This Firm Profile is cancelled."))

    return firm_profile


def _require_admin():
    user = _get_current_user()
    allowed_roles = {"System Manager", "Administrator", "Admin"}

    if not allowed_roles.intersection(set(frappe.get_roles(user))):
        frappe.throw(_("Only an administrator can perform this action."), frappe.PermissionError)

    return user


def _get_subscription():
    firm = _get_firm_profile()

    subscription_name = frappe.db.get_value(
        "Subscription",
        {
            "firm_profile": firm.name,
            "status": ["in", ["Active", "Past Due"]],
        },
        "name",
        order_by="creation desc",
    )

    if not subscription_name:
        return None

    return frappe.get_doc("Subscription", subscription_name)


@frappe.whitelist(allow_guest=True)
def get_plans():
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_plans

    Public endpoint. The frontend uses this before subscription selection.
    """
    plans = frappe.get_all(
        "Plan",
        fields=[
            "name",
            "plan_name",
            "price",
            "notice_cap",
            "draft_cap",
            "gstin_cap",
            "storage_cap",
            "api_calls_cap",
            "user_cap",
            "overage_rate_per_notice",
        ],
        order_by="price asc",
    )

    return _success(plans)


@frappe.whitelist(allow_guest=True)
def get_plan(plan=None):
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_plan?plan=Practice
    """
    if not plan:
        frappe.throw(_("Plan is required."))

    if not frappe.db.exists("Plan", plan):
        frappe.throw(_("Plan {0} does not exist.").format(plan))

    doc = frappe.get_doc("Plan", plan)
    return _success(doc.as_dict_for_api())


@frappe.whitelist()
def get_current_subscription():
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_current_subscription
    """
    subscription = _get_subscription()

    if not subscription:
        return _success(None, "No active subscription found.")

    return _success(subscription.as_dict_for_api())


@frappe.whitelist()
def get_usage():
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_usage
    """
    subscription = _get_subscription()

    if not subscription:
        return _success(None, "No active subscription found.")

    return _success(subscription.get_usage_summary())


@frappe.whitelist()
def get_invoices(status=None, limit_start=0, limit_page_length=20):
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_invoices
    """
    subscription = _get_subscription()

    if not subscription:
        return _success([])

    filters = {"subscription": subscription.name}

    if status:
        filters["status"] = status

    invoices = frappe.get_all(
        "Invoice",
        filters=filters,
        fields=[
            "name",
            "invoice_number",
            "subscription",
            "date",
            "billing_period",
            "base_amount",
            "overage_amount",
            "gst_18",
            "total",
            "status",
            "pdf",
        ],
        order_by="date desc, creation desc",
        start=cint(limit_start),
        page_length=min(cint(limit_page_length or 20), 100),
    )

    return _success(invoices)


@frappe.whitelist()
def get_invoice(invoice=None):
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_invoice?invoice=INV-0001
    """
    if not invoice:
        frappe.throw(_("Invoice is required."))

    subscription = _get_subscription()

    if not subscription:
        frappe.throw(_("No active subscription found."))

    invoice_doc = frappe.get_doc("Invoice", invoice)

    if invoice_doc.subscription != subscription.name:
        frappe.throw(_("You are not allowed to access this invoice."), frappe.PermissionError)

    return _success(invoice_doc.as_dict_for_api())


@frappe.whitelist()
def get_payments(invoice=None, limit_start=0, limit_page_length=20):
    """
    GET:
    /api/method/lexops_demo.api.subscription.get_payments
    /api/method/lexops_demo.api.subscription.get_payments?invoice=INV-0001
    """
    subscription = _get_subscription()

    if not subscription:
        return _success([])

    filters = {}

    if invoice:
        invoice_doc = frappe.get_doc("Invoice", invoice)

        if invoice_doc.subscription != subscription.name:
            frappe.throw(_("You are not allowed to access this invoice."), frappe.PermissionError)

        filters["invoice"] = invoice
    else:
        invoice_names = frappe.get_all(
            "Invoice",
            filters={"subscription": subscription.name},
            pluck="name",
        )

        if not invoice_names:
            return _success([])

        filters["invoice"] = ["in", invoice_names]

    payments = frappe.get_all(
        "Payment",
        filters=filters,
        fields=[
            "name",
            "invoice",
            "paid_on",
            "amount",
            "payment_method",
            "reference_transaction_id",
        ],
        order_by="paid_on desc, creation desc",
        start=cint(limit_start),
        page_length=min(cint(limit_page_length or 20), 100),
    )

    return _success(payments)


@frappe.whitelist()
def create_subscription(plan=None, start_date=None):
    """
    POST:
    /api/method/lexops_demo.api.subscription.create_subscription

    Creates the first subscription for the current Firm Profile.
    Payment gateway integration is intentionally not performed here.
    """
    _require_admin()

    if not plan:
        frappe.throw(_("Plan is required."))

    if not frappe.db.exists("Plan", plan):
        frappe.throw(_("Selected Plan does not exist."))

    firm = _get_firm_profile()

    existing = frappe.db.exists(
        "Subscription",
        {
            "firm_profile": firm.name,
            "status": ["in", ["Active", "Past Due"]],
        },
    )

    if existing:
        frappe.throw(_("An active subscription already exists for this Firm Profile."))

    start = getdate(start_date or today())
    renewal = add_months(start, 1)

    subscription = frappe.new_doc("Subscription")
    subscription.firm_profile = firm.name
    subscription.plan = plan
    subscription.start_date = start
    subscription.renewal_date = renewal
    subscription.status = "Active"

    # Subscription.validate() copies all plan limits.
    subscription.insert()

    return _success(
        subscription.as_dict_for_api(),
        "Subscription created successfully.",
    )


@frappe.whitelist()
def change_plan(new_plan=None):
    """
    POST:
    /api/method/lexops_demo.api.subscription.change_plan

    The new plan is stored as pending_plan and takes effect on renewal.
    """
    _require_admin()

    if not new_plan:
        frappe.throw(_("New Plan is required."))

    subscription = _get_subscription()

    if not subscription:
        frappe.throw(_("No active subscription found."))

    subscription.request_plan_change(new_plan)
    frappe.db.commit()

    return _success(
        subscription.as_dict_for_api(),
        "Plan change scheduled for the next billing cycle.",
    )


@frappe.whitelist()
def cancel_subscription():
    """
    POST:
    /api/method/lexops_demo.api.subscription.cancel_subscription
    """
    _require_admin()

    subscription = _get_subscription()

    if not subscription:
        frappe.throw(_("No active subscription found."))

    subscription.cancel()
    frappe.db.commit()

    return _success(
        subscription.as_dict_for_api(),
        "Subscription cancelled.",
    )


@frappe.whitelist()
def record_payment(invoice=None, amount=None, payment_method=None, reference_transaction_id=None, paid_on=None):
    """
    POST:
    /api/method/lexops_demo.api.subscription.record_payment

    Administrative/manual payment recording endpoint.

    This is NOT a payment-gateway endpoint. Once a gateway is selected,
    gateway/webhook handling should call the Payment DocType directly after
    verifying the gateway transaction.
    """
    _require_admin()

    if not invoice:
        frappe.throw(_("Invoice is required."))

    invoice_doc = frappe.get_doc("Invoice", invoice)
    subscription = _get_subscription()

    if not subscription or invoice_doc.subscription != subscription.name:
        frappe.throw(_("You are not allowed to record payment for this invoice."), frappe.PermissionError)

    payment = frappe.new_doc("Payment")
    payment.invoice = invoice
    payment.amount = flt(amount)
    payment.payment_method = payment_method
    payment.reference_transaction_id = reference_transaction_id
    payment.paid_on = getdate(paid_on or today())

    payment.insert()

    return _success(
        {
            "payment": payment.as_dict_for_api(),
            "invoice": frappe.get_doc("Invoice", invoice).as_dict_for_api(),
        },
        "Payment recorded successfully.",
    )
