#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/home/ec2-user/backups/ecommerce}"
DB_CONTAINER="${DB_CONTAINER:-ecommerce-devops-platform-postgres-1}"

for command in docker flock mktemp date find; do
    command -v "$command" >/dev/null || {
        echo "Required command missing: $command" >&2
        exit 1
    }
done

install -d -m 700 "$BACKUP_DIR"

exec 9>"$BACKUP_DIR/.backup.lock"
if ! flock -n 9; then
    echo "Another backup is running; skipping."
    exit 0
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary_file="$(mktemp "$BACKUP_DIR/ecommerce_db-${timestamp}-XXXXXX.partial")"

cleanup() {
    if [[ -n "$temporary_file" ]]; then
        rm -f -- "$temporary_file"
    fi
}
trap cleanup EXIT

docker exec "$DB_CONTAINER" \
    pg_dump -U postgres -d ecommerce_db -Fc > "$temporary_file"

test -s "$temporary_file"

docker exec -i "$DB_CONTAINER" \
    pg_restore --list < "$temporary_file" > /dev/null

backup_file="${temporary_file%.partial}.dump"
mv -- "$temporary_file" "$backup_file"
temporary_file=""

echo "Backup created and archive listing checked: $backup_file"

# Remove this script's backups aged at least seven days.
# Cleanup occurs only after a new backup succeeds.
find "$BACKUP_DIR" -maxdepth 1 -type f \
    -name 'ecommerce_db-*.dump' -mtime +6 -print -delete