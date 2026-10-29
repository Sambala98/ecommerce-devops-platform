# AWS deployment and recovery runbook

## Deployment overview

Public API documentation:

https://ecommerce-project.duckdns.org/docs

Request path:

HTTPS client → Nginx → API container → PostgreSQL / Redis

The EC2 server runs Amazon Linux 2023 with Docker and Docker Compose.

The API, PostgreSQL, and Redis run in containers.

Nginx and Certbot run on the host.

Prometheus and Grafana are available through the local monitoring

configuration; they are not deployed on this EC2 server.

Checkout creates a PENDING order. Payment processing is not implemented.

## Files and configuration

AWS project directory:

`/home/ec2-user/ecommerce-devops-platform`

Private application configuration:

`/home/ec2-user/ecommerce-devops-platform/.env.compose`

Selected release image:

`/home/ec2-user/ecommerce-release.env`

The release file contains:

```dotenv

API_IMAGE=ghcr.io/sambala98/ecommerce-devops-platform@sha256:REPLACE_WITH_PUBLISHED_DIGEST

```

Use the container image reference from the workflow's

"Published API image" summary. The digest of a downloadable

`.dockerbuild` artifact is not the container image digest.

Never commit private environment files, database dumps, SSH private

keys, or access tokens.

## Start or resume the server

1. Start the existing EC2 instance and wait for status checks.

2. Read its current public IPv4 address.

3. Update `ecommerce-project.duckdns.org` in Duck DNS if the IP changed.

4. Confirm the SSH security group allows your current public IP.

5. Connect with the matching SSH key.

6. Verify public HTTPS health and container status.

A Stop/Start can change the public IP. A normal reboot generally retains it.

Containers use `restart: unless-stopped`.

Docker and Nginx are enabled at boot.

## Health checks

Run these on the AWS Linux host:

```bash

curl --fail-with-body --silent --show-error --max-time 20 https://ecommerce-project.duckdns.org/health/database

```

Expected:

```json

{"status":"healthy","database":"connected"}

```

Inspect all core containers:

```bash

sudo docker compose --env-file /home/ec2-user/ecommerce-devops-platform/.env.compose -f /home/ec2-user/ecommerce-devops-platform/compose.yaml ps

```

Check the running API image:

```bash

sudo docker inspect --format '{{.Config.Image}}' ecommerce-devops-platform-api-1

```

`/health` checks the API response. `/health/database` checks PostgreSQL.

Neither endpoint verifies Redis. The Redis container has its own health check.

## Release publishing

On a push to main, GitHub Actions publishes the API image only after

`test-and-build` and `compose-smoke-test` succeed.

Images are published to:

`ghcr.io/sambala98/ecommerce-devops-platform`

Each image has a commit-based tag. Deploy using its registry digest

to select exact image content.

Pull requests validate the changes but do not publish images.

## Deploy a selected release

Run all deployment commands in the AWS SSH session.

Before changing the selected image:

1. Review application and migration changes.

2. Ensure the currently selected release file matches the running image.

3. Run a database backup and confirm the service succeeded, including S3 upload.

4. Preserve the previous release selection.

```bash

sudo systemctl start ecommerce-db-backup.service

```

```bash

sudo journalctl -u ecommerce-db-backup.service -n 20 --no-pager -l

```

Do not proceed if the backup failed.

```bash

cp -p /home/ec2-user/ecommerce-release.env /home/ec2-user/ecommerce-release.previous.env

```

Update the repository:

```bash

git -C /home/ec2-user/ecommerce-devops-platform pull --ff-only origin main

```

Edit `/home/ec2-user/ecommerce-release.env` to select the intended digest.

Pull that exact image before replacing the running container.

From the project directory:

```bash

cd /home/ec2-user/ecommerce-devops-platform

```

```bash

sudo docker compose --env-file .env.compose --env-file /home/ec2-user/ecommerce-release.env -f compose.yaml -f compose.release.yaml pull api

```

```bash

sudo docker compose --env-file .env.compose --env-file /home/ec2-user/ecommerce-release.env -f compose.yaml -f compose.release.yaml config --quiet

```

```bash

sudo docker compose --env-file .env.compose --env-file /home/ec2-user/ecommerce-release.env -f compose.yaml -f compose.release.yaml up -d --no-build --no-deps --wait --wait-timeout 180 api

```

