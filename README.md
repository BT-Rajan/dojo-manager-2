# Dojo Manager

Management system for a multi-branch martial arts academy: members and belt progression,
memberships and payments, the class timetable and attendance, leads and trial classes,
gradings and seminars, front-desk operations, and inventory.

| Layer    | Stack |
|----------|-------|
| API      | Python 3.12, FastAPI, SQLAlchemy 2 (async, `asyncmy`), Pydantic v2, Alembic |
| Database | MySQL 8 or MariaDB 10.11+ (InnoDB, utf8mb4) |
| Web      | React 18, Vite, TypeScript, Tailwind, shadcn/ui (Radix), TanStack Query, wouter |

## Features

- **Branches & roles**: owner, operations manager (all branches), branch admin and instructor
  (only their assigned branches). Branch isolation is enforced on every API query; rows in
  other branches look like missing rows.
- **Members**: registration (guardian, emergency contact, health notes, media consent),
  generated member numbers (`PRM-00001`), search, belt and BJJ stripes; paginated, sortable
  list; standing derived from memberships (active, lapsed, new, frozen, inactive).
- **Memberships & payments**: plans per branch or academy-wide, priced in KD (3 decimals);
  renewals continue from the current end date; inline payment (KNET / card / cash);
  renewal follow-up list and contact log; payments are append-only and voided by managers.
- **Classes**: weekly timetable, idempotent generation of dated sessions; recording leave
  hands already-generated classes to the cover instructor (and back if the leave is removed), cancel/reschedule with a reason, bulk check-in with capacity lock and a
  "membership covers this date" flag, instructor leave.
- **Coach portal**: each coach signs in with their own login (created under Admin → Coach
  portal) and lands on their portal: today's classes with attendance, the branch's whole day
  (every class, who teaches it, who is on leave), and their week (Saturday to Friday) with the
  weekly timetable. Classes they cover and classes covered for them are marked. Staff can open
  any coach's portal at their branches.
- **Member and parent portal** (`/portal`, English and Arabic): families sign in with their
  mobile number and a 4-digit WhatsApp code (no passwords) and see each child's belt and
  stripes, next class and membership (with "renew soon" warnings). Parents are linked to
  members on the member page (Family and portal); siblings registered with the same parent
  mobile share one family. Adult members sign in with their own mobile. Codes are stored
  hashed, expire after 5 minutes and allow 5 attempts; 3 codes per number per 15 minutes and
  10 per address per hour; the answer is the same for unknown numbers. Until WhatsApp is
  connected, messages are logged and the code is shown on screen outside production.
  Each child's page shows the membership and this week's classes: regular weekly classes,
  bookings (with Cancel) and the classes their membership lets them book, up to 7 days ahead
  at their branch. A full class puts them on the waiting list; when a booked place is freed
  the first in line gets it and is told by WhatsApp. Cancelling less than 2 hours before is
  recorded as late. Recent attendance is listed too.
- **Regular classes**: members can hold a regular weekly place in a timetable class (member
  page → Regular classes). Regulars count towards class capacity and appear on every class
  roster, with bookings, the waiting list and portal bookings marked.
- **Leads**: enquiry → contacted → trial booked → attended → member (or lost, with reason).
- **Gradings & seminars**: Kajukenbo belt system (belt = rank + kickboxing level, stripe =
  grappling level, seminar points required), grading events that promote passing students,
  promotion-readiness view.
- **Operations**: incident reports (any staff, instructors included), complaint log.
- **Inventory**: purchase request → manager approval (one local-vendor purchase per branch
  per month) → receipt with discrepancy detection → inter-branch transfer (ownership moves on
  receipt) → equipment sales → monthly counts with approved variances. Stock never goes
  negative; every change is in a movement ledger.
- **Reports**: dashboard, weekly sales (Saturday–Friday) by method and category, weekly
  branch report vs the previous week, attendance by programme.

## Dates and times

- Shown everywhere as **DD-MM-YYYY** and **HH:mm:ss** (24-hour), in **Kuwait time**, whatever
  the browser's own time zone or locale. Date, time and month fields are typed in the same
  formats (DD-MM-YYYY, HH:MM:SS, MM-YYYY).
- The API exchanges ISO 8601 values. Timestamps are stored in UTC and returned in Kuwait time
  with their offset (`2026-10-20T16:56:00+03:00`); incoming timestamps without an offset are
  read as Kuwait time.
- "Today", expiry lists, revenue and weekly reports use Kuwait calendar days
  (`DOJO_TIMEZONE`, default `Asia/Kuwait`).

## Security

- Opaque session tokens in an `HttpOnly`, `SameSite=Lax` (and `Secure` in production) cookie;
  only a SHA-256 of each token is stored, so sessions can be revoked (logout, password change,
  deactivation).
- Passwords hashed with argon2id, off the event loop; identical responses for unknown users and
  wrong passwords; login throttling per IP and per username.
