# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate


# =======================================================================
# FIXED party / account lists for the ACM site - the report always shows
# exactly these suppliers, customers and "other accounts". No filter.
# =======================================================================
DEFAULT_SUPPLIERS = [
	"NINGBO ZT BULL HYDRAULIC CO., LTD.",
	"GUANGZHOU YAOZHONG JINYE CO. ITRITA (MAIN)",
	"GUANGZHOU RATOP MACHINERY PARTS CO.(MAIN)",
]

DEFAULT_CUSTOMERS = [
	"GULF SOLIDARITY CONTRACTING COMPANY",
	"Integrated Technical Contracting and Construction Company",
	"Saba Al- Arabia Contracting Co.",
	"Alpha Square Contracting Company",
	"ALROUM ALMAAMRI COMPANY FOR GENERAL CONTRACTING",
	"FAHAD SAUD AL HARBI GENERAL CONTRACTING CO.",
	"GREAT MOUNTAIN GENERAL CONTRACTING CO.",
	"مؤسسة جنى الجبيل للمقاولات",
	"LEGACY CRANES COMPANY",
]

DEFAULT_OTHER_ACCOUNTS = [
	"Salary Pakistan Account - ACM",
	"MUSCAT ALSAFWA INT. LLC - ACM",
	"AL-FORSAN CONTRACTING - ACM",
	"ACM CO. LTD KOREA - ACM",
]


def execute(filters=None):
	filters = filters or {}
	validate_filters(filters)

	columns = get_columns()

	executive_summary = get_executive_summary(filters)
	pos_summary = get_pos_summary(filters)
	cash_bank_used = get_cash_bank_accounts_used(filters)
	supplier_other = get_supplier_and_other_accounts(filters)
	customer_summary = get_customer_summary(filters)

	currency = get_company_currency(filters.get("company"))

	html = render_html(
		filters, currency, executive_summary, pos_summary, cash_bank_used,
		supplier_other, customer_summary
	)

	data = []
	return columns, data, html


def validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if getdate(filters["from_date"]) > getdate(filters["to_date"]):
		frappe.throw(_("From Date cannot be after To Date"))


def get_columns():
	return [
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 220},
		{"label": _("Account Type"), "fieldname": "account_type", "fieldtype": "Data", "width": 110},
		{"label": _("Opening Debit"), "fieldname": "opening_debit", "fieldtype": "Currency", "width": 120},
		{"label": _("Opening Credit"), "fieldname": "opening_credit", "fieldtype": "Currency", "width": 120},
		{"label": _("Period Debit"), "fieldname": "period_debit", "fieldtype": "Currency", "width": 120},
		{"label": _("Period Credit"), "fieldname": "period_credit", "fieldtype": "Currency", "width": 120},
		{"label": _("Closing Debit"), "fieldname": "closing_debit", "fieldtype": "Currency", "width": 120},
		{"label": _("Closing Credit"), "fieldname": "closing_credit", "fieldtype": "Currency", "width": 120},
		{"label": _("Net Balance"), "fieldname": "net_balance", "fieldtype": "Currency", "width": 130},
	]


def get_company_currency(company):
	return frappe.get_cached_value("Company", company, "default_currency") if company else None


def base_params(filters):
	return {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"company": filters.get("company"),
		"pos_profile": filters.get("pos_profile"),
		"mode_of_payment": filters.get("mode_of_payment"),
		"customer": filters.get("customer"),
		"supplier": filters.get("supplier"),
		"cost_center": filters.get("cost_center"),
		"project": filters.get("project"),
		"account": filters.get("account"),
	}


def cond(filters, key, column):
	return f" AND {column} = %({key})s" if filters.get(key) else ""


def get_conditions(filters, alias=""):
	p = f"{alias}." if alias else ""
	c = cond(filters, "company", f"{p}company")
	c += cond(filters, "cost_center", f"{p}cost_center")
	c += cond(filters, "project", f"{p}project")
	if filters.get("account"):
		c += cond(filters, "account", f"{p}account")
	return c


def get_doc_conditions(filters, alias):
	p = f"{alias}."
	c = cond(filters, "company", f"{p}company")
	c += cond(filters, "cost_center", f"{p}cost_center")
	c += cond(filters, "project", f"{p}project")
	return c


def get_pe_conditions(filters, alias="pe"):
	return cond(filters, "company", f"{alias}.company")


def get_simple_conditions(filters, alias):
	return cond(filters, "company", f"{alias}.company")


# =======================================================================
# SECTION 1 - Executive Summary
# =======================================================================

def get_executive_summary(filters):
	p = base_params(filters)
	include_credit_notes = int(filters.get("include_credit_notes", 1))

	sales_cond = get_doc_conditions(filters, "si")
	sales_cond += cond(filters, "pos_profile", "si.pos_profile")
	sales_cond += cond(filters, "customer", "si.customer")

	pos_sales = flt(frappe.db.sql(f"""
		SELECT SUM(base_grand_total) FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND is_pos = 1 AND is_return = 0
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {sales_cond}
	""", p)[0][0])

	normal_sales = flt(frappe.db.sql(f"""
		SELECT SUM(base_grand_total) FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND is_pos = 0 AND is_return = 0
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {sales_cond}
	""", p)[0][0])

	credit_notes = 0.0
	if include_credit_notes:
		credit_notes = flt(frappe.db.sql(f"""
			SELECT SUM(ABS(base_grand_total)) FROM `tabSales Invoice` si
			WHERE docstatus = 1 AND is_return = 1
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {sales_cond}
		""", p)[0][0])

	total_sales = pos_sales + normal_sales
	net_sales = total_sales - credit_notes

	pos_collections = flt(frappe.db.sql(f"""
		SELECT SUM(sip.base_amount) FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE si.docstatus = 1 AND si.is_pos = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s {sales_cond}
	""", p)[0][0])

	pe_cond = get_pe_conditions(filters) + cond(filters, "customer", "pe.party") + cond(filters, "mode_of_payment", "pe.mode_of_payment")
	pe_collections = flt(frappe.db.sql(f"""
		SELECT SUM(pe.base_paid_amount) FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive' AND pe.party_type = 'Customer'
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s {pe_cond}
	""", p)[0][0])

	total_collections = pos_collections + pe_collections

	purchase_cond = get_doc_conditions(filters, "pi") + cond(filters, "supplier", "pi.supplier")
	total_purchases = flt(frappe.db.sql(f"""
		SELECT SUM(base_grand_total) FROM `tabPurchase Invoice` pi
		WHERE docstatus = 1 AND is_return = 0
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {purchase_cond}
	""", p)[0][0])

	gl_cond = get_conditions(filters, "gle")
	customer_receivable = flt(frappe.db.sql(f"""
		SELECT SUM(debit - credit) FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Customer' AND posting_date <= %(to_date)s
			{gl_cond}{cond(filters, 'customer', 'gle.party')}
	""", p)[0][0])

	supplier_payable = flt(frappe.db.sql(f"""
		SELECT SUM(credit - debit) FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Supplier' AND posting_date <= %(to_date)s
			{gl_cond}{cond(filters, 'supplier', 'gle.party')}
	""", p)[0][0])

	cb = get_cash_bank_totals(filters)

	return {
		"total_sales": total_sales, "pos_sales": pos_sales, "normal_sales": normal_sales,
		"credit_notes": credit_notes, "net_sales": net_sales,
		"total_collections": total_collections, "total_purchases": total_purchases,
		"customer_receivable": customer_receivable, "supplier_payable": supplier_payable,
		"cash_balance": cb["cash_total"], "bank_balance": cb["bank_total"],
		"cash_plus_bank": cb["grand_total"],
	}


