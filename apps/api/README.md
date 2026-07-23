# API (Django)

The Django + DRF backend. Postgres runs in Docker; the Django app runs natively
(see [`plans/01-architecture.md`](../../plans/01-architecture.md)).

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — manages the Python version and dependencies
  (pinned in `.python-version` / `pyproject.toml`).
- **Docker Desktop running** — hosts the Postgres server. Check with `docker info`.

## Quickstart (from a clean clone)

```bash
# 1. Start Postgres (from the repo root — pins postgres:16, matches production)
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

## Database

Postgres lives in the `pgdata` Docker volume and survives restarts.

```bash
docker compose up -d      # start
docker compose down       # stop (data kept)
docker compose down -v    # stop AND wipe the database — clean slate
```

Wiping and re-migrating is the fastest fix if the schema ever gets into a bad state.
