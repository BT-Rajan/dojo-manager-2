#!/usr/bin/env bash
# One-time setup for a local Dojo Manager install. Safe to re-run: every step skips work
# that is already done.
#
#   ./runonce.sh
#
# Optional environment variables:
#   DOJO_DB_HOST / DOJO_DB_PORT / DOJO_DB_NAME / DOJO_DB_USER   (default 127.0.0.1 / 3306 / dojo / dojo)
#   DOJO_DB_PASSWORD               app database password (generated if not set)
#   MYSQL_ROOT_USER / MYSQL_ROOT_PASSWORD  admin account used to create the database and user
#                                  (default root via the local socket, no password)
#   DOJO_BOOTSTRAP_OWNER_USERNAME / DOJO_BOOTSTRAP_OWNER_PASSWORD   first owner account
#                                  (password prompted for if not set)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
ENV_FILE="$BACKEND/.env"
VENV="$BACKEND/.venv"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- prerequisites
say "Checking prerequisites"
command -v python3 >/dev/null || die "python3 (3.12 or newer) is required"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' \
  || die "Python 3.12 or newer is required (found $(python3 --version))"
command -v node >/dev/null || die "Node.js 22 is required"
command -v npm >/dev/null || die "npm is required"
command -v mysql >/dev/null || die "the mysql command-line client is required"
echo "python $(python3 --version | cut -d' ' -f2), node $(node --version), $(mysql --version | head -c 60)"

# ---------------------------------------------------------------- backend/.env
env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true; }

if [[ -f "$ENV_FILE" ]]; then
  # An existing .env is the source of truth, so a re-run always targets the same database.
  say "Keeping existing backend/.env"
  DB_HOST="$(env_value DOJO_DB_HOST)"; DB_HOST="${DB_HOST:-127.0.0.1}"
  DB_PORT="$(env_value DOJO_DB_PORT)"; DB_PORT="${DB_PORT:-3306}"
  DB_NAME="$(env_value DOJO_DB_NAME)"; DB_NAME="${DB_NAME:-dojo}"
  DB_USER="$(env_value DOJO_DB_USER)"; DB_USER="${DB_USER:-dojo}"
  DB_PASSWORD="$(env_value DOJO_DB_PASSWORD)"
  [[ -n "$DB_PASSWORD" ]] || die "backend/.env has no DOJO_DB_PASSWORD"
else
  DB_HOST="${DOJO_DB_HOST:-127.0.0.1}"
  DB_PORT="${DOJO_DB_PORT:-3306}"
  DB_NAME="${DOJO_DB_NAME:-dojo}"
  DB_USER="${DOJO_DB_USER:-dojo}"
  say "Creating backend/.env"
  DB_PASSWORD="${DOJO_DB_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"
  umask 077
  cat > "$ENV_FILE" <<ENV
DOJO_ENVIRONMENT=development
DOJO_TIMEZONE=Asia/Kuwait
DOJO_DB_HOST=$DB_HOST
DOJO_DB_PORT=$DB_PORT
DOJO_DB_NAME=$DB_NAME
DOJO_DB_USER=$DB_USER
DOJO_DB_PASSWORD=$DB_PASSWORD
# Local http:// development; set to true behind HTTPS.
DOJO_COOKIE_SECURE=false
DOJO_CORS_ORIGINS=["http://localhost:5173"]
ENV
  umask 022
  echo "Written (permissions 600). The database password is stored only there."
fi
# These values are embedded in SQL below, so keep them to safe character sets.
[[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]] || die "DOJO_DB_NAME may only contain letters, digits and _"
[[ "$DB_USER" =~ ^[A-Za-z0-9_]+$ ]] || die "DOJO_DB_USER may only contain letters, digits and _"
[[ "$DB_PASSWORD" =~ ^[A-Za-z0-9_.~-]+$ ]] \
  || die "DOJO_DB_PASSWORD may only contain letters, digits and _ . ~ -"

# ---------------------------------------------------------------- MySQL database and user
say "Creating MySQL database '$DB_NAME' and user '$DB_USER' (if missing)"
ROOT_USER="${MYSQL_ROOT_USER:-root}"
mysql_admin() {
  # MYSQL_PWD keeps the admin password off the command line (and out of `ps`).
  if [[ -n "${MYSQL_ROOT_PASSWORD:-}" ]]; then
    MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -h "$DB_HOST" -P "$DB_PORT" -u "$ROOT_USER" "$@"
  else
    mysql -u "$ROOT_USER" "$@"   # local socket authentication
  fi
}
mysql_admin -e "SELECT 1" >/dev/null 2>&1 \
  || die "cannot connect to MySQL as '$ROOT_USER'. Is MySQL running? Set MYSQL_ROOT_PASSWORD if needed."
mysql_admin <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}_test\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost', '$DB_USER'@'127.0.0.1';
GRANT ALL ON \`${DB_NAME}_test\`.* TO '$DB_USER'@'localhost', '$DB_USER'@'127.0.0.1';
SQL
echo "Done (also created ${DB_NAME}_test for the test suite)."

# ---------------------------------------------------------------- Python environment
say "Installing backend dependencies into backend/.venv"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND/requirements-dev.txt"

# ---------------------------------------------------------------- schema and data
say "Applying database migrations"
(cd "$BACKEND" && "$VENV/bin/alembic" upgrade head)

say "Loading reference data and the first owner account"
user_count="$(MYSQL_PWD="$DB_PASSWORD" mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -N -e \
  "SELECT COUNT(*) FROM \`$DB_NAME\`.users")"
if [[ "$user_count" == "0" && -z "${DOJO_BOOTSTRAP_OWNER_PASSWORD:-}" ]]; then
  owner="${DOJO_BOOTSTRAP_OWNER_USERNAME:-owner}"
  while :; do
    read -rsp "Choose a password for the '$owner' account (10+ characters): " pw1; echo
    read -rsp "Repeat it: " pw2; echo
    [[ "$pw1" == "$pw2" ]] || { echo "Passwords do not match."; continue; }
    (( ${#pw1} >= 10 )) || { echo "Too short."; continue; }
    break
  done
  export DOJO_BOOTSTRAP_OWNER_PASSWORD="$pw1"
fi
(cd "$BACKEND" && "$VENV/bin/python" -m app.seed --reference)
unset DOJO_BOOTSTRAP_OWNER_PASSWORD

# ---------------------------------------------------------------- frontend
say "Installing frontend dependencies"
(cd "$FRONTEND" && npm ci --no-audit --no-fund)

say "Setup complete. Run ./start.sh to start Dojo Manager."