def get_cash_bank_totals(filters):
	p = base_params(filters)
	gl_cond = get_conditions(filters, "gle")
	rows = frappe.db.sql(f"""
		SELECT acc.account_type AS account_type,
			SUM(CASE WHEN gle.posting_date <= %(to_date)s THEN gle.debit - gle.credit ELSE 0 END) AS balance
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0 AND acc.account_type IN ('Cash', 'Bank') {gl_cond}
		GROUP BY acc.account_type
	""", p, as_dict=True)
	cash_total = sum(flt(r.balance) for r in rows if r.account_type == "Cash")
	bank_total = sum(flt(r.balance) for r in rows if r.account_type == "Bank")
	return {"cash_total": cash_total, "bank_total": bank_total, "grand_total": cash_total + bank_total}


# =======================================================================
# SECTION 2 - POS Profile Summary
# =======================================================================

def get_pos_openings(filters):
	p = base_params(filters)
	c = get_simple_conditions(filters, "poe") + cond(filters, "pos_profile", "poe.pos_profile")
	rows = frappe.db.sql(f"""
		SELECT poe.pos_profile AS pos_profile, SUM(poed.opening_amount) AS amount
		FROM `tabPOS Opening Entry` poe
		INNER JOIN `tabPOS Opening Entry Detail` poed ON poed.parent = poe.name
		WHERE poe.docstatus = 1 AND DATE(poe.period_start_date) BETWEEN %(from_date)s AND %(to_date)s {c}
		GROUP BY poe.pos_profile
	""", p, as_dict=True)
	return {r.pos_profile: flt(r.amount) for r in rows}


def get_branch_gl_movement(filters, before_date=False):
	p = base_params(filters)
	si_extra = cond(filters, "pos_profile", "si.pos_profile") + cond(filters, "company", "si.company")
	date_cond = "gle.posting_date < %(from_date)s" if before_date else "gle.posting_date BETWEEN %(from_date)s AND %(to_date)s"

	rows = frappe.db.sql(f"""
		SELECT si.pos_profile AS pos_profile, SUM(gle.debit - gle.credit) AS amount
		FROM `tabGL Entry` gle
		INNER JOIN `tabSales Invoice` si ON si.name = gle.voucher_no AND gle.voucher_type = 'Sales Invoice'
		WHERE gle.is_cancelled = 0 AND si.is_pos = 1 AND {date_cond} {si_extra}
		GROUP BY si.pos_profile

		UNION ALL

		SELECT si.pos_profile AS pos_profile, SUM(gle.debit - gle.credit) AS amount
		FROM `tabGL Entry` gle
		INNER JOIN `tabPayment Entry Reference` per ON per.parent = gle.voucher_no
		INNER JOIN `tabSales Invoice` si ON si.name = per.reference_name AND per.reference_doctype = 'Sales Invoice'
		WHERE gle.is_cancelled = 0 AND gle.voucher_type = 'Payment Entry' AND si.is_pos = 1 AND {date_cond} {si_extra}
		GROUP BY si.pos_profile
	""", p, as_dict=True)

	result = {}
	for r in rows:
		result[r.pos_profile] = result.get(r.pos_profile, 0.0) + flt(r.amount)
	return result


def get_pos_summary(filters):
	p = base_params(filters)
	include_credit_notes = int(filters.get("include_credit_notes", 1))

	si_cond = get_doc_conditions(filters, "si") + cond(filters, "pos_profile", "si.pos_profile") + cond(filters, "customer", "si.customer")

	profiles = frappe.db.sql(f"""
		SELECT DISTINCT pos_profile FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND is_pos = 1 AND pos_profile IS NOT NULL
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {si_cond}
	""", p, as_dict=True)
	profile_names = [r.pos_profile for r in profiles]
	if not profile_names:
		return []

	gross_map = {r.pos_profile: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT pos_profile, SUM(base_grand_total) AS amount FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND is_pos = 1 AND is_return = 0
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {si_cond}
		GROUP BY pos_profile
	""", p, as_dict=True)}

	returns_map = {}
	if include_credit_notes:
		returns_map = {r.pos_profile: flt(r.amount) for r in frappe.db.sql(f"""
			SELECT pos_profile, SUM(ABS(base_grand_total)) AS amount FROM `tabSales Invoice` si
			WHERE docstatus = 1 AND is_pos = 1 AND is_return = 1
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {si_cond}
			GROUP BY pos_profile
		""", p, as_dict=True)}

	payment_cond = cond(filters, "mode_of_payment", "sip.mode_of_payment")
	payment_map = {r.pos_profile: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT si.pos_profile AS pos_profile, SUM(sip.base_amount) AS amount
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE si.docstatus = 1 AND si.is_pos = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s {si_cond}{payment_cond}
		GROUP BY si.pos_profile
	""", p, as_dict=True)}

	pos_opening_map = get_pos_openings(filters)
	financial_opening_map = get_branch_gl_movement(filters, before_date=True)
	period_movement_map = get_branch_gl_movement(filters, before_date=False)

	rows = []
	for profile in profile_names:
		gross = gross_map.get(profile, 0.0)
		returns = returns_map.get(profile, 0.0)
		net_sales = gross - returns
		payments = payment_map.get(profile, 0.0)
		financial_opening = financial_opening_map.get(profile, 0.0)
		rows.append({
			"pos_profile": profile,
			"pos_opening": pos_opening_map.get(profile, 0.0),
			"financial_opening": financial_opening,
			"gross_sales": gross, "returns": returns, "net_sales": net_sales,
			"payments": payments, "difference": flt(net_sales - payments),
			"closing_financial": financial_opening + period_movement_map.get(profile, 0.0),
		})
	return sorted(rows, key=lambda r: r["pos_profile"])


# =======================================================================
# SECTION 3 - Cash & Bank Accounts Used
# =======================================================================

