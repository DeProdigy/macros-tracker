# API (Django)

The Django + DRF backend. Postgres runs in Docker; the Django app runs natively
(see [`plans/01-architecture.md`](../../plans/01-architecture.md)).

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — manages the Python version and dependencies
  (pinned in `.python-version` / `pyproject.toml`).
- **Docker Desktop running** — hosts the Postgres server. Check with `docker info`.

## Quickstart (from a clean clone)

```bash
# 1. Start Postgres (from the repo root — pins postgres:18, matches production)
docker compose up -d

# 2. Install dependencies into the project venv (Python 3.12)
cd apps/api
uv sync

# 3. Apply migrations to the Docker Postgres
uv run python manage.py migrate

# 4. Create an admin user (interactive: email + password)
uv run python manage.py createsuperuser

# 5. Run the dev server -> http://localhost:8000
uv run python manage.py runserver
```

`uv run <cmd>` executes inside the venv without activating it; run `source .venv/bin/activate`
first if you'd rather call `python`/`manage.py` directly.

## Settings

Split by environment under `config/settings/`, values via `django-environ`:

| Module          | When                          | Notes                                            |
| --------------- | ----------------------------- | ------------------------------------------------ |
| `base.py`       | shared                        | INSTALLED_APPS, DB, DRF defaults                 |
| `local.py`      | dev (default via `manage.py`) | `DEBUG=True`, console email, browsable API       |
| `production.py` | deploy (via `wsgi`/`asgi`)    | `DEBUG=False`, required secrets, HTTPS hardening |

Config comes from the environment. Copy the repo-root `.env.example` to `apps/api/.env`
and fill in values as needed — the `DATABASE_URL` default already matches the Docker
Compose Postgres, so `migrate` works out of the box with no `.env`.

## Common commands

```bash
uv run python manage.py makemigrations   # generate migrations from model changes
uv run python manage.py migrate          # apply them
uv run python manage.py createsuperuser  # create an admin
uv run python manage.py runserver        # dev server
uv run python manage.py shell            # Django shell
```

## Tests

Run from `apps/api`, with Docker Postgres running — tests use a separate,
rolled-back test database (pytest ≈ RSpec).

```bash
uv run pytest                                # run the whole suite
uv run pytest -v                             # verbose — list each test by name
uv run pytest accounts/tests/test_models.py  # a single file
uv run pytest accounts/tests/test_models.py::test_str_is_the_email  # a single test
uv run pytest -k superuser                   # only tests whose name matches "superuser"
uv run pytest -x                             # stop at the first failure
uv run pytest -s                             # show print() / stdout
uv run pytest --create-db                    # rebuild the test DB (default is --reuse-db)
```

`uv run <cmd>` runs inside the venv without activating it. After
`source .venv/bin/activate` you can drop the `uv run` prefix (`pytest`, `python …`).

## Lint & types

```bash
uv run ruff check .         # lint
uv run ruff check --fix .   # lint + autofix
uv run ruff format .        # format
uv run mypy                 # type-check
```

## Deployment (Railway)

Deployed to Railway: a Django service plus a managed Postgres 18, auto-deploying
on merge to `main`. See [`plans/09-deployment.md`](../../plans/09-deployment.md).

The service's **root directory is set to `apps/api`**. Without that, Railway's
builder sees the repo-root `package.json` and tries to build a Node app.

| File            | Role                                                                       |
| --------------- | -------------------------------------------------------------------------- |
| `Dockerfile`    | Build (`uv sync --locked --no-dev`, `collectstatic`) and the start command |
| `.dockerignore` | Keeps secrets, the local venv, and test files out of the image             |
| `railway.json`  | Builder, release command, health check path                                |

`railway.json` is JSON and cannot carry comments, so its choices are recorded here:

- **`builder: DOCKERFILE`** — auto-detection has to guess the Python package
  manager. This project uses `uv` with a committed lockfile that is only worth
  having if it is installed with `--locked`.
- **`preDeployCommand: migrate`** — migrations belong in the release command, not
  the start command. Start commands run on every container restart, so two
  replicas restarting would race each other on the migration table. A release
  command runs once, before the new deploy takes traffic.
- **no `startCommand`** — gunicorn is defined once, as the Dockerfile's `CMD`, so
  `docker run` locally behaves exactly like Railway. Setting it in both places
  invites drift. It also has to be shell-form: Railway injects `$PORT` but does
  not run the start command through a shell, so an exec-form gunicorn gets the
  literal string `$PORT` and exits with `'$PORT' is not a valid port number`.
- **`healthcheckPath: /api/health/`** — runs a real `SELECT 1`. `/api/ping/`
  deliberately touches no database, so it would report green while the app
  could not serve a single request.

### Environment variables

All values live in Railway, none in the repo. `.env.example` at the repo root is
the full list; the ones that must be set for a deploy to work at all:

| Variable                 | Value                                             |
| ------------------------ | ------------------------------------------------- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production`                      |
| `DJANGO_SECRET_KEY`      | Freshly generated, never the dev default          |
| `DJANGO_ALLOWED_HOSTS`   | The app domain **plus `healthcheck.railway.app`** |
| `DATABASE_URL`           | Injected automatically once Postgres is linked    |

Two failure modes worth knowing, because both look like an app bug and are not:

- Omitting `healthcheck.railway.app` from `ALLOWED_HOSTS` makes every health
  probe a 400, so the deploy never goes live.
- `SECURE_SSL_REDIRECT` would 301 those probes, since they arrive over plain
  HTTP on the internal network. `production.py` exempts the health path via
  `SECURE_REDIRECT_EXEMPT`.

### Verifying production settings

```bash
# Run the deployment checklist against production settings. The required vars
# have no fallbacks by design, so they must be supplied.
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
DJANGO_ALLOWED_HOSTS=example.com \
DJANGO_SECURE_HSTS_SECONDS=31536000 \
  uv run python manage.py check --deploy

railway logs      # live deploy logs — far easier than diagnosing after the fact
```

## Database

Postgres lives in the `pgdata` Docker volume and survives restarts.

```bash
docker compose up -d      # start
docker compose down       # stop (data kept)
docker compose down -v    # stop AND wipe the database — clean slate
```

Wiping and re-migrating is the fastest fix if the schema ever gets into a bad state.
