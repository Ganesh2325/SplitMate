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

The signed-in menu has three groups. Every item stays available.

- **Everyday:** Dashboard, All expenses, Friends, Groups, Balances, Settle up.
- **Money tools:** Recurring, Categories, Budgets, Reports, Informal debts, Templates.
- **Account:** Notifications, Profile, Settings.

You can also:

- Create an account, then sign in with the same username and password. Creating an account does not sign you in.
- Receive one welcome email the first time you sign in successfully.
- Confirm your email only when you choose **Resend email**. SplitMate does not send that message on its own.
- Reset a forgotten password from the login page. The reset message is sent to the email on the account.
- Add friends and create groups. A group can have an owner, an admin, a member, or a read-only person.
- Add expenses, comments, and receipt photos. The person who created an expense can edit it. A group owner or admin can edit group expenses too.
- See balances for a group, for a friend, and for an informal loan separately. The same bill is not counted twice.
- Record a repayment by cash, UPI, bank transfer, or Paytm. You can reverse it if it was a mistake. The original row stays in the history.
- Keep categories, budgets, recurring bills, and expense templates.
- Open reports and download them as CSV, Excel, or PDF.

## What SplitMate does not do

- It does not move or check money. A repayment is your note that the money changed hands.
- It does not read receipts into an expense. Receipt scanning is turned off.
- It does not create recurring bills by itself. Someone has to run the recurring command, or a scheduler has to run it.
- One group uses one currency. Rupees and dollars are never added together.

## Architecture

SplitMate is one Django project. The outer folder is the project you open. Inside it, `config` is the project package that starts the site, and `apps` holds the feature apps. This is the same Django layout as an inner project folder plus apps. The inner folder is named `config` so it is obvious that it holds settings, URLs, and the server entry points.

```text
SplitMate/
  manage.py              starts the site and the management commands
  config/                project package: settings, URLs, server entry
  apps/                  one folder for each feature
  templates/             HTML pages
  static/                CSS, JavaScript, and images
  requirements.txt       Python packages
  .env.example           names of settings, with no secrets
  .env                   your private settings (not in git)
  db.sqlite3             the local database file (not in git)
  media/                 uploaded pictures and receipts (not in git)
```

A page request moves in one direction:

```text
Browser
  -> config/urls.py          chooses the app
  -> apps/<feature>/views.py reads the form and checks who is signed in
  -> apps/<feature>/services.py and apps/common/  calculate shares and balances
  -> db.sqlite3              stores the rows
  -> templates/ and static/  draw the page
  -> Browser
```

Money math lives on the server. The browser does not decide a share, a balance, or a suggested repayment. A positive number means that person should receive money. A negative number means that person owes money.

### The project package

| Folder or file | What it is for |
| --- | --- |
| `manage.py` | The command you run. It points Django at `config.settings`. |
| `config/settings.py` | Apps, database, email, passwords, and file locations. |
| `config/urls.py` | The front door. It sends each address to the right app. |
| `config/wsgi.py` and `config/asgi.py` | How a production server loads the project. |
| `config/middleware.py` | Adds a request id and uses each person's timezone. |

### The apps

Each app owns its models, pages, and rules. Shared helpers live in `apps/common` so the other apps do not copy the same money code.

| App | What it keeps |
| --- | --- |
| `accounts` | People, passwords, profile, welcome mail, and email confirmation. |
| `friends` | Friend requests, blocks, and email invitations. |
| `groups` | Groups, members, roles, and invitations. |
| `expenses` | Bills, who paid, who shares, comments, receipts, and templates. |
| `settlements` | Balances, recorded repayments, and informal loans. |
| `categories` | Built-in and personal expense categories. |
| `budgets` | Spending limits for a person or a group. |
| `recurring` | Schedules that can create a real expense later. |
| `reports` | Dashboard, charts, and CSV, Excel, and PDF downloads. |
| `notifications` | In-app messages and optional email notices. |
| `audit` | A history of important changes. |
| `common` | Currencies, split math, and the money format used by every page. |