def get_cash_bank_accounts_used(filters):
	"""Every Cash / Bank account of the company (even zero activity), fully
	GL-reconciled per account:

	Opening  = balance strictly before From Date
	Invoice  = net GL movement from Sales Invoice / POS Invoice vouchers
	Payments = net GL movement from Payment Entry vouchers
	JV Debit / JV Credit = journal entry legs during the period
	Other    = net movement from every remaining voucher type
	Closing  = Opening + Invoice + Payments + JV Debit - JV Credit + Other
	           (= GL balance of the account at To Date - matches GL/Trial Balance)
	"""
	p = base_params(filters)
	gl_cond = get_conditions(filters, "gle")

	rows = frappe.db.sql(f"""
		SELECT acc.name AS account, acc.account_type AS account_type,
			COALESCE(g.opening, 0) AS opening,
			COALESCE(g.invoice_amount, 0) AS invoice_amount,
			COALESCE(g.payment_amount, 0) AS payment_amount,
			COALESCE(g.jv_debit, 0) AS jv_debit,
			COALESCE(g.jv_credit, 0) AS jv_credit,
			COALESCE(g.other_amount, 0) AS other_amount,
			COALESCE(g.txn_count, 0) AS txn_count
		FROM `tabAccount` acc
		LEFT JOIN (
			SELECT gle.account AS account,
				SUM(CASE WHEN gle.posting_date < %(from_date)s THEN gle.debit - gle.credit ELSE 0 END) AS opening,
				SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
							AND gle.voucher_type IN ('Sales Invoice', 'POS Invoice') THEN gle.debit - gle.credit ELSE 0 END) AS invoice_amount,
				SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
							AND gle.voucher_type = 'Payment Entry' THEN gle.debit - gle.credit ELSE 0 END) AS payment_amount,
				SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
							AND gle.voucher_type = 'Journal Entry' THEN gle.debit ELSE 0 END) AS jv_debit,
				SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
							AND gle.voucher_type = 'Journal Entry' THEN gle.credit ELSE 0 END) AS jv_credit,
				SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
							AND gle.voucher_type NOT IN ('Sales Invoice', 'POS Invoice', 'Payment Entry', 'Journal Entry')
							THEN gle.debit - gle.credit ELSE 0 END) AS other_amount,
				COUNT(DISTINCT gle.voucher_no) AS txn_count
			FROM `tabGL Entry` gle
			WHERE gle.is_cancelled = 0 {gl_cond}
			GROUP BY gle.account
		) g ON g.account = acc.name
		WHERE acc.company = %(company)s
			AND acc.account_type IN ('Cash', 'Bank')
			AND acc.is_group = 0
		GROUP BY acc.name, acc.account_type
		ORDER BY acc.account_type, acc.name
	""", p, as_dict=True)

	for r in rows:
		r["period_movement"] = (flt(r.invoice_amount) + flt(r.payment_amount)
			+ flt(r.jv_debit) - flt(r.jv_credit) + flt(r.other_amount))
		r["closing"] = flt(r.opening) + flt(r.period_movement)
	return rows



def get_account_opening_balance(account, from_date, company=None):
	filters_p = {"account": account, "from_date": from_date, "company": company}
	c = " AND company = %(company)s" if company else ""
	row = frappe.db.sql(f"""
		SELECT SUM(debit) - SUM(credit) AS balance FROM `tabGL Entry`
		WHERE account = %(account)s AND posting_date < %(from_date)s AND is_cancelled = 0 {c}
	""", filters_p, as_dict=True)
	return flt(row[0].balance) if row and row[0].balance else 0.0


def get_cash_bank_mode_of_payment(filters):
	p = base_params(filters)

	sip_cond = get_doc_conditions(filters, "si") + cond(filters, "pos_profile", "si.pos_profile") + cond(filters, "mode_of_payment", "sip.mode_of_payment")
	invoice_rows = frappe.db.sql(f"""
		SELECT sip.account AS account, sip.mode_of_payment AS mode_of_payment, SUM(sip.base_amount) AS amount
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		INNER JOIN `tabAccount` acc ON acc.name = sip.account
		WHERE si.docstatus = 1 AND acc.account_type IN ('Cash', 'Bank')
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s {sip_cond}
		GROUP BY sip.account, sip.mode_of_payment
	""", p, as_dict=True)

	pe_cond = get_pe_conditions(filters) + cond(filters, "mode_of_payment", "pe.mode_of_payment")
	pe_receive_rows = frappe.db.sql(f"""
		SELECT pe.paid_to AS account, pe.mode_of_payment AS mode_of_payment, SUM(pe.base_paid_amount) AS amount
		FROM `tabPayment Entry` pe
		INNER JOIN `tabAccount` acc ON acc.name = pe.paid_to
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive' AND acc.account_type IN ('Cash', 'Bank')
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s {pe_cond}
		GROUP BY pe.paid_to, pe.mode_of_payment
	""", p, as_dict=True)

	pe_pay_rows = frappe.db.sql(f"""
		SELECT pe.paid_from AS account, pe.mode_of_payment AS mode_of_payment, SUM(pe.base_paid_amount) AS amount
		FROM `tabPayment Entry` pe
		INNER JOIN `tabAccount` acc ON acc.name = pe.paid_from
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Pay' AND acc.account_type IN ('Cash', 'Bank')
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s {pe_cond}
		GROUP BY pe.paid_from, pe.mode_of_payment
	""", p, as_dict=True)

	result = {}

	def bucket(account, mop):
		key = (account, mop or "Not Set")
		return result.setdefault(key, {"account": account, "mode_of_payment": mop or "Not Set", "invoice_amount": 0.0, "payment_amount": 0.0})

	for r in invoice_rows:
		bucket(r.account, r.mode_of_payment)["invoice_amount"] += flt(r.amount)
	for r in pe_receive_rows:
		bucket(r.account, r.mode_of_payment)["invoice_amount"] += flt(r.amount)
	for r in pe_pay_rows:
		bucket(r.account, r.mode_of_payment)["payment_amount"] += flt(r.amount)

	rows = list(result.values())
	for r in rows:
		r["opening"] = get_account_opening_balance(r["account"], filters.get("from_date"), filters.get("company"))
		r["balance"] = flt(r["opening"]) + flt(r["invoice_amount"]) - flt(r["payment_amount"])

	return sorted(rows, key=lambda r: (r["account"], r["mode_of_payment"]))


# =======================================================================
# SECTION 5 - Supplier & Other Accounts (whitelisted only)
# =======================================================================

def parse_name_list(text):
	"""Split a semicolon-separated filter value into a clean list of names."""
	if not text:
		return []
	return [x.strip() for x in text.split(";") if x.strip()]


def get_other_accounts_summary(filters):
	accounts = [a for a in DEFAULT_OTHER_ACCOUNTS if frappe.db.exists("Account", a)]
	if not accounts:
		return []

	p = dict(base_params(filters), accounts=accounts)
	gl_cond = get_conditions(filters, "gle")

	rows = frappe.db.sql(f"""
		SELECT account,
			SUM(CASE WHEN posting_date < %(from_date)s THEN debit - credit ELSE 0 END) AS opening,
			SUM(CASE WHEN posting_date BETWEEN %(from_date)s AND %(to_date)s THEN debit ELSE 0 END) AS period_debit,
			SUM(CASE WHEN posting_date BETWEEN %(from_date)s AND %(to_date)s THEN credit ELSE 0 END) AS period_credit
		FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND account IN %(accounts)s {gl_cond}
		GROUP BY account
	""", p, as_dict=True)

	row_map = {}
	for r in rows:
		r["balance"] = flt(r.opening) + flt(r.period_debit) - flt(r.period_credit)
		row_map[r.account] = r

	result = []
	for account in accounts:
		if account in row_map:
			result.append(row_map[account])
		else:
			# show the account even when it has zero activity in the period
			result.append(frappe._dict({
				"account": account,
				"opening": 0.0, "period_debit": 0.0,
				"period_credit": 0.0, "balance": 0.0,
			}))
	return result


