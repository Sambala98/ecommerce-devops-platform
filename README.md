# E-Commerce DevOps Platform

An e-commerce backend built with FastAPI, PostgreSQL, and Redis, deployed on AWS EC2 using Docker Compose and Nginx.

The project demonstrates transactional checkout, inventory concurrency protection, automated testing, versioned container releases, database recovery, and uptime alerting.

## Project status

- Backend implemented and deployed on AWS.
- HTTPS and certificate renewal tested.
- Database backup and S3 recovery tested.
- Container rollback and reboot recovery tested.
- Downtime email alert tested.
- Frontend development is in progress.
- Payment processing is not implemented.

Checkout creates a PENDING order; it does not process a payment.

## Live API

- [API documentation](https://ecommerce-project.duckdns.org/docs)
- [API health](https://ecommerce-project.duckdns.org/health)
- [Database health](https://ecommerce-project.duckdns.org/health/database)

The learning environment may be stopped between development sessions to control AWS costs.

## Architecture

Public requests follow this path:

HTTPS client → Nginx → FastAPI container → PostgreSQL / Redis

Docker Compose runs the API, PostgreSQL, and Redis.
Nginx and Certbot run on the EC2 host.

Prometheus and Grafana are available in the optional local monitoring stack. They are not deployed on the EC2 server.

## Technology stack

| Area | Technologies |
| --- | --- |
| API | Python, FastAPI, Pydantic |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Authentication | JWT, Argon2id, role-based access control |
| Caching | Redis |
| Testing | Pytest, integration and concurrency tests |
| Containers | Docker, Docker Compose |
| CI and image publishing | GitHub Actions, GitHub Container Registry |
| Hosting | AWS EC2, Nginx, Certbot |
| Backups | PostgreSQL custom-format dumps, Amazon S3, systemd timer |
| Monitoring | UptimeRobot; optional local Prometheus and Grafana |

## Backend features

### Authentication and authorization

- User registration and login.
- JWT authentication.
- USER and ADMIN roles.
- Admin-only product writes.

### Product catalog

- Unique product SKUs.
- Search across name, description, and SKU.
- Price filtering and offset pagination.
- Redis product caching.

Example requests:

```text
GET /products?q=mouse
GET /products?q=wireless&min_price=20&max_price=50&limit=10
```

Search is case-insensitive. Search and price filters apply before pagination. Results are ordered by product ID.

### Cart, checkout, and orders

- Persistent authenticated shopping carts.
- Cart quantity updates and item removal.
- Atomic checkout with user-scoped idempotency keys.
- Order lifecycle management.
- Inventory reservations and concurrency protection.

Examples:

- Retrying checkout with the same valid idempotency key avoids creating a duplicate order.
- Concurrent purchases of the last available unit are tested to preserve inventory consistency.

## Deployment and operations

- API container runs as a non-root user.
- Debug mode is disabled by default.
- Published API, PostgreSQL, and Redis ports bind to localhost.
- Nginx exposes the API through HTTPS.
- Public access to `/metrics` is blocked.
- Core containers use `restart: unless-stopped`.
- API startup runs database migrations before starting Uvicorn.
- Successful CI runs on main publish versioned API images to GHCR.
- Release deployments select an image through `API_IMAGE`, including digest-pinned references.

See [the deployment and recovery runbook](deploy/RUNBOOK.md) for deployment, rollback, backup, recovery, and pause/resume procedures.

## Run locally

The commands below use Windows Command Prompt.

### Prerequisites

- Git.
- Docker Desktop with the Linux engine running.
- Available host ports: 8000, 5434, and 6379.

### Configure the environment

For a new checkout:

```cmd
copy .env.compose.example .env.compose
notepad .env.compose
```

Do not overwrite an existing configuration file.

Configure:

- `POSTGRES_PASSWORD`.
- Matching passwords in `DATABASE_URL` and `TEST_DATABASE_URL`.
- A long, randomly generated `JWT_SECRET_KEY`.

URL-encode special characters in database URL passwords.

Inside Docker, use these service addresses:

- PostgreSQL: `postgres:5432`
- Redis: `redis:6379`

Keep `.env.compose` private and out of version control.

Changing `POSTGRES_PASSWORD` does not change the password in an already initialized PostgreSQL volume.

### Start the application

Run each command separately:

```cmd
docker compose --env-file .env.compose config --quiet
docker compose --env-file .env.compose up -d --build --wait --wait-timeout 180
docker compose --env-file .env.compose ps
```

Open:

- [Local Swagger UI](http://127.0.0.1:8000/docs)
- [Local API health](http://127.0.0.1:8000/health)
- [Local database health](http://127.0.0.1:8000/health/database)

From Windows, PostgreSQL is available at `127.0.0.1:5434`.
Containers connect through `postgres:5432`.

### Check health and logs

```cmd
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i http://127.0.0.1:8000/health/database
docker compose --env-file .env.compose exec -T api alembic current
docker compose --env-file .env.compose logs --tail=80 api
```

The container health check calls `/health`. It checks HTTP responsiveness, not database or Redis connectivity.

An unhealthy status alone does not automatically restart a container.

### Database initialization

PostgreSQL initialization scripts create `ecommerce_test_db` when the data directory is first initialized.

These scripts do not run again for an existing database volume.

Tests require a separate database named `ecommerce_test_db`. Guards reject unexpected database names and application/test database name collisions.

### Stop the local application

```cmd
docker compose --env-file .env.compose down
```

Named volumes are retained. Adding `--volumes` or `-v` deletes their data.

## Optional local monitoring

Monitoring requires available host ports 9090 and 3000.

Set a strong `GRAFANA_ADMIN_PASSWORD` in your private `.env.compose` file.

Start the monitoring stack:

```cmd
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml config --quiet
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml up -d --build --wait --wait-timeout 180
```

Open:

- [Prometheus](http://127.0.0.1:9090)
- [Grafana dashboard](http://127.0.0.1:3000/d/ecommerce-api)

Log into Grafana as `admin` using your configured password.

The data source and dashboard are provisioned from the repository.

Prometheus scrapes `api:8000/metrics` every 15 seconds. Monitoring ports bind to localhost.

Dashboard examples:

- Compare successful product requests with missing-route requests.
- Inspect estimated p95 response-ready duration by method and route.

Allow at least a minute and generate application traffic before evaluating rates.

Metrics are process-local and reset when the API restarts. Duration measurements exclude streaming and background-task completion. Histogram percentiles are estimates.

Prometheus history uses a named volume with seven-day and 1 GB retention limits. Actual disk use can exceed the retention size setting.

Grafana uses a separate named volume. Changing `GRAFANA_ADMIN_PASSWORD` does not change the password of an existing Grafana account.

Stop the monitoring stack:

```cmd
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml down
```

This retains its named volumes.

## Backups and recovery

The database backup script:

- Creates a PostgreSQL custom-format dump.
- Checks that the archive can be listed.
- Uploads the completed backup to S3 when configured.
- Preserves completed local backups if upload fails.
- Removes local backups aged at least seven days only after successful backup and configured upload.

A systemd timer schedules daily backups at approximately 08:00 UTC, with up to five minutes of randomized delay.

S3 access uses an EC2 IAM role. No static AWS access keys are required on the instance.

The configured S3 lifecycle expires backups after seven days, independently of whether new backups succeed.

Recovery verification included downloading a populated backup from S3, restoring it into an isolated database, and checking product prices, stock, and reservations. Temporary recovery databases were removed afterward.

Archive listing checks are not a substitute for a restore test.

## Validation evidence

Completed checks include:

- Last recorded full application test run: 195 passed.
- Fresh-database initialization and migration checks in CI.
- Compose startup and health checks.
- Local Prometheus collection and Grafana dashboard verification.
- Public HTTPS database-health verification.
- Certificate renewal dry run.
- EC2 reboot recovery.
- Versioned GHCR image deployment.
- Controlled rollback and return to the selected release.
- S3 upload and denied-upload preservation tests.
- Populated-data S3 restore verification.
- UptimeRobot downtime email delivery.