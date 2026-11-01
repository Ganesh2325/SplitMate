# SplitMate

SplitMate keeps a clear record of money that people share. It answers four questions:

- Who paid?
- Who was supposed to share the cost?
- Who still owes money?
- What changed if someone edits, cancels, or reverses a record?

It is for trips, roommates, students, families, and small teams. SplitMate does not send money. It only remembers what you enter, then shows the balance.

## How a shared bill works

1. **Record who paid.** One person can pay, or several people can pay parts of the same bill.
2. **Choose the split.** Divide the total equally, by exact amounts, by percentages, by shares, or item by item. SplitMate checks that the shares add up to the total.
3. **Settle when you are ready.** SplitMate can suggest who should pay whom. Nothing is recorded as paid until you confirm it yourself.

A **positive** balance means that person should receive money. A **negative** balance means that person owes money. **Zero** means that part is settled.

## A short example

Four friends go on a weekend trip. The bills are:

| What | Amount | Who paid |
| --- | ---: | --- |
| Hotel | 4,000 | Ganesh |
| Food | 2,000 | Rahul |
| Transport | 1,000 | Priya |
| Tickets | 1,000 | Arjun |

The total is 8,000. Split equally, each person owes 2,000.

- Ganesh paid 4,000 and owes 2,000, so Ganesh should receive **2,000**.
- Rahul paid 2,000 and owes 2,000, so Rahul is **settled**.
- Priya paid 1,000 and owes 2,000, so Priya owes **1,000**.
- Arjun paid 1,000 and owes 2,000, so Arjun owes **1,000**.

The four results add up to zero. That is how you know the record is complete.

## What you can do

- Create an account, then sign in with the same username and password.
- Reset a forgotten password from the login page. The reset message is sent to the email on the account.
- Add friends and create groups. A group can have an owner, an admin, a member, or a read-only person.
- Add expenses, comments, and receipt photos.
- See balances for a group, for a friend, and for an informal loan separately. The same bill is not counted twice.
- Record a repayment by cash, UPI, bank transfer, or Paytm. You can reverse it if it was a mistake. The original row stays in the history.
- Keep categories, budgets, recurring bills, and expense templates.
- Open reports and download them as CSV, Excel, or PDF.

## What SplitMate does not do

- It does not move or check money. A repayment is your note that the money changed hands.
- It does not read receipts into an expense. Receipt scanning is turned off.
- It does not create recurring bills by itself. Someone has to run the recurring command, or a scheduler has to run it.
- One group uses one currency. Rupees and dollars are never added together.

## Use it in the browser

1. Open the home page.
2. Choose **Create account**. Enter your name, username, email, and a password of at least 6 characters. Agree to the terms and privacy policy.
3. After the account is saved, you land on the login page. You are not signed in yet.
4. Sign in with the same username and password. Your dashboard opens.
5. From the dashboard you can add an expense, create a group, add a friend, or settle up.

If you forget the password, choose **Forgot password**, enter the account email, and open the link in the message.

## Run it on your computer

You need Python 3.14. In PowerShell, from this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Then open http://127.0.0.1:8000/. If that address is already used by another program, start it on another port:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Until you connect a real mailbox, password and verification emails are printed in the server window. The rest of the app still works.

To load the weekend-trip example while debug is on:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo
```

Sign in as `ganesh` with password `ValidPass123`. The same password is used for `rahul`, `priya`, and `arjun` when that command creates them. The command will not replace expenses that are already in the Weekend Trip group, and it will not run when debug is off.

## For someone setting up the code

SplitMate is a Django application. Pages are Django templates. Styling uses Bootstrap 5. Charts use Chart.js. Money is stored as decimal numbers, and the server calculates every share and balance.

Local development uses SQLite. Set `DB_ENGINE=postgres` in `.env` to use PostgreSQL. Copy `.env.example` to `.env` and keep `.env` private. It is not part of the git repository.

Useful checks:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

Other commands:

```powershell
.\.venv\Scripts\python.exe manage.py process_recurring_expenses
.\.venv\Scripts\python.exe manage.py send_repayment_reminders
.\.venv\Scripts\python.exe manage.py purge_login_attempts
.\.venv\Scripts\python.exe manage.py reconcile_balances
```

`process_recurring_expenses` is safe to run more than once on the same day. It will not create the same bill twice.

For a public server, set `DJANGO_DEBUG=false`, a long `DJANGO_SECRET_KEY`, and your real host name in `DJANGO_ALLOWED_HOSTS`. Use HTTPS before turning on `ENABLE_HSTS`. Staff can open `/admin/`. Change expenses and repayments on the site, not by typing amounts directly in the admin.

`GET /health/` checks that the database can answer a simple query.

Docker files are included as a starting point. They were not run in this project, so try them in your own environment before you rely on them.
