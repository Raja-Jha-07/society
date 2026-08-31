# Utthan Society Manager

Private web portal and offline Windows software for member savings, internal loans, monthly dues, receipts and record keeping.

![Classic Windows interface with high-DPI rendering](docs/classic-hd-preview.png)

## Ready-to-use application

Open `dist/Utthan-Society-Manager.exe`. No Python installation is required on the computer that runs the EXE.

On first launch, the application creates its database and imports the 60 members and August 2026 opening balances from the attached due-list PDF.

## Private web portal

The web portal uses the same database rules and opening records as the desktop application. Administrators have full management access. Every member account is linked to one member and can view only that member's savings, loans, dues, bills, payments and receipts.

1. Install dependencies with `python -m pip install -r requirements.txt`.
2. Start the private server with `python web_app.py`.
3. Open `http://127.0.0.1:8080` and create the first administrator.
4. Open **User accounts**. Create accounts individually, or use **Create all missing member accounts** to download a one-time credentials CSV.
5. Give each member only their own temporary credentials. Every temporary password must be changed at first login.

Administrators can search members and monthly dues by member number or name, open any member's complete history, and review data changes and login attempts under **Activity & security**. **Cashbook** provides both backup download and validated restore. Restore accepts only a backup created by the web portal that contains an active administrator, creates a safety copy first, and signs out the current session afterward.

The server listens only on the current computer by default. For private-LAN access, set `UTTHAN_HOST=0.0.0.0` before starting it and allow TCP port 8080 only from the trusted network. For internet access, place the server behind an HTTPS reverse proxy, set `UTTHAN_COOKIE_SECURE=true`, use a strong `UTTHAN_SECRET_KEY`, restrict firewall access, and maintain encrypted off-site backups. Do not expose the Waitress port directly to the internet.

The first administrator setup page is available only while no user accounts exist. There are no hard-coded or default passwords.

## Included features

- dashboard with savings, loans, interest, expenses and available funds;
- member register;
- fresh and top-up loans;
- reducing-balance interest and EMI calculation;
- monthly due generation;
- old-due and late-fee tracking;
- full or partial payment entry;
- printable monthly due lists, member bills and payment receipts;
- cashbook and expenses;
- CSV export;
- local backup and restore;
- audit log in the database;
- configurable contribution, EMI and interest defaults.
- administrator and member login accounts with hashed passwords;
- member-level record isolation, CSRF protection, login throttling and security headers;
- one-time bulk account provisioning for all active members.
- administrator member-history search and security/audit activity views;
- validated web database backup download and restore.

## Data location

The EXE stores working data outside its installation folder:

`%LOCALAPPDATA%\UtthanSociety\utthan_society.db`

Generated reports and backups are stored below the same folder. Their exact locations are displayed inside the application.

Create a backup regularly and copy important backups to another physical drive. Data remains only on the local computer unless a user manually copies it elsewhere.

## Recommended monthly process

1. Review the previous month's unpaid balances.
2. Close the previous period after all intended entries are made.
3. Select **Generate Next Month**.
4. Review the automatically calculated contribution, EMI, interest and carried due.
5. Create the due-list PDF or member bills.
6. Record each payment; the application updates savings and loan balances and creates a receipt.
7. Enter expenses and reconcile the cashbook with cash/bank holdings.
8. Create a backup.

## Source rules imported

The attached August 2026 PDF indicates:

- monthly contribution: ₹500 per member;
- EMI: ₹1,000 for borrowers;
- interest: 1.5% per month on opening outstanding loan balance;
- 60 members;
- opening member contributions: ₹15,90,000;
- loans in circulation: ₹10,77,000;
- previous interest: ₹1,48,085.

See [docs/RESEARCH_AND_DESIGN.md](docs/RESEARCH_AND_DESIGN.md) for the complete analysis, verified totals, official references, design and legal/accounting cautions.

## Development

Requirements: Python 3.14 or a compatible current Python 3 version.

- Start from source: `python app.py`
- Start the private web portal: `python web_app.py`
- Run tests: `python -m unittest discover -s tests -v`
- Rebuild EXE: run `scripts/build.ps1`

## Important scope note

This application maintains records; it is not legal, tax or audit advice and does not confer authority to accept public deposits or conduct regulated banking. Confirm the organisation's legal form and accounting policy with a qualified local professional before treating it as the final statutory ledger.
