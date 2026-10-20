#!/usr/bin/env bash
# One-time setup for a local Dojo Manager install (MySQL 8 or MariaDB). Safe to re-run:
# every step skips work that is already done.
#
#   ./runonce.sh
#
# Optional environment variables (only used when backend/.env does not exist yet):
#   DOJO_DB_HOST / DOJO_DB_PORT / DOJO_DB_NAME / DOJO_DB_USER   (default 127.0.0.1 / 3306 / dojo / dojo)
#   DOJO_DB_PASSWORD               app database password (generated if not set)
# Always honoured:
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
command -v node >/dev/null || die "Node.js 20 or newer is required"
node -e 'process.exit(Number(process.versions.node.split(".")[0]) < 20 ? 1 : 0)' \
  || die "Node.js 20 or newer is required (found $(node --version))"
command -v npm >/dev/null || die "npm is required"
# MariaDB ships `mariadb` (its `mysql` name is deprecated); MySQL ships `mysql`.
DB_CLI="$(command -v mariadb || command -v mysql || true)"
[[ -n "$DB_CLI" ]] || die "the mariadb or mysql command-line client is required"
echo "python $(python3 --version | cut -d' ' -f2), node $(node --version), $("$DB_CLI" --version | head -c 70)"

# ---------------------------------------------------------------- Python environment
say "Installing backend dependencies into backend/.venv"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$BACKEND/requirements-dev.txt"

# Print one setting exactly as the app will see it (backend/.env plus DOJO_* overrides).
app_setting() {
  (cd "$BACKEND" && "$VENV/bin/python" - "$1" <<'PY'
import sys
from app.core.config import get_settings
value = getattr(get_settings(), sys.argv[1])
sys.stdout.write(str(value.get_secret_value() if hasattr(value, "get_secret_value") else value))
PY
  )
}

# ---------------------------------------------------------------- backend/.env
# A value written so the app reads it back unchanged ("Pass#1" stays as is; values with
# spaces or quotes are quoted).
env_quote() {
  if [[ "$1" =~ ^[^[:space:]\"\'\\]*$ && "$1" != \#* ]]; then printf '%s' "$1"
  elif [[ "$1" != *\'* ]]; then printf "'%s'" "$1"
  elif [[ "$1" != *\"* && "$1" != *\\* ]]; then printf '"%s"' "$1"
  else die "the database password cannot contain both single and double quotes"
  fi
}

if [[ -f "$ENV_FILE" ]]; then
  say "Keeping existing backend/.env"
  WANTED_PASSWORD=""
else
  say "Creating backend/.env"
  WANTED_PASSWORD="${DOJO_DB_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"
  umask 077
  cat > "$ENV_FILE" <<ENV
DOJO_ENVIRONMENT=development
DOJO_TIMEZONE=Asia/Kuwait
DOJO_DB_HOST=${DOJO_DB_HOST:-127.0.0.1}
DOJO_DB_PORT=${DOJO_DB_PORT:-3306}
DOJO_DB_NAME=${DOJO_DB_NAME:-dojo}
DOJO_DB_USER=${DOJO_DB_USER:-dojo}
DOJO_DB_PASSWORD=$(env_quote "$WANTED_PASSWORD")
# Local http:// development; set to true behind HTTPS.
DOJO_COOKIE_SECURE=false
DOJO_CORS_ORIGINS=["http://localhost:5173"]
ENV
  umask 022
  echo "Written (permissions 600). The database password is stored only there."
fi

DB_HOST="$(app_setting db_host)"
DB_PORT="$(app_setting db_port)"
DB_NAME="$(app_setting db_name)"
DB_USER="$(app_setting db_user)"
DB_PASSWORD="$(app_setting db_password)"
[[ -n "$DB_PASSWORD" ]] || die "no database password: set DOJO_DB_PASSWORD in backend/.env"
# Check the file itself round-trips (without the DOJO_DB_PASSWORD override, if one is set).
if [[ -n "$WANTED_PASSWORD" && "$(env -u DOJO_DB_PASSWORD bash -c "$(declare -f app_setting); \
      BACKEND='$BACKEND' VENV='$VENV' app_setting db_password")" != "$WANTED_PASSWORD" ]]; then
  rm -f "$ENV_FILE"
  # shellcheck disable=SC2016  # the literal text ${...} is meant
  die 'the app would read that password differently (it expands ${...}); choose another'
fi
echo "Database: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"

# Names are used as SQL identifiers, so keep them simple.
[[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]] || die "DOJO_DB_NAME may only contain letters, digits and _"
[[ "$DB_USER" =~ ^[A-Za-z0-9_]+$ ]] || die "DOJO_DB_USER may only contain letters, digits and _"
# Any password works (#, @, !, spaces, quotes ...): it goes into a SQL string literal with
# single quotes doubled. A backslash would be read differently depending on the server's
# SQL mode, so that one character is refused rather than guessed at.
[[ "$DB_PASSWORD" != *\\* ]] || die "the database password must not contain a backslash"
SQL_PASSWORD="${DB_PASSWORD//\'/\'\'}"

# ---------------------------------------------------------------- database and user
say "Creating database '$DB_NAME' and user '$DB_USER' (if missing)"
ROOT_USER="${MYSQL_ROOT_USER:-root}"
db_admin() {
  # MYSQL_PWD keeps passwords off the command line (and out of `ps`).
  if [[ -n "${MYSQL_ROOT_PASSWORD:-}" ]]; then
    MYSQL_PWD="$MYSQL_ROOT_PASSWORD" "$DB_CLI" -h "$DB_HOST" -P "$DB_PORT" -u "$ROOT_USER" "$@"
  else
    "$DB_CLI" -u "$ROOT_USER" "$@"   # local socket authentication
  fi
}
db_admin -e "SELECT 1" >/dev/null 2>&1 \
  || die "cannot connect as '$ROOT_USER'. Is the database running? Set MYSQL_ROOT_PASSWORD if needed."
db_admin <<SQL
-- utf8mb4 with the server's default collation (MySQL and MariaDB name theirs differently).
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}_test\` CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$SQL_PASSWORD';
CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$SQL_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$SQL_PASSWORD';
ALTER USER '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$SQL_PASSWORD';
GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost', '$DB_USER'@'127.0.0.1';
GRANT ALL ON \`${DB_NAME}_test\`.* TO '$DB_USER'@'localhost', '$DB_USER'@'127.0.0.1';
SQL
MYSQL_PWD="$DB_PASSWORD" "$DB_CLI" -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -e "SELECT 1" \
  >/dev/null || die "the app user cannot log in with the password from backend/.env"
echo "Done; the app user logs in with the password from backend/.env."

# ---------------------------------------------------------------- schema and data
say "Applying database migrations"
(cd "$BACKEND" && "$VENV/bin/alembic" upgrade head)

say "Loading reference data and the first owner account"
user_count="$(MYSQL_PWD="$DB_PASSWORD" "$DB_CLI" -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -N -e \
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
