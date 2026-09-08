# Business Financial Report (business_financial_report)

Multi-section **Business Financial Report** for Frappe / ERPNext **v15** (also works on v16) - built for the **ACM** chart of accounts with **fixed supplier / customer / account lists**.

## Report sections (single custom-HTML script report)

1. **Executive Summary** - KPI cards: Total/POS/Normal Sales, Credit Notes, Net Sales, Collections, Purchases, Customer Receivable, Supplier Payable, Cash, Bank, Cash + Bank
2. **POS Profile Summary** - POS Opening (float), Financial Opening, Gross Sales, Returns, Net Sales, Payments, Difference (✓/⚠ badge), Closing Financial
3. **Cash & Bank Accounts Used - GL Reconciled** - per Cash/Bank account: Opening, Invoice Amount (Sales/POS), Payment Amount (Payment Entry), JV Debit / JV Credit (Journal Entries), Other (remaining voucher types), Closing, Txns + Total row. **Closing = GL balance at To Date - matches ERPNext General Ledger / Trial Balance.**
4. **Supplier & Other Accounts** - fixed suppliers + fixed named accounts with Opening / Debit / Credit / Balance
5. **Customer Balance** - fixed customer list with Opening / Invoice / Payment / Balance

Plus: **Excel** and **PDF** toolbar buttons - exports generated exactly like the on-screen report layout.

## Fixed lists (edit in `business_financial_report.py`)

```python
DEFAULT_SUPPLIERS     = ["NINGBO ZT BULL HYDRAULIC CO., LTD.", ...]
DEFAULT_CUSTOMERS     = ["GULF SOLIDARITY CONTRACTING COMPANY", ..., "Alpha Square Contracting Company"]
DEFAULT_OTHER_ACCOUNTS= ["Salary Pakistan Account - ACM", "MUSCAT ALSAFWA INT. LLC - ACM", "AL-FORSAN CONTRACTING - ACM"]
```

## Filters

From / To Date, Company, POS Profile, Mode of Payment, Customer, Supplier, Include Credit Notes. Section 4 & 5 lists are **fixed** (not filter driven). Section 3's Opening = GL balance before From Date.

## Installation

```bash
cd ~/frappe-bench
git clone https://github.com/ArslanMalyieck/business_financial_report.git apps/business_financial_report
grep -q "^business_financial_report$" sites/apps.txt || echo "business_financial_report" >> sites/apps.txt
bench pip install -e apps/business_financial_report
bench --site your-site.local install-app business_financial_report
bench --site your-site.local migrate
bench restart
```

Then open: **Report > Business Financial Report** (Accounts Manager / System Manager / Accounts User roles) - or
`/app/query-report/Business Financial Report`.

## Prepared Report

The Report is created with **"Disable Prepared Report Automation" = ON**, so it always runs live/quick instead of offering a Prepared Report.

## Accuracy

All amount figures are pulled from `GL Entry` (or Sales Invoice / POS Opening Entry vouchers where noted) and reconcile with **ERPNext General Ledger / Trial Balance** for the same company and period. Section 3's Closing is verified per-account against the GL balance at To Date.

## Files

```
business_financial_report/
└── business_financial_report/
    └── business_financial_report/
        └── report/business_financial_report/
            ├── business_financial_report.py      # logic + Excel/PDF export endpoints
            ├── business_financial_report.js      # filters + Excel/PDF toolbar buttons
            └── business_financial_report.json    # Report doc (script report, roles)
```

## License

MIT
