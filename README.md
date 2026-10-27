# E-Commerce DevOps Platform

An e-commerce backend built with FastAPI, PostgreSQL, Redis,
SQLAlchemy, Alembic, Docker Compose, and GitHub Actions.

## Features

- JWT authentication and role-based access control
- Product management with admin-only writes
- Product search across name, description, and SKU
- Price filters and offset pagination
- Redis product caching
- Order lifecycle and inventory reservations
- Persistent authenticated shopping carts
- Atomic cart checkout with user-scoped idempotency
- Concurrency tests for orders, carts, and checkout
- Database migrations with Alembic
- Structured request logging with generated request IDs
- Prometheus request counters and response-ready duration histograms
- Optional Prometheus collection and provisioned Grafana dashboard

Checkout creates a pending order. Payment processing is not implemented.

## Prerequisites

- Git
- Docker Desktop with the Linux engine running
- Available host ports: 8000, 5434, and 6379

The commands below use Windows Command Prompt.

## Configure Docker

For a new checkout, create the local configuration file:

```bat
copy .env.compose.example .env.compose
notepad .env.compose
```

Do not overwrite an existing configuration file.

Set POSTGRES_PASSWORD and use the matching password in DATABASE_URL
and TEST_DATABASE_URL. URL-encode special characters in the password
portion of database URLs.

Inside Docker, use:

- PostgreSQL: postgres:5432
- Redis: redis:6379

Set JWT_SECRET_KEY to a long, randomly generated secret.
Keep .env.compose private and out of version control.

Changing POSTGRES_PASSWORD does not change the password in an
already initialized PostgreSQL volume.

## Start the application

```bat
docker compose --env-file .env.compose config --quiet
docker compose --env-file .env.compose up -d --build
docker compose --env-file .env.compose ps -a
```

Compose waits for PostgreSQL and Redis health checks.
The API then runs `alembic upgrade head` before starting Uvicorn.

Open:

- Swagger UI: http://127.0.0.1:8000/docs
- API health: http://127.0.0.1:8000/health
- Database health: http://127.0.0.1:8000/health/database

The API container health check calls /health.
It verifies HTTP responsiveness, not database or Redis connectivity.
An unhealthy status alone does not automatically restart the container.

## Verify the deployment

Run each command separately:

```bat
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i http://127.0.0.1:8000/health/database
docker compose --env-file .env.compose exec -T api alembic current
docker compose --env-file .env.compose logs --tail=80 api
```

From Windows, PostgreSQL is available at localhost:5434.
Containers connect to PostgreSQL at postgres:5432.

## Product search examples

```text
GET /products?q=mouse
GET /products?q=wireless&min_price=20&max_price=50&limit=10
```

Search is case-insensitive. Search and price filters apply before
pagination. Results are ordered by product ID.

## Database initialization

PostgreSQL initialization scripts create ecommerce_test_db when
the PostgreSQL data directory is first initialized.

These scripts do not run again for an existing database volume.


## Optional monitoring

Monitoring requires available host ports 9090 and 3000.

Generate a Grafana password:

```bat
python -c "import secrets; print(secrets.token_hex(24))"
```

Set GRAFANA_ADMIN_PASSWORD in your private .env.compose file
to the generated value. Do not commit this password.

Start the application with monitoring. Run each command separately:

```bat
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml config --quiet
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml up -d --build --wait --wait-timeout 180
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml ps -a
```

Open:

- Prometheus: http://127.0.0.1:9090
- Grafana dashboard: http://127.0.0.1:3000/d/ecommerce-api

Log into Grafana as admin using GRAFANA_ADMIN_PASSWORD.

The Grafana data source and dashboard load automatically from
the version-controlled monitoring directory.

Prometheus scrapes api:8000/metrics every 15 seconds.
Prometheus and Grafana host ports bind only to 127.0.0.1.

### Dashboard examples

- Compare HTTP 200 product requests with HTTP 404 missing-route requests.
- Inspect estimated p95 response-ready duration by method and route.

Health checks are included in the status panel but excluded from
the application-route and latency panels.

The UP indicator confirms that Prometheus can scrape the API.
It does not verify PostgreSQL or Redis connectivity.

Rate calculations need multiple samples. Allow at least a minute
after startup and generate application traffic. Idle routes can
show zero rates or gaps in latency graphs.

Duration measurements exclude streaming and background-task completion.
Histogram percentiles are estimates, not exact request timings.

### Monitoring storage and credentials

API counters are process-local and reset when the API restarts.
Prometheus stores collected history in its named volume.
Retention is configured for 7 days with a 1 GB size limit;
whichever limit is reached first governs retention.
Actual disk use can exceed the configured retention size.

Grafana stores its state in a separate named volume.

GRAFANA_ADMIN_PASSWORD initializes the administrator password.
Changing this variable does not update an existing Grafana account.
Change an existing password through Grafana, and keep the local
configuration consistent.

### Stop the stack with monitoring

```bat
docker compose --env-file .env.compose -f compose.yaml -f compose.monitoring.yaml down
```

This retains PostgreSQL, Prometheus, and Grafana named volumes.
Do not add --volumes or -v unless you intend to delete their data.

This monitoring configuration targets a single API process.
Public deployment requires access controls for /metrics and a review
of exposed ports, credentials, and network configuration.

## Stop the application

```bat
docker compose --env-file .env.compose down
```

This retains the named PostgreSQL data volume.
Adding `-v` deletes the volume and its database data.

## Validation status

- Most recent local application suite: 195 passed, no skips
- Docker image build and existing-volume startup verified
- Existing database upgraded to checkout_key_v1
- API and database health endpoints returned HTTP 200
- Redis connectivity verified from the API container
- Fresh-volume initialization verified by the existing CI smoke test
- Prometheus collection and Grafana dashboard verified locally
- Monitoring CI verification added; its first CI run is pending

Production deployment has not been verified.
This Compose setup is intended for local development.