#!/usr/bin/env bash
# One-time setup for a local Dojo Manager install (MySQL 8 or MariaDB). Safe to re-run:
# every step skips work that is already done.
#
#   ./runonce.sh
#
# Optional environment variables (only used when backend/.env does not exist yet):
#   DOJO_DB_HOST / DOJO_DB_PORT / DOJO_DB_NAME / DOJO_DB_USER   (default 127.0.0.1 / 3306 / dojo / dojo)
#   DOJO_DB_PASSWORD               app database password (generated if not set)
# The database is reached only as the app user from backend/.env (never as root). If the
# database or user is missing and that user cannot create it, the script prints the SQL for
# an administrator to run and stops.
#
# Always honoured:
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
# Where Dojo Manager listens (API and web app on one port).
DOJO_HOST=0.0.0.0
DOJO_PORT=8090
# Plain http://; set to true once the site is served over HTTPS.
DOJO_COOKIE_SECURE=false
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

[[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]] || die "DOJO_DB_NAME may only contain letters, digits and _"

# ---------------------------------------------------------------- database
# Only the app's own account (from backend/.env) is used; never root or another admin user.
# MYSQL_PWD keeps the password off the command line (and out of `ps`).
db_app() { MYSQL_PWD="$DB_PASSWORD" "$DB_CLI" -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$@"; }

need_admin() {
  cat >&2 <<MSG

Error: $1.
This script connects only as '$DB_USER', so a database administrator needs to run this
once (with the password from backend/.env in place of <password>):

  CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '<password>';
  CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '<password>';
  ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '<password>';
  ALTER USER '$DB_USER'@'127.0.0.1' IDENTIFIED BY '<password>';
  GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost', '$DB_USER'@'127.0.0.1';

Then run ./runonce.sh again.
MSG
  exit 1
}

say "Checking database '$DB_NAME' as '$DB_USER'"
if err="$(db_app -N -e "SELECT 1" "$DB_NAME" 2>&1 >/dev/null)"; then
  echo "Database exists and '$DB_USER' can use it; skipping creation."
else
  case "$err" in
    *"ERROR 1049"*)  # unknown database: the user logged in, so try creating it as that user
      if db_app -e "CREATE DATABASE \`$DB_NAME\` CHARACTER SET utf8mb4" 2>/dev/null; then
        echo "Created database '$DB_NAME' as '$DB_USER'."
      else
        need_admin "database '$DB_NAME' does not exist and '$DB_USER' is not allowed to create it"
      fi ;;
    *"ERROR 1045"* | *"ERROR 1698"*)  # wrong password, or no such user
      need_admin "the server refused '$DB_USER' with the password in backend/.env" ;;
    *"ERROR 1044"*) need_admin "'$DB_USER' has no access to database '$DB_NAME'" ;;
    *"ERROR 2002"* | *"ERROR 2003"* | *"ERROR 2005"*)
      die "cannot reach the database server at $DB_HOST:$DB_PORT. Is it running?" ;;
    *) die "cannot use database '$DB_NAME': $err" ;;
  esac
fi

# ---------------------------------------------------------------- schema and data
say "Applying database migrations"
(cd "$BACKEND" && "$VENV/bin/alembic" upgrade head) \
  || die "migrations failed. '$DB_USER' needs full rights on '$DB_NAME' (CREATE, ALTER, INDEX, REFERENCES, ...)"

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
