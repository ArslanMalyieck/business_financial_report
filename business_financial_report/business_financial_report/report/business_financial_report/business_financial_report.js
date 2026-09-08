// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Business Financial Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start()
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company")
		},
		{
			fieldname: "pos_profile",
			label: __("POS Profile"),
			fieldtype: "Link",
			options: "POS Profile"
		},
		{
			fieldname: "mode_of_payment",
			label: __("Mode of Payment"),
			fieldtype: "Link",
			options: "Mode of Payment"
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer"
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier"
		},
		{
			fieldname: "include_credit_notes",
			label: __("Include Credit Notes"),
			fieldtype: "Check",
			default: 1
		}
],

	onload: function (report) {
		if (!report || !report.page || report.page.__bfr_export_added) return;
		report.page.__bfr_export_added = true;

		var module_path =
			"business_financial_report.business_financial_report.report.business_financial_report.business_financial_report.";

		function current_filters() {
			return report.get_filter_values ? report.get_filter_values() : {};
		}

		function download(method) {
			var url =
				frappe.urllib.get_full_url("/api/method/" + module_path + method) +
				"?filters=" +
				encodeURIComponent(JSON.stringify(current_filters()));
			window.open(url);
		}

		report.page.add_inner_button(__("Excel"), function () {
			download("export_excel");
		});

		report.page.add_inner_button(__("PDF"), function () {
			download("download_report_pdf");
		});
	}
};