def get_supplier_and_other_accounts(filters):
	p = base_params(filters)
	include_journal = int(filters.get("include_journal_adjustments", 1))

	supplier_list = list(DEFAULT_SUPPLIERS)

	gl_cond = get_conditions(filters, "gle")
	gl_supplier_filter = ""
	if supplier_list:
		p["supplier_list"] = supplier_list
		gl_supplier_filter = " AND party IN %(supplier_list)s"

	opening_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Supplier' AND posting_date < %(from_date)s
			{gl_cond}{gl_supplier_filter}
		GROUP BY party
	""", p, as_dict=True)}

	debit_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(debit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Supplier'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}{gl_supplier_filter}
		GROUP BY party
	""", p, as_dict=True)}

	credit_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Supplier'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}{gl_supplier_filter}
		GROUP BY party
	""", p, as_dict=True)}

	closing_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Supplier' AND posting_date <= %(to_date)s
			{gl_cond}{gl_supplier_filter}
		GROUP BY party
	""", p, as_dict=True)}

	if not include_journal:
		je_rows = frappe.db.sql(f"""
			SELECT party, SUM(debit) AS d, SUM(credit) AS c FROM `tabGL Entry` gle
			WHERE is_cancelled = 0 AND party_type = 'Supplier' AND voucher_type = 'Journal Entry'
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}{gl_supplier_filter}
			GROUP BY party
		""", p, as_dict=True)
		for r in je_rows:
			debit_map[r.party] = debit_map.get(r.party, 0.0) - flt(r.d)
			credit_map[r.party] = credit_map.get(r.party, 0.0) - flt(r.c)

	parties = set(supplier_list) if supplier_list else (
		set(opening_map) | set(debit_map) | set(credit_map) | set(closing_map)
	)

	rows = []
	for party in parties:
		rows.append({
			"name": party, "type": "Supplier",
			"opening": opening_map.get(party, 0.0),
			"debit": debit_map.get(party, 0.0),
			"credit": credit_map.get(party, 0.0),
			"balance": closing_map.get(party, opening_map.get(party, 0.0)),
		})

	for r in get_other_accounts_summary(filters):
		rows.append({
			"name": r.account, "type": "Account",
			"opening": flt(r.opening), "debit": flt(r.period_debit),
			"credit": flt(r.period_credit), "balance": flt(r.balance),
		})

	return sorted(rows, key=lambda r: (r["type"], r["name"]))


# =======================================================================
# SECTION 6 - Customer Balance (whitelisted only)
# =======================================================================

def get_customer_summary(filters):
	p = base_params(filters)

	customer_list = list(DEFAULT_CUSTOMERS)

	gl_cond = get_conditions(filters, "gle")
	gl_customer_filter = ""
	if customer_list:
		p["customer_list"] = customer_list
		gl_customer_filter = " AND party IN %(customer_list)s"

	opening_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Customer' AND posting_date < %(from_date)s
			{gl_cond}{gl_customer_filter}
		GROUP BY party
	""", p, as_dict=True)}

	closing_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND party_type = 'Customer' AND posting_date <= %(to_date)s
			{gl_cond}{gl_customer_filter}
		GROUP BY party
	""", p, as_dict=True)}

	si_cond = get_doc_conditions(filters, "si")
	si_customer_filter = " AND customer IN %(customer_list)s" if customer_list else ""
	invoice_map = {r.customer: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT customer, SUM(base_grand_total) AS amount FROM `tabSales Invoice` si
		WHERE docstatus = 1 AND is_return = 0
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {si_cond}{si_customer_filter}
		GROUP BY customer
	""", p, as_dict=True)}

	pe_cond = get_pe_conditions(filters)
	pe_customer_filter = " AND party IN %(customer_list)s" if customer_list else ""
	payment_map = {r.party: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT party, SUM(base_paid_amount) AS amount FROM `tabPayment Entry` pe
		WHERE docstatus = 1 AND payment_type = 'Receive' AND party_type = 'Customer'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {pe_cond}{pe_customer_filter}
		GROUP BY party
	""", p, as_dict=True)}

	customers = set(customer_list) if customer_list else (
		set(opening_map) | set(closing_map) | set(invoice_map) | set(payment_map)
	)

	rows = []
	for c in customers:
		rows.append({
			"customer": c,
			"opening": opening_map.get(c, 0.0),
			"invoice": invoice_map.get(c, 0.0),
			"payment": payment_map.get(c, 0.0),
			"balance": closing_map.get(c, opening_map.get(c, 0.0)),
		})
	return sorted(rows, key=lambda r: r["customer"])


# =======================================================================
# SECTION 7 - Cost Center Performance
# =======================================================================

