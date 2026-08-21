# Production image for the Django API.
#
# A Dockerfile rather than letting Railway's builder auto-detect: detection has
# to guess the Python package manager, and this project uses uv with a committed
# lockfile that must be installed with --locked to be worth having. Being
# explicit also puts collectstatic in the build, where a missing asset fails the
# deploy instead of surfacing as a 500 on the first admin page load.
#
# Railway's service root is set to apps/api, so the build context is this
# directory and paths below are relative to it.

# uv's own image ships the binary on top of a slim Debian Python. The Python
# minor is pinned to match CI's PYTHON_VERSION and pyproject's requires-python.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# - PYTHONDONTWRITEBYTECODE: .pyc files are dead weight in a layer that is never
#   written to again.
# - PYTHONUNBUFFERED: without it Python blocks stdout, and Railway's log stream
#   shows nothing until a buffer fills — which is exactly when you need to see
#   the traceback that killed the boot.
# - UV_COMPILE_BYTECODE trades build time for faster cold starts; UV_LINK_MODE
#   silences uv's hardlink warning when cache and target sit on different mounts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies are installed before the source is copied so that editing a view
# does not invalidate the install layer. Only the two files that actually
# determine the dependency set are copied at this stage.
COPY pyproject.toml uv.lock ./

# --locked fails if uv.lock disagrees with pyproject rather than silently
# resolving something new — the deployed dependency set is then exactly the one
# CI tested. --no-dev omits pytest/mypy/ruff; --no-install-project installs only
# the dependencies, since the project source has not been copied yet.
RUN uv sync --locked --no-dev --no-install-project

COPY . .

RUN uv sync --locked --no-dev

# Use the venv directly, so `python`/`gunicorn` resolve without `uv run`.
ENV PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.production

# collectstatic has to import production settings, which by design require
# DJANGO_SECRET_KEY and DJANGO_ALLOWED_HOSTS rather than falling back to
# defaults. Neither real value exists at build time, and neither affects the
# output — collecting static files reads no secret and serves no request. These
# throwaway values exist only for the length of this RUN: they are scoped to the
# command, never written into the image's environment, and the real values come
# from Railway at runtime.
#
# --noinput because there is no TTY to answer the overwrite prompt.
RUN DJANGO_SECRET_KEY="build-time-only-not-a-real-secret" \
    DJANGO_ALLOWED_HOSTS="localhost" \
    python manage.py collectstatic --noinput

# Documentation only — Railway injects $PORT and routes to it regardless.
EXPOSE 8000

# The single definition of how the app is served: railway.json deliberately sets
# no startCommand, so `docker run` locally does exactly what Railway does and
# the two cannot drift.
#
# The `sh -c` wrapper is load-bearing. Railway injects $PORT but does not run
# the start command through a shell, so an exec-form gunicorn would receive the
# literal string "$PORT" and exit with "'$PORT' is not a valid port number".
# The ${PORT:-8000} default is what makes the same image runnable locally.
#
# - --workers 2: gunicorn is a pre-fork server, so a single worker serializes
#   every request; two is the floor at which a slow request cannot block the
#   health check and take down an otherwise fine instance.
# - --forwarded-allow-ips '*': makes gunicorn trust X-Forwarded-* from Railway's
#   proxy, which production.py's SECURE_PROXY_SSL_HEADER depends on to tell
#   HTTPS from HTTP. Safe only because nothing but that proxy can reach the
#   container.
# - --access-logfile/--error-logfile -: gunicorn logs to files by default, which
#   in a container means logs that exist nowhere anyone can read them.
# - --access-logformat: gunicorn's default omits X-Forwarded-For, and %(h)s is
#   REMOTE_ADDR, which behind Railway is always the proxy. MAC-36 needs the
#   forwarded chain to count the appending hops in front of this container. The
#   count cannot be assumed — too low lands every caller on a shared proxy
#   address and locks the world out, too high reads the forged end of the chain
#   and leaves the bypass open. TEMPORARY: removed in the same ticket once the
#   count is recorded.
#
#   This is gunicorn's default format with one field appended, rather than a
#   format of its own, so nothing already in the access log is lost while it is
#   live. The value is quoted because a forwarded chain contains commas and
#   spaces and would otherwise spill across what look like separate fields. An
#   absent header logs as "-".
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60 --access-logfile - --error-logfile - --access-logformat '%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\" xff=\"%({x-forwarded-for}i)s\"' --forwarded-allow-ips '*'"]
