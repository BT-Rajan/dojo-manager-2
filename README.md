# Dojo Manager

Management system for a multi-branch martial arts academy: members and belt progression,
memberships and payments, the class timetable and attendance, leads and trial classes,
gradings and seminars, front-desk operations, and inventory.

| Layer    | Stack |
|----------|-------|
| API      | Python 3.12, FastAPI, SQLAlchemy 2 (async, `asyncmy`), Pydantic v2, Alembic |
| Database | MySQL 8 (InnoDB, utf8mb4) |
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

## Running locally

Requirements: Python 3.12+, Node 22, MySQL 8 (running), and the `mysql` client.

```bash
./runonce.sh   # one-time setup; safe to re-run
./start.sh     # API on :8000, web app on http://localhost:5173
./stop.sh
```

`runonce.sh` creates the database and user (as MySQL `root` over the local socket, or set
`MYSQL_ROOT_PASSWORD`), writes `backend/.env` with a generated database password
(permissions 600), installs dependencies, runs migrations, loads the academy's reference data
and asks for the first `owner` password (or reads `DOJO_BOOTSTRAP_OWNER_PASSWORD`). On later
runs it keeps the existing `.env` and only does what is missing. `start.sh` applies any new
migrations, starts both servers in the background, waits until they answer and writes logs
and process ids to `.run/`; ports can be changed with `API_PORT` / `WEB_PORT`.

### Manual setup

```bash
# Database
mysql -uroot -e "CREATE DATABASE dojo CHARACTER SET utf8mb4;
  CREATE USER 'dojo'@'localhost' IDENTIFIED BY 'change-me';
  GRANT ALL ON dojo.* TO 'dojo'@'localhost';"

# API (http://localhost:8000, docs at /api/docs)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set DOJO_DB_PASSWORD, DOJO_COOKIE_SECURE=false for http
alembic upgrade head
DOJO_BOOTSTRAP_OWNER_PASSWORD='choose-a-strong-one' python -m app.seed --reference
uvicorn app.main:app --reload

# Web (http://localhost:5173, proxies /api to :8000)
cd ../frontend
npm ci
npm run dev
```

Sign in as `owner` with the bootstrap password, then create staff accounts under **Admin**.

`python -m app.seed --reference` loads the academy's programmes, belt system, price plans,
weekly timetable and uniform/gear catalogue (only into empty tables).

With Docker: `DOJO_DB_PASSWORD=… MYSQL_ROOT_PASSWORD=… docker compose up` starts MySQL and the
API (migrations run on start).

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
frontend/
  src/components/ui/   shadcn/ui kit
  src/pages/           one page per area
  src/lib/, src/hooks/ API client, types, auth and branch state
```