def get_cost_center_summary(filters):
	p = base_params(filters)
	include_journal = int(filters.get("include_journal_adjustments", 1))
	gl_cond = get_conditions(filters, "gle")

	opening_map = {r.cost_center: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT cost_center, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND cost_center IS NOT NULL AND posting_date < %(from_date)s {gl_cond}
		GROUP BY cost_center
	""", p, as_dict=True)}

	sales_map = {r.cost_center: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT cost_center, SUM(debit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND cost_center IS NOT NULL AND voucher_type IN ('Sales Invoice', 'POS Invoice')
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY cost_center
	""", p, as_dict=True)}

	expense_map = {r.cost_center: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT gle.cost_center AS cost_center, SUM(gle.debit) AS amount FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0 AND gle.cost_center IS NOT NULL AND acc.root_type = 'Expense'
			AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY gle.cost_center
	""", p, as_dict=True)}

	credit_map = {r.cost_center: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT cost_center, SUM(credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND cost_center IS NOT NULL
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY cost_center
	""", p, as_dict=True)}

	journal_map = {}
	if include_journal:
		journal_map = {r.cost_center: flt(r.amount) for r in frappe.db.sql(f"""
			SELECT cost_center, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
			WHERE is_cancelled = 0 AND cost_center IS NOT NULL AND voucher_type = 'Journal Entry'
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
			GROUP BY cost_center
		""", p, as_dict=True)}

	period_net_map = {r.cost_center: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT cost_center, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND cost_center IS NOT NULL
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY cost_center
	""", p, as_dict=True)}

	cost_centers = set(opening_map) | set(sales_map) | set(expense_map) | set(credit_map) | set(journal_map)
	if filters.get("cost_center"):
		cost_centers &= {filters.get("cost_center")}

	rows = []
	for cc in cost_centers:
		opening = opening_map.get(cc, 0.0)
		rows.append({
			"cost_center": cc, "opening": opening,
			"sales_debit": sales_map.get(cc, 0.0), "expenses": expense_map.get(cc, 0.0),
			"credit": credit_map.get(cc, 0.0), "journal_adjustments": journal_map.get(cc, 0.0),
			"closing": opening + period_net_map.get(cc, 0.0),
		})
	return sorted(rows, key=lambda r: r["cost_center"])


# =======================================================================
# SECTION 8 - Project Performance
# =======================================================================

def get_project_summary(filters):
	p = base_params(filters)
	include_journal = int(filters.get("include_journal_adjustments", 1))
	gl_cond = get_conditions(filters, "gle")

	opening_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT project, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND project IS NOT NULL AND posting_date < %(from_date)s {gl_cond}
		GROUP BY project
	""", p, as_dict=True)}

	sales_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT project, SUM(debit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND project IS NOT NULL AND voucher_type IN ('Sales Invoice', 'POS Invoice')
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY project
	""", p, as_dict=True)}

	purchase_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT project, SUM(debit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND project IS NOT NULL AND voucher_type = 'Purchase Invoice'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY project
	""", p, as_dict=True)}

	expense_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT gle.project AS project, SUM(gle.debit) AS amount FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0 AND gle.project IS NOT NULL AND acc.root_type = 'Expense'
			AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY gle.project
	""", p, as_dict=True)}

	payment_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT project, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND project IS NOT NULL AND voucher_type = 'Payment Entry'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY project
	""", p, as_dict=True)}

	journal_map = {}
	if include_journal:
		journal_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
			SELECT project, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
			WHERE is_cancelled = 0 AND project IS NOT NULL AND voucher_type = 'Journal Entry'
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
			GROUP BY project
		""", p, as_dict=True)}

	period_net_map = {r.project: flt(r.amount) for r in frappe.db.sql(f"""
		SELECT project, SUM(debit - credit) AS amount FROM `tabGL Entry` gle
		WHERE is_cancelled = 0 AND project IS NOT NULL
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_cond}
		GROUP BY project
	""", p, as_dict=True)}

	projects = set(opening_map) | set(sales_map) | set(purchase_map) | set(expense_map) | set(payment_map) | set(journal_map)
	if filters.get("project"):
		projects &= {filters.get("project")}

	rows = []
	for proj in projects:
		opening = opening_map.get(proj, 0.0)
		rows.append({
			"project": proj, "opening": opening,
			"sales": sales_map.get(proj, 0.0), "purchases": purchase_map.get(proj, 0.0),
			"expenses": expense_map.get(proj, 0.0), "payments": payment_map.get(proj, 0.0),
			"journal_adjustments": journal_map.get(proj, 0.0),
			"closing": opening + period_net_map.get(proj, 0.0),
		})
	return sorted(rows, key=lambda r: r["project"])


# =======================================================================
# SECTION 9 - Journal Entry Adjustments
# =======================================================================

def get_journal_adjustments(filters):
	if not int(filters.get("include_journal_adjustments", 1)):
		return []

	p = base_params(filters)
	c = cond(filters, "company", "je.company")
	c += cond(filters, "cost_center", "jea.cost_center")
	c += cond(filters, "project", "jea.project")
	c += cond(filters, "account", "jea.account")
	if filters.get("customer"):
		c += " AND jea.party_type = 'Customer'" + cond(filters, "customer", "jea.party")
	if filters.get("supplier"):
		c += " AND jea.party_type = 'Supplier'" + cond(filters, "supplier", "jea.party")

	return frappe.db.sql(f"""
		SELECT je.name AS journal_entry, je.posting_date AS posting_date,
			jea.account AS account, jea.party_type AS party_type, jea.party AS party,
			jea.cost_center AS cost_center, jea.project AS project,
			jea.debit AS debit, jea.credit AS credit, je.user_remark AS remarks
		FROM `tabJournal Entry Account` jea
		INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
		WHERE je.docstatus = 1 AND je.posting_date BETWEEN %(from_date)s AND %(to_date)s {c}
		ORDER BY je.posting_date DESC, je.name
	""", p, as_dict=True)


# =======================================================================
# SECTION 10 - Complete GL Summary (Reconciliation)
# =======================================================================

def get_gl_summary(filters):
	"""Account-wise GL summary taken directly from ERPNext's own Trial
	Balance engine (leaf accounts only) - so every Opening / Period /
	Closing figure here is EXACTLY what the GL / Trial Balance shows.
	Returns rows with opening_debit/credit, period_debit/credit,
	closing_debit/credit and net_balance (closing debit - closing credit)."""
	from erpnext.accounts.report.trial_balance.trial_balance import execute as tb_exec

	company = filters.get("company")
	f_from = filters.get("from_date")
	f_to = filters.get("to_date")

	fiscal_year = None
	for fy in frappe.db.get_all("Fiscal Year", fields=["name", "year_start_date", "year_end_date"]):
		if str(fy["year_start_date"])[:10] <= f_from <= str(fy["year_end_date"])[:10]:
			fiscal_year = fy["name"]
			break
	if not fiscal_year:
		all_fy = frappe.db.get_all("Fiscal Year", fields=["name", "year_start_date"])
		fiscal_year = all_fy[0]["name"] if all_fy else None

	if not fiscal_year:
		return []

	res = tb_exec(frappe._dict({
		"company": company,
		"from_date": f_from,
		"to_date": f_to,
		"fiscal_year": fiscal_year,
		"period_start_date": f_from,
		"period_end_date": f_to,
		"show_zero_values": 0,
		"show_unposted": 0,
	}))
	data = res[1] if len(res) > 1 else []

	rows = []
	for row in data:
		acct = row.get("account")
		if not acct or not frappe.db.exists("Account", acct):
			continue
		is_group = frappe.db.get_value("Account", acct, "is_group")
		if is_group:
			continue
		op_dr = flt(row.get("opening_debit"))
		op_cr = flt(row.get("opening_credit"))
		p_dr = flt(row.get("debit"))
		p_cr = flt(row.get("credit"))
		cl_dr = op_dr + p_dr
		cl_cr = op_cr + p_cr
		rows.append(frappe._dict({
			"account": acct,
			"account_type": frappe.db.get_value("Account", acct, "account_type") or "",
			"opening_debit": op_dr,
			"opening_credit": op_cr,
			"period_debit": p_dr,
			"period_credit": p_cr,
			"closing_debit": cl_dr,
			"closing_credit": cl_cr,
			"net_balance": cl_dr - cl_cr,
		}))
	return sorted(rows, key=lambda r: (r["account_type"] or "", r["account"]))


# =======================================================================
# HTML rendering
# =======================================================================

def money(amount, currency):
	return fmt_money(flt(amount), currency=currency)


def kpi_card(label, value, currency, color="#6c757d"):
	return f"""<div class="kpi-card" style="border-color:{color};"><h5>{label}</h5><h2 style="color:{color};">{money(value, currency)}</h2></div>"""


def diff_badge(diff):
	if abs(flt(diff)) < 0.01:
		return '<span style="background:#28a745;color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">✓ Reconciled</span>'
	return '<span style="background:#dc3545;color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">⚠ Difference</span>'


def render_html(filters, currency, summary, pos_summary, cash_bank_used,
	supplier_other, customers):

	kpi_html = "".join([
		kpi_card("Total Sales", summary["total_sales"], currency, "#343a40"),
		kpi_card("POS Sales", summary["pos_sales"], currency, "#007bff"),
		kpi_card("Normal Sales", summary["normal_sales"], currency, "#17a2b8"),
		kpi_card("Credit Notes / Returns", summary["credit_notes"], currency, "#dc3545"),
		kpi_card("Net Sales", summary["net_sales"], currency, "#28a745"),
		kpi_card("Total Collections", summary["total_collections"], currency, "#20c997"),
		kpi_card("Total Purchases", summary["total_purchases"], currency, "#fd7e14"),
		kpi_card("Customer Receivable", summary["customer_receivable"], currency, "#6f42c1"),
		kpi_card("Supplier Payable", summary["supplier_payable"], currency, "#e83e8c"),
		kpi_card("Cash Balance", summary["cash_balance"], currency, "#20c997"),
		kpi_card("Bank Balance", summary["bank_balance"], currency, "#0d6efd"),
		kpi_card("Cash + Bank Balance", summary["cash_plus_bank"], currency, "#198754"),
	])

	gl_badge = ''

	company_name = filters.get("company") or "-"
	fd = str(filters.get("from_date") or "")[:10]
	td = str(filters.get("to_date") or "")[:10]

	# [COMMENTED - not needed] report header / legend info removed
	report_header_html = """
	<div class="report-header">
		<div>
			<h2>Business Financial Report</h2>
			<div class="meta">Company: <b>{company_name}</b> &nbsp;|&nbsp; Period: <b>{fd}</b> to <b>{td}</b> &nbsp;|&nbsp; Currency: <b>{currency}</b></div>
			<div class="meta">Generated: {generated}</div>
		</div>
		<div class="meta" style="margin-left:auto;text-align:right;">
			<b>Basis (all figures from ERPNext GL Entry unless noted)</b><br>
			Opening = balance strictly before From Date &nbsp;•&nbsp; Closing = Opening + Period<br>
			Sign: positive = Debit, negative = Credit<br>
			Section 2 uses Sales Invoice / POS Opening Entry vouchers
		</div>
	</div>""".format(company_name=company_name, fd=fd, td=td, currency=currency,
		generated=frappe.utils.formatdate(frappe.utils.nowdate()))

	# [COMMENTED - not needed]
	filters_legend = """
	<div class="basis-note">
		<b>Filters - kaunse section ko kaise control karte hain:</b><br>
		• <b>From / To Date</b> &amp; <b>Company</b>: har section (mandatory)<br>
		• <b>POS Profile</b>: Section 2 (POS Profile Summary)<br>
		• <b>Mode of Payment</b>: Section 2 (Collections)<br>
		• <b>Customer</b>: Section 1 (Sales / Collections / Receivable) aur Section 5 (Customer Balance fixed list alag hai)<br>
		• <b>Supplier</b>: Section 1 (Purchases)<br>
		• <b>Include Credit Notes</b>: Section 1 &amp; 2 (returns)<br>
		<b>Sections 4 (Supplier &amp; Other Accounts) aur 5 (Customer Balance):</b> fixed lists - har waqt wohi names, filters se change nahi hote.
	<div class="basis-note">
		<b>Filters - kaunse section ko kaise control karte hain:</b><br>
		• <b>From / To Date</b> &amp; <b>Company</b>: har section (mandatory)<br>
		• <b>POS Profile</b>: Section 1 (POS Sales), 2, 4<br>
		• <b>Mode of Payment</b>: Section 1 (Collections), 2 (Collections), 4<br>
		• <b>Customer</b>: Section 1 (Sales/Collections/Receivable), 2, 9 (Journal party)<br>
		• <b>Supplier</b>: Section 1 (Purchases), 9 (Journal party) &nbsp;• Section 5 hamesha fixed supplier list<br>
		• <b>Cost Center / Project / Account</b>: GL-based sections 1 (balances), 3, 7, 8, 9, 10<br>
		• <b>Include Credit Notes</b>: Section 1 &amp; 2 returns column<br>
		• <b>Include Journal Adjustments</b>: Section 1-8 journal effects, Section 9 list<br>
		<b>Section 5 &amp; 6:</b> fixed lists (suppliers/customers/accounts) - har waqt wohi names, filters se change nahi hote.
	</div>"""


	pos_rows_html = ""
	if pos_summary:
		totals = {k: 0.0 for k in ("pos_opening", "financial_opening", "gross_sales", "returns", "net_sales", "payments", "closing_financial")}
		for r in pos_summary:
			for k in totals:
				totals[k] += flt(r[k])

		pos_rows_html += f"""<tr style="background:#eef6ff;font-weight:700;">
			<td>Opening (all branches)</td>
			<td style='text-align:right;'>{money(totals['pos_opening'], currency)}</td>
			<td style='text-align:right;'>{money(totals['financial_opening'], currency)}</td>
			<td colspan='6'></td>
		</tr>"""

		for r in pos_summary:
			pos_rows_html += f"""<tr>
				<td>{r['pos_profile']}</td>
				<td style='text-align:right;'>{money(r['pos_opening'], currency)}</td>
				<td style='text-align:right;'>{money(r['financial_opening'], currency)}</td>
				<td style='text-align:right;'>{money(r['gross_sales'], currency)}</td>
				<td style='text-align:right;'>{money(r['returns'], currency)}</td>
				<td style='text-align:right;'>{money(r['net_sales'], currency)}</td>
				<td style='text-align:right;'>{money(r['payments'], currency)}</td>
				<td style='text-align:right;'>{money(r['difference'], currency)} {diff_badge(r['difference'])}</td>
				<td style='text-align:right;'>{money(r['closing_financial'], currency)}</td>
			</tr>"""

		pos_rows_html += f"""<tr style="background:#f8f9fa;font-weight:700;border-top:2px solid #343a40;">
			<td>Total</td>
			<td style='text-align:right;'>{money(totals['pos_opening'], currency)}</td>
			<td style='text-align:right;'>{money(totals['financial_opening'], currency)}</td>
			<td style='text-align:right;'>{money(totals['gross_sales'], currency)}</td>
			<td style='text-align:right;'>{money(totals['returns'], currency)}</td>
			<td style='text-align:right;'>{money(totals['net_sales'], currency)}</td>
			<td style='text-align:right;'>{money(totals['payments'], currency)}</td>
			<td style='text-align:right;'>{money(totals['net_sales'] - totals['payments'], currency)}</td>
			<td style='text-align:right;'>{money(totals['closing_financial'], currency)}</td>
		</tr>"""
	else:
		pos_rows_html = "<tr><td colspan='9' style='text-align:center;color:#adb5bd;'>No POS activity in this period</td></tr>"

	def cbu_table(account_type, title, note):
		rows = [r for r in cash_bank_used if r.account_type == account_type]
		totals = {"opening": 0.0, "invoice_amount": 0.0, "payment_amount": 0.0,
			"jv_debit": 0.0, "jv_credit": 0.0, "other_amount": 0.0, "closing": 0.0}
		body = ""
		for r in rows:
			for k in totals:
				totals[k] += flt(r.get(k))
			body += f"""<tr>
				<td>{r.account}</td>
				<td style='text-align:right;'>{money(r.opening, currency)}</td>
				<td style='text-align:right;'>{money(r.invoice_amount, currency)}</td>
				<td style='text-align:right;'>{money(r.payment_amount, currency)}</td>
				<td style='text-align:right;'>{money(r.jv_debit, currency)}</td>
				<td style='text-align:right;'>{money(r.jv_credit, currency)}</td>
				<td style='text-align:right;'>{money(r.other_amount, currency)}</td>
				<td style='text-align:right;font-weight:700;'>{money(r.closing, currency)}</td>
				<td style='text-align:right;'>{r.txn_count}</td>
			</tr>"""
		if not body:
			body = "<tr><td colspan='9' style='text-align:center;color:#adb5bd;'>No activity in this period</td></tr>"
		else:
			body += f"""<tr style="background:#f8f9fa;font-weight:700;border-top:2px solid #343a40;">
				<td>Total</td>
				<td style='text-align:right;'>{money(totals['opening'], currency)}</td>
				<td style='text-align:right;'>{money(totals['invoice_amount'], currency)}</td>
				<td style='text-align:right;'>{money(totals['payment_amount'], currency)}</td>
				<td style='text-align:right;'>{money(totals['jv_debit'], currency)}</td>
				<td style='text-align:right;'>{money(totals['jv_credit'], currency)}</td>
				<td style='text-align:right;'>{money(totals['other_amount'], currency)}</td>
				<td style='text-align:right;'>{money(totals['closing'], currency)}</td>
				<td></td>
			</tr>"""
		return f"""<h4 class="section-title">🏦 {title}</h4>
			<div class="basis-note">{note}</div>
			<div style="overflow-x:auto;">
				<table class="bfr-table">
					<thead><tr><th>Account</th><th>Opening</th><th>Invoice Amount</th><th>Payment Amount</th><th>JV Debit</th><th>JV Credit</th><th>Other</th><th>Closing</th><th>Txns</th></tr></thead>
					<tbody>{body}</tbody>
				</table>
			</div>"""

	cbu_note = "Opening = GL balance before From Date • Invoice = Sales/POS movement • Payments = Payment Entry movement • JV Dr/Cr = Journal legs in period • Other = remaining voucher types • Closing = GL balance at To Date (matches General Ledger / Trial Balance)."
	cbu_3_html = cbu_table("Cash", "3. Cash Accounts - GL Reconciled", cbu_note)
	cbu_4_html = cbu_table("Bank", "4. Bank Accounts - GL Reconciled", cbu_note)

	so_rows_html = ""
	so_totals = {"opening": 0.0, "debit": 0.0, "credit": 0.0, "balance": 0.0}
	for r in supplier_other:
		for k in so_totals:
			so_totals[k] += flt(r.get(k))
		so_rows_html += f"""<tr>
			<td>{r['name']}</td><td>{r['type']}</td>
			<td style='text-align:right;'>{money(r['opening'], currency)}</td>
			<td style='text-align:right;'>{money(r['debit'], currency)}</td>
			<td style='text-align:right;'>{money(r['credit'], currency)}</td>
			<td style='text-align:right;font-weight:700;'>{money(r['balance'], currency)}</td>
		</tr>"""
	if not so_rows_html:
		so_rows_html = "<tr><td colspan='6' style='text-align:center;color:#adb5bd;'>No supplier/other-account activity</td></tr>"
	else:
		so_rows_html += f"""<tr style="background:#f8f9fa;font-weight:700;border-top:2px solid #343a40;">
			<td>Total</td><td></td>
			<td style='text-align:right;'>{money(so_totals['opening'], currency)}</td>
			<td style='text-align:right;'>{money(so_totals['debit'], currency)}</td>
			<td style='text-align:right;'>{money(so_totals['credit'], currency)}</td>
			<td style='text-align:right;'>{money(so_totals['balance'], currency)}</td>
		</tr>"""

	cust_rows_html = ""
	cust_totals = {"opening": 0.0, "invoice": 0.0, "payment": 0.0, "balance": 0.0}
	for r in customers:
		for k in cust_totals:
			cust_totals[k] += flt(r.get(k))
		cust_rows_html += f"""<tr>
			<td>{r['customer']}</td>
			<td style='text-align:right;'>{money(r['opening'], currency)}</td>
			<td style='text-align:right;'>{money(r['invoice'], currency)}</td>
			<td style='text-align:right;'>{money(r['payment'], currency)}</td>
			<td style='text-align:right;font-weight:700;'>{money(r['balance'], currency)}</td>
		</tr>"""
	if not cust_rows_html:
		cust_rows_html = "<tr><td colspan='5' style='text-align:center;color:#adb5bd;'>No customer activity</td></tr>"
	else:
		cust_rows_html += f"""<tr style="background:#f8f9fa;font-weight:700;border-top:2px solid #343a40;">
			<td>Total</td>
			<td style='text-align:right;'>{money(cust_totals['opening'], currency)}</td>
			<td style='text-align:right;'>{money(cust_totals['invoice'], currency)}</td>
			<td style='text-align:right;'>{money(cust_totals['payment'], currency)}</td>
			<td style='text-align:right;'>{money(cust_totals['balance'], currency)}</td>
		</tr>"""

	return f"""
	<style>
		.bfr-wrap * {{ box-sizing: border-box; }}
		.bfr-wrap {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 8px; }}
		.kpi-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
		.kpi-card {{ flex: 1 1 160px; border-radius: 10px; padding: 16px 14px; background: #fff;
			box-shadow: 0 1px 6px rgba(0,0,0,.08); border-left: 4px solid #ccc; min-width: 150px; }}
		.kpi-card h5 {{ margin: 0 0 6px; font-size: 11px; color: #6c757d; text-transform: uppercase; letter-spacing: .5px; }}
		.kpi-card h2 {{ margin: 0; font-size: 22px; font-weight: 700; }}
		.bfr-table {{ width: 100%; border-collapse: collapse; font-size: 12px; background:#fff;
			border-radius:10px; overflow:hidden; box-shadow:0 1px 6px rgba(0,0,0,.08); }}
		.bfr-table th {{ background: #343a40; color: #fff; padding: 9px 10px; font-size: 11px; text-align:left; white-space:nowrap; }}
		.bfr-table td {{ padding: 7px 10px; border-bottom: 1px solid #f1f3f5; vertical-align:middle; }}
		.bfr-table tr:last-child td {{ border-bottom: none; }}
		.bfr-table tr:hover {{ background: #f8f9fa; }}
		.report-header {{ background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 10px;
			padding: 12px 16px; margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 24px; }}
		.report-header h2 {{ margin: 0 0 4px; font-size: 18px; font-weight: 800; color: #212529; }}
		.report-header .meta {{ font-size: 12px; color: #495057; line-height: 1.7; }}
		.basis-note {{ font-size: 11px; color: #6c757d; background: #fffbe6; border: 1px solid #ffe58f;
			border-radius: 8px; padding: 8px 12px; margin: 10px 0 14px; line-height: 1.6; }}
		.balance-badge {{ display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 13px;
			font-weight: 700; margin-bottom: 14px; }}
		.balance-ok {{ background: #e6f4ea; color: #1e7e34; }}
		.balance-bad {{ background: #fdecea; color: #c0392b; }}
		h4.section-title {{ font-size: 14px; font-weight: 700; color: #343a40; margin: 26px 0 10px;
			padding-bottom: 6px; border-bottom: 2px solid #e9ecef; }}
	</style>

	<div class="bfr-wrap">
		<h4 class="section-title">📊 1. Executive Summary</h4>
		<div class="kpi-row">{kpi_html}</div>

		<h4 class="section-title">🏪 2. POS Profile Summary - Sales &amp; Payment History</h4>
		<div class="basis-note">Basis: POS Opening Entry floats + Sales Invoice / Sales Invoice Payment vouchers (POS Profile wise). "Financial Opening" = net GL movement of POS vouchers before From Date.</div>
		<div style="overflow-x:auto;">
			<table class="bfr-table">
				<thead><tr>
					<th>POS Profile</th><th>POS Opening</th><th>Financial Opening</th>
					<th>Gross Sales</th><th>Returns</th><th>Net Sales</th>
					<th>Payments</th><th>Difference</th><th>Closing Financial</th>
				</tr></thead>
				<tbody>{pos_rows_html}</tbody>
			</table>
		</div>

		{cbu_3_html}{cbu_4_html}

<h4 class="section-title">🏭 5. Supplier &amp; Other Accounts</h4>
		<div style="overflow-x:auto;">
			<table class="bfr-table">
				<thead><tr><th>Name</th><th>Type</th><th>Opening</th><th>Debit</th><th>Credit</th><th>Balance</th></tr></thead>
				<tbody>{so_rows_html}</tbody>
			</table>
		</div>

		<h4 class="section-title">👤 6. Customer Balance</h4>
		<div style="overflow-x:auto;">
			<table class="bfr-table">
				<thead><tr><th>Customer</th><th>Opening</th><th>Invoice</th><th>Payment</th><th>Balance</th></tr></thead>
				<tbody>{cust_rows_html}</tbody>
			</table>
		</div>

		<div class="basis-note" style="margin-top:20px;">Figures reconcile with ERPNext General Ledger / Trial Balance for the same company &amp; period. Verify against GL Report &gt; General Ledger for any account.</div>
	</div>
	"""


# =======================================================================
# Excel / PDF export - same layout as the on-screen report
# =======================================================================

def _export_dataset(filters):
	"""Return every section's data exactly like the screen report uses."""
	filters = filters or {}
	exec_summary = get_executive_summary(filters)
	pos_rows = get_pos_summary(filters)
	cbu_rows = get_cash_bank_accounts_used(filters)
	supplier_rows = get_supplier_and_other_accounts(filters)
	customer_rows = get_customer_summary(filters)
	currency = get_company_currency(filters.get("company"))
	return exec_summary, pos_rows, cbu_rows, supplier_rows, customer_rows, currency


@frappe.whitelist()
def export_excel(filters=None):
	"""Download the report as a styled Excel workbook (one sheet, sections
	in the same order & wording as the report view)."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = frappe._dict(filters or {})

	exec_summary, pos_rows, cbu_rows, supplier_rows, customer_rows, currency = _export_dataset(filters)

	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
	from openpyxl.utils import get_column_letter
	import io

	wb = Workbook()
	ws = wb.active
	ws.title = "Business Financial Report"

	thin = Side(style="thin", color="D0D5DD")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	hdr_fill = PatternFill("solid", fgColor="343A40")
	hdr_font = Font(color="FFFFFF", bold=True, size=10)
	sec_font = Font(bold=True, size=12, color="1F2937")
	title_font = Font(bold=True, size=15, color="1F2937")
	meta_font = Font(size=10, color="495057")
	money_fmt = "#,##0.00"

	def title_row(text):
		ws.append([text])
		ws.cell(ws.max_row, 1).font = title_font
		ws.append([])

	def meta_row(text):
		ws.append([text])
		ws.cell(ws.max_row, 1).font = meta_font

	def section(title, headers, rows, money_cols=None):
		money_cols = money_cols or []
		ws.append([])
		ws.append([title])
		ws.cell(ws.max_row, 1).font = sec_font
		ws.append(headers)
		hrow = ws.max_row
		for c in range(1, len(headers) + 1):
			cell = ws.cell(hrow, c)
			cell.fill = hdr_fill
			cell.font = hdr_font
			cell.border = border
		for r in rows:
			ws.append(r)
			for c in range(1, len(headers) + 1):
				cell = ws.cell(ws.max_row, c)
				cell.border = border
				if c in money_cols and isinstance(r[c - 1], (int, float)):
					cell.number_format = money_fmt
		for c in range(1, len(headers) + 1):
			ws.column_dimensions[get_column_letter(c)].width = 26

	meta = "Company: {}   Period: {} to {}   Currency: {}".format(
		filters.get("company") or "-", filters.get("from_date"), filters.get("to_date"), currency or "-")
	title_row("Business Financial Report")
	meta_row(meta)
	ws.append([])

	# 1 Executive Summary
	kpi_rows = [
		["Total Sales", exec_summary["total_sales"]], ["POS Sales", exec_summary["pos_sales"]],
		["Normal Sales", exec_summary["normal_sales"]], ["Credit Notes / Returns", exec_summary["credit_notes"]],
		["Net Sales", exec_summary["net_sales"]], ["Total Collections", exec_summary["total_collections"]],
		["Total Purchases", exec_summary["total_purchases"]], ["Customer Receivable", exec_summary["customer_receivable"]],
		["Supplier Payable", exec_summary["supplier_payable"]], ["Cash Balance", exec_summary["cash_balance"]],
		["Bank Balance", exec_summary["bank_balance"]], ["Cash + Bank Balance", exec_summary["cash_plus_bank"]],
	]
	section("1. Executive Summary", ["Metric", "Amount"], kpi_rows, money_cols=[2])

	# 2 POS Profile Summary
	pos_headers = ["POS Profile", "POS Opening", "Financial Opening", "Gross Sales", "Returns", "Net Sales", "Payments", "Difference", "Closing Financial"]
	pos_data = []
	for r in pos_rows:
		pos_data.append([r["pos_profile"], r["pos_opening"], r["financial_opening"], r["gross_sales"],
			r["returns"], r["net_sales"], r["payments"], r["difference"], r["closing_financial"]])
	section("2. POS Profile Summary - Sales & Payment History", pos_headers, pos_data, money_cols=[2, 3, 4, 5, 6, 7, 8, 9])

	# 3 + 4 Cash & Bank split (GL Reconciled)
	cbu_headers = ["Account", "Opening", "Invoice Amount", "Payment Amount", "JV Debit", "JV Credit", "Other", "Closing", "Txns"]
	for cb_type, cb_title in (("Cash", "3. Cash Accounts - GL Reconciled"), ("Bank", "4. Bank Accounts - GL Reconciled")):
		cbu_data = []
		for r in cbu_rows:
			if r["account_type"] != cb_type:
				continue
			cbu_data.append([r["account"], r["opening"], r["invoice_amount"], r["payment_amount"],
				r["jv_debit"], r["jv_credit"], r["other_amount"], r["closing"], r["txn_count"]])
		section(cb_title, cbu_headers, cbu_data, money_cols=[2, 3, 4, 5, 6, 7, 8])

	# 5 Supplier & Other Accounts
	so_headers = ["Name", "Type", "Opening", "Debit", "Credit", "Balance"]
	so_data = [[r["name"], r["type"], r["opening"], r["debit"], r["credit"], r["balance"]] for r in supplier_rows]
	if so_data:
		so_t = [sum(flt(x[i]) for x in so_data) for i in (2, 3, 4, 5)]
		so_data.append(["Total", "", so_t[0], so_t[1], so_t[2], so_t[3]])
	section("5. Supplier & Other Accounts", so_headers, so_data, money_cols=[3, 4, 5, 6])

	# 6 Customer Balance
	cust_headers = ["Customer", "Opening", "Invoice", "Payment", "Balance"]
	cust_data = [[r["customer"], r["opening"], r["invoice"], r["payment"], r["balance"]] for r in customer_rows]
	if cust_data:
		c_t = [sum(flt(x[i]) for x in cust_data) for i in (1, 2, 3, 4)]
		cust_data.append(["Total", c_t[0], c_t[1], c_t[2], c_t[3]])
	section("6. Customer Balance", cust_headers, cust_data, money_cols=[2, 3, 4, 5])

	ws.append([])
	ws.append(["Note: Amounts reconcile with ERPNext General Ledger / Trial Balance for the same company & period."])

	buf = io.BytesIO()
	wb.save(buf)
	buf.seek(0)

	frappe.local.response.filename = "Business-Financial-Report.xlsx"
	frappe.local.response.filecontent = buf.getvalue()
	frappe.local.response.type = "download"


@frappe.whitelist()
def download_report_pdf(filters=None):
	"""Download the report exactly as it looks on screen (A4 landscape PDF)."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = frappe._dict(filters or {})

	from frappe.utils.pdf import get_pdf
	from frappe.utils import cint

	columns, data, html = execute(filters)

	pdf = get_pdf(html, {
		"orientation": "Landscape",
		"margin-top": "8mm",
		"margin-bottom": "12mm",
		"margin-left": "6mm",
		"margin-right": "6mm",
	})

	frappe.local.response.filename = "Business-Financial-Report.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"