### Where the data is stored

Local development uses one SQLite file, `db.sqlite3`, in the project folder. That file is the database. Accounts, groups, expenses, shares, repayments, loans, budgets, and notifications are rows inside it. Uploaded profile pictures, group images, and receipts go in `media/`.

Both `db.sqlite3` and `media/` stay on your computer. They are listed in `.gitignore`, so a git push does not publish them. To look at the rows, open `db.sqlite3` in [DB Browser for SQLite](https://sqlitebrowser.org/), or from the project folder run:

```powershell
.\.venv\Scripts\python.exe manage.py shell
```

```python
from apps.accounts.models import User
for user in User.objects.order_by("id"):
    print(user.id, user.username, user.email)
```

The useful tables are:

| What you are looking for | Table |
| --- | --- |
| Username, email, password hash, currency | `accounts_user` |
| Friend links | `friends_friendship` |
| Groups and members | `groups_group`, `groups_groupmembership` |
| Expenses, who paid, who shares | `expenses_expense`, `expenses_expensepayer`, `expenses_expenseshare` |
| Recorded repayments | `settlements_settlement` |
| Informal loans | `settlements_informaldebt` |
| Categories, budgets, repeating bills | `categories_expensecategory`, `budgets_budget`, `recurring_recurringexpense` |
| Notifications | `notifications_notification` |

Passwords are stored as hashes. Set `DB_ENGINE=postgres` in `.env` when you want PostgreSQL instead of the SQLite file.

## Use it in the browser

1. Open the home page.
2. Choose **Create account**. Enter your name, username, email, and a password of at least 6 characters. Agree to the terms and privacy policy.
3. After the account is saved, you land on the login page. You are not signed in yet.
4. Sign in with the same username and password. Your dashboard opens. The first successful sign-in sends the welcome email.
5. From the dashboard you can add an expense, create a group, add a friend, or settle up.

If you forget the password, choose **Forgot password**, enter the account email, and open the link in the message.

To try the product with four people at once, use a normal window and a private window for each person. One browser window keeps one login.

| Window | Username | Password |
| --- | --- | --- |
| Normal Chrome | `ganesh` | `ValidPass123` |
| Chrome private window | `rahul` | `ValidPass123` |
| Normal Edge | `priya` | `ValidPass123` |
| Edge private window | `arjun` | `ValidPass123` |

Those four accounts exist only after you run `seed_demo`. Their emails are `ganesh@example.com`, `rahul@example.com`, `priya@example.com`, and `arjun@example.com`.

## Run it on your computer

You need Python 3.14. In PowerShell, from this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Then open http://127.0.0.1:8001/.

Password, welcome, and verification messages are sent through the Gmail account named in `.env`. The message goes to the email address on that person's account, whether it is Gmail, Outlook, or another provider. The mailbox address and app password stay in `.env` and are not part of the git repository.

To load the weekend-trip example while debug is on:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo
```

Sign in as `ganesh` with password `ValidPass123`. The same password is used for `rahul`, `priya`, and `arjun` when that command creates them. The command will not replace expenses that are already in the Weekend Trip group, and it will not run when debug is off.

## Checks and other commands

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py process_recurring_expenses
.\.venv\Scripts\python.exe manage.py send_repayment_reminders
.\.venv\Scripts\python.exe manage.py purge_login_attempts
.\.venv\Scripts\python.exe manage.py reconcile_balances
```

`process_recurring_expenses` is safe to run more than once on the same day. It will not create the same bill twice.

For a public server, set `DJANGO_DEBUG=false`, a long `DJANGO_SECRET_KEY`, and your real host name in `DJANGO_ALLOWED_HOSTS`. Use HTTPS before turning on `ENABLE_HSTS`. Staff can open `/admin/`. Change expenses and repayments on the site, not by typing amounts directly in the admin.

`GET /health/` checks that the database can answer a simple query.

Docker files are included as a starting point. They were not run in this project, so try them in your own environment before you rely on them.
