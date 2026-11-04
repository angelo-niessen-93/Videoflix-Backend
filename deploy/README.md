# Project-owned Docker setup

This directory is our own configuration, not Academy-supplied material.
The [official frontend README](https://github.com/Developer-Akademie-Backendkurs/project.Videoflix/blob/main/readme.md)
requires a Docker Django backend and explicitly says it is not included.
The complete official Git tree at `eec23e014aabefacb22c02dbf1532aa3857ddd75`
contains no Docker/Compose files. Its wording permits creating a backend;
whether a separate course rubric requires a particular supplied template
must be confirmed with the Academy if such a template exists elsewhere.
No official file has been changed.

**Runtime acceptance passed on 4 November 2026.** Docker Engine 29.9.2
and Compose v5.6.1 built and started the isolated stack successfully.
PostgreSQL migrations/persistence, Redis, both independent workers, local
worker email, FFmpeg/HLS and real Nginx/Gunicorn HTTP delivery passed.
See [the verification report](../VIDEOFLIX_DOD_REPORT.md) for evidence and
remaining submission limits. General Windows troubleshooting is in the
[diagnostic guide](WINDOWS_DOCKER_DIAGNOSIS.md), without local machine data.

## Local HTTP startup

Run from the backend root with a working Linux Docker engine:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Put your generated secret and a private POSTGRES_PASSWORD in .env first.
docker compose --env-file .env -f deploy/compose.yaml config --quiet
docker compose --env-file .env -f deploy/compose.yaml up --build --wait
docker compose --env-file .env -f deploy/compose.yaml ps --all
docker compose --env-file .env -f deploy/compose.yaml exec web python manage.py createsuperuser
```

Open `http://127.0.0.1:8000/admin/` and start the unchanged official frontend
on `http://127.0.0.1:5500`. Only the gateway port is published, on loopback.
Compose supplies internal database/Redis/storage values; application settings
in `.env` do not implicitly override the explicit Compose environment block.
Adjust that block deliberately for custom origins or a deployment environment.
The file is explicitly for local HTTP: Secure cookies and SSL redirect are
disabled there while Django DEBUG remains false. Production settings otherwise
keep HTTPS defaults. No production-readiness claim is made for this local stack.

The image includes FFmpeg/FFprobe and Gunicorn. A non-root application user
runs migrations, web and workers. PostgreSQL 17 and Redis 7.4 have independent
healthchecks and persistent volumes. Migration/collectstatic completion gates
web and both workers; web readiness gates the unprivileged Nginx gateway.
`worker-default` and `worker-video` are distinct processes with RQ schedulers
for delayed retries. Web and workers share public and private media volumes.
Nginx sees only public thumbnails and static assets; HLS/originals remain
private and playlists/segments go through Django authorization. Access logs
are disabled at gateway/Gunicorn to avoid recording action-token URLs.

Mail uses Django's **file-based backend**, never SMTP. Its private `test_mail`
volume contains token-bearing messages. It is not mounted into Nginx.
No real email is sent. Docker named volumes retain all application data on
ordinary shutdown. Stop this stack without deleting data:

```powershell
docker compose --env-file .env -f deploy/compose.yaml down
```

Do not use `down -v`, volume pruning or other destructive cleanup against
existing application data. No host database/Redis services are installed.

## Dedicated live infrastructure acceptance

Use a **new project name**, private generated credentials and a disposable
database ending in `_acceptance`. Never reuse a production environment or
production volumes. The following overrides `.env` through process variables
and uses its own project-scoped volumes. Existing application volumes remain
separate. Port 8000 must be free.

```powershell
$env:DJANGO_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(64))"
$env:POSTGRES_PASSWORD = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:POSTGRES_DB = 'videoflix_acceptance'
$env:POSTGRES_USER = 'videoflix_acceptance'
docker compose -p videoflix-release-acceptance -f deploy/compose.yaml up --build --wait
docker compose -p videoflix-release-acceptance -f deploy/compose.yaml ps --all
docker compose -p videoflix-release-acceptance -f deploy/compose.yaml exec web python manage.py shell -c "from scripts.verify_infrastructure import main; main()"
Invoke-WebRequest http://127.0.0.1:8000/api/csrf/
```

The script rejects SQLite, database names without the acceptance suffix and
every mail backend except file-based delivery before doing any writes. Naming
is a guard, not proof of isolation: the operator must provision the new stack.
It verifies PostgreSQL ORM persistence, real Redis PING and cache roundtrips,
registered workers for both queues, a worker-delivered local email and a real
admin upload of a generated 1080p video with audio. It waits for the separate
video worker to mark the video ready, checks the thumbnail and dashboard, then
fetches authenticated playlists/segments and decodes all three HLS variants.
The Django test client exercises the real views without starting an extra web
server; the explicit HTTP request verifies gateway reachability separately.
Full browser integration remains the separate Playwright suite in the root
README. The infrastructure script is outside application coverage; its live
run passed on 4 November 2026. Five automated tests verify its isolation
guards and worker failure/timeout behavior. All previous 122 tests remain;
the final expanded 129-test suite passed
without skips, with 97% application coverage. This includes two real frontend
flows, two email-layout tests, eleven FFmpeg tests and two loopback SMTP tests.

Synthetic records and media stay in the dedicated acceptance volumes for
inspection; the script does not delete them. Shut down without `-v` afterward.
Keep the generated credentials locally if retaining that stack; do not commit
them or expect a new password to replace one stored in an existing DB volume.
Clear the temporary `POSTGRES_*` and `DJANGO_SECRET_KEY` process variables in
this shell before returning to other environments.

## Remaining production and course acceptance

Builds, migrations, live PostgreSQL/Redis, separate workers and gateway
static/media delivery passed the isolated local acceptance.
Before hosting, configure TLS, Secure cookies, redirect/proxy trust, backups,
resource/upload limits, secrets and approved SMTP separately. Images use
version tags; rebuild intentionally for security updates. Public hosting is
not required for this Academy submission. No Academy
Docker originals were supplied in the inspected official source tree; the
existing project-owned configuration was left unchanged during acceptance.

## Retained acceptance stack

The completed acceptance uses project `videoflix-release-acceptance` and
private generated credentials in the ignored root file `.env.acceptance`.
Its six volumes contain only synthetic acceptance data and local test mail.
The stack remains running for inspection. Reuse these credentials when
inspecting it; do not generate replacement passwords for its existing DB.

```powershell
docker compose --env-file .env.acceptance -p videoflix-release-acceptance -f deploy/compose.yaml ps --all
# Stop the stack when finished; all volumes are retained:
docker compose --env-file .env.acceptance -p videoflix-release-acceptance -f deploy/compose.yaml stop
```

For a future fresh acceptance, first inspect existing project resources.
Do not overwrite this retained stack or delete its volumes. The browser test
suite needs port 8000: temporarily stop the acceptance gateway before running
it, then start the gateway again afterward. Workers have no Compose healthcheck;
verify their registrations and completed jobs as part of the live test.

## Verified restart and repeated acceptance

The existing six service containers were restarted without rebuilding images
or deleting volumes. Database-record and private/public-media/mail checksums
were identical before and after restart; all 35 migrations remained applied.
The live script and real gateway HTTP probes then passed again. Restarting
an isolated acceptance stack is distinct from resetting its database.

To repeat the live script on this retained synthetic environment:

```powershell
docker compose --env-file .env.acceptance -p videoflix-release-acceptance -f deploy/compose.yaml exec -T web python manage.py shell -c "from scripts.verify_infrastructure import main; main()"
```

Each run adds synthetic users, mail and media; it does not reset prior data.
The example fresh-stack commands earlier in this guide must not be used to
replace credentials of this already populated stack.