This replaces only the API container. Brief downtime is expected.

API startup runs `alembic upgrade head` before starting Uvicorn.

Verify the public database health endpoint and inspect the running image.

Do not delete database volumes when troubleshooting.

## Application rollback

Before rolling back, confirm the previous application is compatible with

the current database schema. Matching migration heads alone do not prove

compatibility.

From the AWS project directory:

```bash

sudo docker compose --env-file .env.compose --env-file /home/ec2-user/ecommerce-release.previous.env -f compose.yaml -f compose.release.yaml up -d --no-build --no-deps --wait --wait-timeout 180 api

```

Verify public health and the running image.

After a successful rollback, make the main release selection agree

with the actual running version:

```bash

cp -p /home/ec2-user/ecommerce-release.previous.env /home/ec2-user/ecommerce-release.env

```

This rolls back application image selection. It does not downgrade or

restore the database.

A controlled rollback to the preserved pre-registry image and return

to the published image was tested successfully with unchanged migration

head `checkout_key_v1`.

## Database backups

Installed script:

`/usr/local/libexec/ecommerce/backup_database.sh`

Local scheduled backups:

`/var/backups/ecommerce`

Service:

`ecommerce-db-backup.service`

Timer:

`ecommerce-db-backup.timer`

Schedule: daily at 08:00 UTC, with up to five minutes of randomized delay.

The persistent timer attempts a catch-up run after a missed schedule.

Failed service runs retry after 60 seconds, limited to five starts

within 15 minutes.

The script:

1. Prevents overlapping runs with a lock.

2. Creates a private custom-format PostgreSQL dump.

3. Checks that its archive listing can be read.

4. Uploads it to S3 when configured.

5. Cleans up matching local backups at least seven days old only

   after the preceding steps succeed.

On upload failure, the completed local backup remains and cleanup is skipped.

Reading an archive listing is not a full restore test.

Inspect scheduling and results:

```bash

sudo systemctl list-timers --all ecommerce-db-backup.timer --no-pager

```

```bash

sudo journalctl -u ecommerce-db-backup.service -n 30 --no-pager -l

```

```bash

sudo ls -lh /var/backups/ecommerce

```

## S3 backup storage

Bucket:

`sudheer-ecommerce-backups-20261029`

Prefix:

`postgres/`

Public access is blocked. Uploads use SSE-S3 encryption.

The EC2 role `EcommerceBackupRole` supplies temporary credentials.

Its backup policy grants upload and incomplete-upload abort permissions

only under this prefix. It does not grant download or completed-object

deletion permissions.

For recovery, use a separately authorized identity to download a backup.

Do not broaden the server role merely to work around a denied download.

S3 lifecycle expires current objects under `postgres/` after seven days.

Bucket versioning is disabled, so expiration permanently removes them.

Expiration is independent of backup success or EC2 availability.

All S3 backups can expire during an extended server shutdown.

## Restore verification and limits

A manual backup was restored into a separate database named

`ecommerce_restore_check`. All seven application tables were present.

At that time, both live and restored databases contained zero users,

products, and orders. Recovery of populated application data remains untested.

The manual backup was downloaded to Windows, and its SHA-256 checksum

matched the server copy.

Restore future backups into a separate database first. Validate expected

schema and data before planning any live database replacement.

Backups do not include PostgreSQL server-wide roles.

Database dumps also do not replace backups of private configuration

or recovery documentation.

## HTTPS and network restrictions

Nginx configuration:

`/etc/nginx/conf.d/fastapi.conf`

HTTP redirects to HTTPS. Public `/metrics` requests return 404.

Published API, PostgreSQL, and Redis ports bind to localhost.

The security group permits HTTP/HTTPS publicly and SSH from the

administrator's public IP.

Certbot renewal simulation passed:

```bash

sudo certbot renew --dry-run

```

Renewal still depends on correct DNS, network access, and server availability.

## Pausing and remaining work

Stop the EC2 instance to pause compute usage; do not terminate it.

The public demo and backup execution are unavailable while it is stopped.

EBS and S3 storage can continue generating charges.

Remaining verification and operations work:

- Observe an updated timer-triggered backup reaching S3.

- Restore a backup containing actual sample application data.

- Verify recovery using an S3-downloaded backup.

- Configure and test meaningful failure notifications.

- Keep deployment and recovery instructions current.
