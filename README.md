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

## Stop the application

```bat
docker compose --env-file .env.compose down
```

This retains the named PostgreSQL data volume.
Adding `-v` deletes the volume and its database data.

## Validation status

- Most recent local application suite: 176 passed, no skips
- Docker image build and existing-volume startup verified
- Existing database upgraded to checkout_key_v1
- API and database health endpoints returned HTTP 200
- Redis connectivity verified from the API container

Fresh-volume initialization and production deployment have not
yet been verified. This Compose setup is intended for local development.