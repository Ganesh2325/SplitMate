# SplitMate

SplitMate is a shared-expense application for friends, roommates, families, and trip groups. People record who paid, how a bill was divided, and which repayments have been made. Balances are calculated from those records.

It is for anyone who needs a clear answer to: who paid, who shared the cost, who owes whom, and what changed after an edit, a void, or a reversed repayment.

## Capabilities

- Accounts with registration, login, logout, email verification, password reset, profile, preferences, deactivation, and anonymized deletion.
- Friends, blocks, and email invitations.
- Groups with owner, admin, member, and read-only roles.
- Expenses with multiple payers and five split methods: equal, exact, percentage, shares, and itemized.
- Group, friend, and informal-loan balances that are not mixed together.
- Recorded repayments, reversals, and a deterministic debt-simplification suggestion.
- Categories, tags, search, filters, reports, CSV, Excel, and PDF export.
- Comments, receipt uploads, recurring expenses, budgets, templates, and an audit log.

## Stack

- Python 3.14 and Django 6.1
- Django templates, Bootstrap 5, vanilla JavaScript, Chart.js
- SQLite for local development, PostgreSQL when `DB_ENGINE=postgres`
- Decimal money only. The server calculates shares and balances.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Open http://127.0.0.1:8000/.

With `DJANGO_DEBUG=true` you can load the Weekend Trip example:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo
```

Log in as `ganesh` / `ValidPass123`. The same password is set for `rahul`, `priya`, and `arjun` when those accounts are created by the command. The command refuses to run when debug is off, and it does not replace expenses that are already in that group.

Email uses the console backend in development. Verification and reset messages are printed in the server terminal. The site stays usable when mail cannot be delivered.

## Accounting

Positive balance means that person should receive money. Negative means they owe money.

```text
net = expense payments − expense shares + repayments made − repayments received
```

A repayment increases the payer's net and decreases the recipient's net. That matches a payment toward a debt: the person who owed money moves toward zero, and the person who was owed money is owed less.

Group expenses stay on the group balance. Expenses with no group use a pairwise split between the people on that bill. Informal loans are a separate line and are reduced only by loan payments, not by expense settlements.

Each group uses one currency. The currency cannot change after the group has expenses or settlements. Amounts in different currencies are never added together. `ExchangeRate` rows can be stored, and they are not applied to historical group books.

Debt simplification is a deterministic greedy match of the largest remaining creditor and debtor. It preserves every net. It does not claim to find the smallest possible number of payments in every case. A suggestion does not record a payment until someone submits the settlement form.

The expense list filter “my result” compares what you paid on that bill with your share. A later repayment does not change that filter. Outstanding balances are on the balance pages.

Voids and settlement reversals keep the original rows and remove them from the active balance.

## Data

Main records: user, friendship, group, membership, invitation, expense, payer, share, item, comment, attachment, settlement, settlement reversal, informal debt, category, notification, audit log, recurring expense, occurrence, budget, template, and export job.

Financial foreign keys use `PROTECT`. Deleting an account anonymizes the user (`deleted-<id>`), sets an unusable password, and refuses while that user is the sole owner of a group that still has other members. Sole-owner groups with no other members are archived.

Migrations:

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py migrate
```

Backup a SQLite file by copying `db.sqlite3` while the server is stopped. For PostgreSQL, use `pg_dump` and `pg_restore`. Media files under `media/` must be backed up with the database because receipts are not stored in the database itself.

## Commands

```powershell
.\.venv\Scripts\python.exe manage.py process_recurring_expenses
.\.venv\Scripts\python.exe manage.py send_repayment_reminders
.\.venv\Scripts\python.exe manage.py purge_login_attempts
.\.venv\Scripts\python.exe manage.py reconcile_balances
```

`process_recurring_expenses` is safe to run more than once. Each scheduled date has one occurrence row, and the generated expense uses a stable token. There is no Celery worker. Schedule the command with the operating system or a host scheduler if you want it to run unattended. Nothing in the request path waits on that command.

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

The suite covers split rounding, the Weekend Trip balances, edits, voids, settlement reversal, duplicate settlement tokens, separate currencies, registration, page rendering, friend expenses, receipt access, viewer restrictions, recurring duplicate prevention, budget shares, and CSV formula quoting.

SQLite tests do not prove PostgreSQL row-locking behavior. Settlement recording uses `select_for_update` inside a transaction; confirm concurrent behavior on PostgreSQL before relying on it in production.

## Production

Set `DJANGO_DEBUG=false`, a long `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DB_ENGINE=postgres`. Put the app behind HTTPS and set `ENABLE_HSTS=true` only after HTTPS works. Set `CSRF_TRUSTED_ORIGINS` to the public origin.

```powershell
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

WhiteNoise serves collected files. Gunicorn can serve the app with `gunicorn config.wsgi:application`. Receipts are downloaded through an authenticated view, not a public media URL. Configure SMTP with the email variables in `.env.example` if you want messages to leave the machine. `REDIS_URL` is optional; without it the cache is in-process memory.

`Dockerfile` and `docker-compose.yml` are included for a local PostgreSQL layout. They were not executed in this workspace, so treat them as a starting point and run them in your own environment before relying on them.

Health check: `GET /health/` runs `SELECT 1`.

Logging uses the `splitmate` logger configured in settings. Do not put passwords or reset tokens in audit rows. The application does not store them there.

## Admin

`/admin/` is limited to staff users. Expense amounts, settlements, revisions, and audit rows are read-only there so a direct edit does not bypass the accounting services. Create and change financial records through the site.

## Limitations

- Recording cash, UPI, bank transfer, or Paytm stores a label. SplitMate does not move or verify money.
- Receipt OCR is off unless `ENABLE_OCR=true` and `pytesseract` is installed. A scan never saves an expense. `pytesseract` is not installed in this environment, and OCR was not verified.
- There is no Celery or Redis requirement. Recurring expenses and reminders run only when the management commands run.
- The interface is English.
- Bootstrap, Bootstrap Icons, and Chart.js are loaded from a CDN.
- Docker Compose was not run here.
- Cross-currency settlement inside one group is not implemented. Keep each group in one currency.

## Requirement status

Implemented and covered by automated tests: authentication, friends, groups and roles, all five split methods, balances, settlements and reversals, debt simplification, the Weekend Trip scenario, edits and voids, recurring duplicate prevention, budgets, receipt access control, CSV formula protection, and the main pages rendering.

Implemented with service and page support, with less direct test coverage: comments, notifications, activity, templates, saved preferences, informal debts, reports and charts, Excel and PDF export, categories, and audit logging.

Not claimed as working here: live payments, OCR, unattended scheduling, and the Docker stack.