- CSRF: writes require an `X-Requested-With` header, which cross-site pages cannot send
  without passing CORS.
- Strict request schemas (unknown fields rejected), LIKE wildcards escaped, database errors
  never echoed, security headers, `Cache-Control: no-store` on API responses, audit log for
  sensitive actions. API docs are disabled in production.

## Running

Requirements: Python 3.12+, Node 20+, MySQL 8 or MariaDB 10.11+ (running), its command-line
client (`mariadb` or `mysql`), and optionally [pm2](https://pm2.keymetrics.io/).

```bash
./runonce.sh   # one-time setup; safe to re-run
./start.sh     # Dojo Manager on http://<server>:8090 (pm2 app "dojo")
./stop.sh
```

Dojo Manager runs as **one process on port 8090**: the FastAPI server answers `/api/...` and
also serves the built web app, so pages and API share one origin. Change the port or address
with `DOJO_PORT` / `DOJO_HOST` in `backend/.env` (default `0.0.0.0:8090`, reachable from other
machines; use `127.0.0.1` behind a reverse proxy), then run `./start.sh` again.

### Setup: `runonce.sh`

Connects to the database only as the app user from `backend/.env` (never as `root`). If that
user can already use the database, creation is skipped; if the database is missing and the
user may create it, it is created; otherwise the script prints the SQL for a database
administrator to run and stops. On a first run without `backend/.env` it writes one
(permissions 600) with a generated password, or yours via `DOJO_DB_PASSWORD` (any characters
except `${`). It then installs dependencies, runs migrations, loads the academy's reference
data and asks for the first `owner` password (or reads `DOJO_BOOTSTRAP_OWNER_PASSWORD`).
Later runs keep the existing `.env`, read it exactly as the app does, and only do what is
missing.

### Start and stop: pm2

`start.sh` builds the web app when its sources changed, applies new database migrations, then
starts (or restarts) the pm2 app **`dojo`** defined in `ecosystem.config.cjs`, saves the pm2
process list and waits until the app answers. Without pm2 it runs the same server in the
background (log in `.run/dojo.log`). `stop.sh` stops it and saves the pm2 list, so a reboot
does not bring back an app stopped on purpose.

```bash
pm2 status            # dojo should be "online"
pm2 logs dojo         # application log
pm2 restart dojo      # restart without rebuilding (./start.sh also rebuilds and migrates)
pm2 startup           # once: start pm2 (and dojo) at boot; run the command it prints
```

pm2 restarts the app if it crashes. To update: `git pull && ./start.sh`.

Over plain `http://` keep `DOJO_COOKIE_SECURE=false` in `backend/.env`, otherwise browsers
drop the sign-in cookie; once the site is served over HTTPS set it to `true` (and
`DOJO_ENVIRONMENT=production`, which also turns off the `/api/docs` pages). Open port 8090 in
the server's firewall if needed (e.g. `ufw allow 8090/tcp`).

### Development

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8090   # API
cd frontend && npm run dev                                          # http://localhost:5173
```

The Vite dev server reloads on every change and proxies `/api` to port 8090.

### Manual setup

```bash
# Database (as an administrator)
mariadb -uroot -e "CREATE DATABASE dojo CHARACTER SET utf8mb4;
  CREATE USER 'dojo'@'localhost' IDENTIFIED BY 'change-me';
  GRANT ALL ON dojo.* TO 'dojo'@'localhost';"

cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set DOJO_DB_PASSWORD
alembic upgrade head
DOJO_BOOTSTRAP_OWNER_PASSWORD='choose-a-strong-one' python -m app.seed --reference
cd ../frontend && npm ci && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8090   # http://<server>:8090
```

Sign in as `owner` with the bootstrap password, then create staff accounts under **Admin**.

`python -m app.seed --reference` loads the academy's programmes, belt system, price plans,
weekly timetable and uniform/gear catalogue (only into empty tables).

With Docker: `DOJO_DB_PASSWORD=… MYSQL_ROOT_PASSWORD=… docker compose up` starts MySQL and the
API on port 8090 (migrations run on start).

## Tests

```bash
cd backend
mysql -uroot -e "CREATE DATABASE dojo_test; GRANT ALL ON dojo_test.* TO 'dojo'@'localhost';"
python -m pytest -q     # runs against MySQL (database dojo_test)
ruff check . && ruff format --check .
```

## Project layout

```
backend/
  app/core/       config, database engine, security, dependencies (auth, branch scoping)
  app/models/     SQLAlchemy models: org, dojo, classes, progress, inventory
  app/schemas/    Pydantic request/response models
  app/api/        routers, one per area
  app/services/   memberships, stock ledger, audit
  alembic/        migrations, one per build phase
  tests/          API tests against MySQL
frontend/             built to frontend/dist and served by the API process
  src/components/ui/   shadcn/ui kit
  src/pages/           one page per area
  src/lib/, src/hooks/ API client, types, auth and branch state
```
