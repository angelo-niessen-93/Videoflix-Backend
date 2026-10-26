# Videoflix backend

A separate Django REST API for email registration, account activation,
JWT cookie authentication, password recovery and protected HLS video streaming.
The backend implements the supplied contract and has been integrated with the
unchanged official Academy Vanilla JavaScript frontend in a separate sibling
directory. No Academy backend Docker files have been supplied.
See [VIDEOFLIX_DOD_REPORT.md](VIDEOFLIX_DOD_REPORT.md) for verified results and
remaining infrastructure acceptance work.

## Technology stack and features

- Python 3.12+ and Django 5.2 LTS; verified locally on Python 3.14.2.
- Django REST Framework, Simple JWT and its database-backed refresh blacklist.
- PostgreSQL as the normal application database; Redis for queues and cache.
- Django RQ workers for email, HLS conversion and thumbnail generation.
- FFmpeg/FFprobe with H.264, AAC and MPEG-TS video-on-demand playlists.
- Django admin for staff video uploads and processing status inspection.
- Signed, expiring, purpose-specific activation and reset tokens.
- HttpOnly cookies, CSRF enforcement, explicit CORS origins, private storage,
  password validation and case-insensitive database email uniqueness.
- Durable email records and video processing state for failure recovery.

The project contains `accounts/`, `videos/`, `config/`, email templates,
migrations and a logically separated `tests/` suite. Views handle HTTP,
serializers validate input, services implement business rules and tasks run
background work. `scripts/check_code_rules.py` enforces the physical 14-line
function limit and snake_case, allowing Django's required test method names.

## Requirements and local setup

Install Python, PostgreSQL, Redis and FFmpeg including FFprobe. FFmpeg must
include the `libx264` encoder. PostgreSQL and Redis run as independent services;
the application does not install or start them. On Windows, use a Linux/WSL
worker environment for the normal RQ worker and Redis.

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Put the generated value in `DJANGO_SECRET_KEY` inside your local `.env`, then
configure your database credentials. Keep `.env` private. The example values
are placeholders. Existing process environment variables take priority over
`.env`; no existing secrets are overwritten by the application.

On Linux/macOS activate with `source .venv/bin/activate`. For application-only
installation use `requirements.txt`; the dev file additionally installs Ruff,
Coverage and fakeredis. Gunicorn is installed on non-Windows systems.

## Environment variables

All supported variables appear in [.env.example](.env.example).

| Variable | Purpose / default |
|---|---|
| `DJANGO_SECRET_KEY` | Required private signing secret; no application default |
| `DJANGO_DEBUG` | `false` by default; example enables local development |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts; `localhost,127.0.0.1` |
| `POSTGRES_DB`, `POSTGRES_USER` | Database and role, both default to `videoflix` |
| `POSTGRES_PASSWORD` | Database password; supply your own |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Database host and port; `localhost`, `5432` |
| `REDIS_URL` | Redis database URL including connection/read timeouts |
| `FRONTEND_URL` | Frontend base URL; `http://127.0.0.1:5500` |
| `CORS_ALLOWED_ORIGINS` | Exact comma-separated frontend origins |
| `CSRF_TRUSTED_ORIGINS` | Exact comma-separated trusted frontend origins |
| `CSRF_TRUSTED_JSON_ORIGINS` | Exact origins permitted to use the restricted tokenless JSON flow; empty requires CSRF tokens |
| `ACTIVATION_PATH`, `PASSWORD_RESET_PATH` | Frontend routes; `/pages/auth/activate.html`, `/pages/auth/confirm_password.html` |
| `ACTIVATION_TIMEOUT`, `PASSWORD_RESET_TIMEOUT` | Token validity in seconds; `86400`, `3600` |
| `COOKIE_SECURE` | Defaults to true outside debug mode |
| `COOKIE_SAMESITE` | `Lax`; `None` requires Secure and HTTPS |
| `EMAIL_BACKEND` | Application default SMTP; example uses local console output |
| `EMAIL_HOST`, `EMAIL_PORT` | SMTP server and port; port defaults to `587` |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP credentials |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | STARTTLS defaults true; SSL defaults false |
| `DEFAULT_FROM_EMAIL` | Verified sender for your SMTP service |
| `FFMPEG_BINARY`, `FFPROBE_BINARY` | Executable names or absolute executable paths |
| `FFMPEG_TIMEOUT`, `FFMPEG_THREADS` | Per-conversion seconds and thread count; `1800`, `2` |
| `MEDIA_ROOT` | Public thumbnail storage; defaults to `media/` |
| `PRIVATE_MEDIA_ROOT` | Originals and HLS storage; defaults to `private_media/` |

Private media must be outside the public media root; startup rejects an unsafe
overlap. `MEDIA_URL` is `/media/`; only thumbnails belong there.

## PostgreSQL and database migrations

Provision a dedicated PostgreSQL database and role, configure the five
`POSTGRES_*` variables and start PostgreSQL before running:

```powershell
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The application has no normal SQLite fallback. Initial migrations create the
custom user, email job and video tables; Django and Simple JWT migrations create
the session/authentication/blacklist tables. Never replace a populated database
or delete migration history. Admin login accepts the superuser's email.

For a production process on Linux, run migrations and `collectstatic` during
deployment, then start `gunicorn config.wsgi:application`. Provide HTTPS and
configure your trusted reverse proxy for the deployment topology. This project
does not blindly trust forwarded headers.

## Redis configuration and Django RQ worker

Set `REDIS_URL` to a private Redis instance. The default URL sets a two-second
connection timeout and ten-second socket timeout. Redis must not be exposed as
a public unauthenticated service. The cache uses a short 30-second manifest TTL;
cache lookups occur after authorization, ready-status and path checks. Its key
contains file modification time. Redis cache errors are logged and fall back
to the private manifest file.

Use separate processes for web and workers:

```powershell
python manage.py rqworker default
python manage.py rqworker video
```

Run those worker commands in Linux/WSL for standard RQ process isolation. Both
workers need the same `.env`, database and storage as Django. The email queue
uses a 120-second timeout and three retries; the video queue uses 7200 seconds
and two retries. Failed RQ jobs are retained for seven days. FFmpeg subprocesses
have their own configurable timeout and never use a shell.

Jobs are scheduled through `transaction.on_commit`, so workers only receive
committed database records. Queue submission failures preserve the records with
a failed state and a non-sensitive error class. Once Redis is healthy:

```powershell
python manage.py retry_jobs
python manage.py retry_jobs --video-id 1
```

The command retries pending/failed email and video records. `--video-id` limits
the video selection; email recovery still runs. Sent emails and ready videos
are not resent/reconverted. Failed conversion retains original uploads and
reuses valid completed variants. An abrupt worker termination can leave a video
in `processing`; first verify its worker/job has stopped, then explicitly use:

```powershell
python manage.py retry_jobs --video-id 1 --recover-stopped
```

Email processing locks its durable record. Delivery is at least once: an SMTP
acceptance followed by process/database failure can cause a duplicate message.
This is not a guarantee of exactly-once delivery. An expired email link is
marked expired rather than delivered. For an expired activation, an operator
can issue a new activation through `schedule_email(user, "activation")` in a
Django shell; no public resend endpoint is part of the supplied contract.

Anonymous API requests are throttled using Redis. If Redis fails, the limiter
logs the outage and permits requests so account flows remain available; use an
edge rate limit in production when enforcement during Redis outages is needed.

## Email configuration

The `.env.example` console backend deliberately avoids SMTP. To enable actual
delivery after approval, select `django.core.mail.backends.smtp.EmailBackend`
and configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` and either STARTTLS or SSL, according
to the provider. Do not enable both TLS and SSL. SMTP calls time out after ten
seconds and execute exclusively in the email worker.

Messages contain plaintext and responsive HTML matching the official PNG design
references: white backgrounds, blue buttons, a centered activation logo and a
left-aligned reset footer logo. The official SVG and its email-compatible PNG
are in `templates/emails/assets/`; the PNG is attached inline with a Content-ID.
Table layouts, inline styles and an Outlook VML button provide broad email
compatibility. Actual Gmail/Outlook delivery and rendering remain untested. Links use:

```text
FRONTEND_URL/pages/auth/activate.html?uid=<uidb64>&token=<activation-token>
FRONTEND_URL/pages/auth/confirm_password.html?uid=<uidb64>&token=<reset-token>
```

The route paths and `uid`/`token` query names were verified against the official
frontend and exercised through the actual browser activation/reset pages. Tests always use
Django's in-memory mail backend and never send real email. Console email output
contains live links during manual development; do not retain it in public logs.

## API endpoints

All routes are relative to `http://127.0.0.1:8000`, the official client's
configured backend origin. State-changing requests require the CSRF protections
described below. No additional JSON fields are required.

| Method | Endpoint | Successful result |
|---|---|---|
| GET | `/api/csrf/` | 200, `{ "csrfToken": "..." }` and CSRF cookie |
| POST | `/api/register/` | 201, `{ "user": { "id", "email" }, "token" }` |
| GET | `/api/activate/<uidb64>/<token>/` | 200, account activation message |
| POST | `/api/login/` | 200, login detail, user ID/username, HttpOnly JWT cookies |
| POST | `/api/logout/` | 200, logout detail, cookie deletion and refresh blacklist |
| POST | `/api/token/refresh/` | 200, `{ "detail": "Token refreshed", "access": "..." }` |
| POST | `/api/password_reset/` | 200, generic reset email response |
| POST | `/api/password_confirm/<uidb64>/<token>/` | 200, password reset detail |
| GET | `/api/video/` | 200, metadata array ordered by creation date descending |
| GET | `/api/video/<movie_id>/<resolution>/index.m3u8` | 200, protected manifest |
| GET | `/api/video/<movie_id>/<resolution>/<segment>/` | 200, protected MPEG-TS segment |

The required JSON bodies are:

```json
{"email":"user@example.com","password":"A-long-secret!74","confirmed_password":"A-long-secret!74"}
```

```json
{"email":"user@example.com","password":"A-long-secret!74"}
```

```json
{"email":"user@example.com"}
```

```json
{"new_password":"Another-strong-secret!93","confirm_password":"Another-strong-secret!93"}
```

Those examples correspond to registration, login, reset request and reset
confirmation. Passwords must satisfy Django's validators and have at least eight
characters. Registration creates an inactive account. Its returned token is
usable only for activation and never authenticates protected endpoints.
Activation expires in 24 hours by default; reset expires in one hour. Changing
the relevant account state invalidates used links. Email uniqueness is enforced
case-insensitively in the database. Login works by email even if a staff member
created a different internal username.

Validation and duplicate-registration errors return 400. Invalid login returns
the same generic 400 for absent, inactive and incorrect-password accounts.
Password reset returns the same 200 payload whether or not an eligible account
exists. Invalid, expired or reused action links return 400.

Missing refresh cookies return 400, invalid/expired/blacklisted refresh tokens
return 401. JWT-authenticated resources return 401 without a valid access
cookie. Missing videos, unavailable resolutions, files or invalid paths return
404. Failed CSRF checks return 403. Rate limits can return 429.

## Authentication, cookies, CORS and CSRF

`access_token` and `refresh_token` are HttpOnly and scoped to `/api/` to cover
both refresh and logout. Their lifetimes are 30 minutes and seven days. Use
`COOKIE_SECURE=true` for HTTPS production and `COOKIE_SAMESITE=None` only when
the deployment truly needs cookies across sites. Browsers may still block
third-party cookies; same-site deployment is preferable when possible.

Every frontend request that needs cookies, including HLS player requests, must
use credentials. The official client sends JSON and credentials but no CSRF
token. It is supported by the restricted origin policy below. Clients using
Django CSRF tokens can continue to follow this flow:

1. GET `/api/csrf/` with credentials and retain its JSON `csrfToken`.
2. POST login/register/reset with credentials and the `X-CSRFToken` header.
3. Login rotates the CSRF cookie. GET `/api/csrf/` again for subsequent POSTs.
4. GET video metadata, manifests and segments with credentials.
5. Refresh/logout with credentials and the current CSRF token.

The JSON bootstrap allows a frontend on a different origin to obtain a CSRF
token without reading the backend's cookie directly. Configure exact trusted
origins; wildcard credentialed CORS is not used.

For the unmodified Academy frontend, tokenless unsafe requests are accepted
only when all these conditions hold:

- `Origin` exactly matches `CSRF_TRUSTED_JSON_ORIGINS`, `CSRF_TRUSTED_ORIGINS`
  and `CORS_ALLOWED_ORIGINS`.
- Content-Type is `application/json`, requiring browser CORS preflight across
  origins. Form, multipart and text/plain submissions do not qualify.
- Fetch mode is `cors` if the browser supplies `Sec-Fetch-Mode`.
- No explicit CSRF header is supplied; an invalid supplied token is rejected
  using Django's normal protection.

Missing/null/untrusted Origin, other ports, other hostnames, navigation requests
and simple form submissions still require a valid Django CSRF token. There is
no general CSRF exemption. Set `CSRF_TRUSTED_JSON_ORIGINS=` to require Django
CSRF tokens for all unsafe requests. Origin verification is a browser CSRF
defense, not authentication for non-browser clients; protected resources still
require valid JWTs. This design follows the restrictions described in the
[OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

The installed VS Code Live Server extension uses `127.0.0.1:5500` with no user
port/host override. Both browser flows used that actual origin. Open the
frontend using `http://127.0.0.1:5500`; `localhost:5500` is a different host from
the client's hardcoded `127.0.0.1:8000` backend and is not silently allowed.
Access tokens last 30 minutes, exceeding the frontend's 20-minute refresh
interval. Refresh timing was exercised with Playwright's virtual browser clock.

Logout blacklists the refresh token and clears browser cookies. An already
copied access token remains valid until its short expiry, as with ordinary
stateless JWT logout. Password changes revoke both prior access and refresh
tokens through the stored password-state claim. Tokens in Authorization headers
or refresh request bodies are not used as substitutes for the specified cookies.

## Video upload, FFmpeg installation and HLS processing

Check the media tools before starting a worker:

```powershell
ffmpeg -version
ffprobe -version
ffmpeg -encoders
```

Install your platform's FFmpeg package or binary distribution, ensure both
executables are in PATH and verify `libx264` is listed. Alternatively provide
absolute executable paths in `.env`. The worker account needs write access to
public thumbnail and private video storage, and read access to uploaded sources.

Upload a video in `/admin/` as staff. Supply title, description, category and a
supported MP4/MOV/MKV/WebM source. Saving stores the original privately and
schedules processing after database commit. There is no public upload endpoint
in the supplied API contract. Admin source replacement is read-only after
creation: upload a new video record for a different source.

FFprobe determines source dimensions. A worker creates all supported heights
up to the source height: 480p, 720p and 1080p, preserving display aspect ratio,
using even widths and square pixels. Sources below 480 pixels high fail with a
recorded status rather than being upscaled. A missing audio stream is allowed.
HLS uses six-second target segments, closed GOPs, periodic keyframes and VOD
playlists. Segment durations depend on keyframe placement and source duration.

```text
private_media/
  uploads/<random-id>.mp4
  videos/<video-id>/
    480p/index.m3u8
    480p/000.ts
    720p/index.m3u8
    720p/000.ts
    1080p/index.m3u8
    1080p/000.ts
    thumbnail.jpg
media/
  thumbnails/<video-id>.jpg
```

Available files depend on source height. Every variant is checked for a finished
playlist, safe local segment references, existing segments and expected H.264
dimensions. The generated thumbnail is verified before publishing. Only ready
videos with a thumbnail and resolution metadata appear in the unpaginated list.
Its fields are `id`, `created_at`, `title`, `description`, `thumbnail_url` and
`category`. The frontend performs genre grouping and hero selection.

The manifest response uses `application/vnd.apple.mpegurl`; segment responses
use `video/MP2T`. The API adds trailing slashes to segment references to match
the specified segment route. It accepts only the known resolutions and numeric
`.ts` names, checks resolved path containment and sends private/no-store headers.
Do not configure a web server, CDN or storage bucket to publicly serve
`private_media/`. Serve only `media/` as public media, plus collected static
assets. Debug Django routing also exposes only the public media root.

## Docker setup

There is no supplied Dockerfile, Compose file or Docker configuration in this
workspace. None has been created or modified. Therefore no project-specific
Compose service names or launch commands can be documented honestly. Docker
CLI was present during verification, but Docker Desktop's Linux engine pipe
was unavailable. Container startup was not verified. WSL reports that WSL 2 cannot start and no
distributions are installed. Its virtualization diagnostic conflicts with CIM
reporting firmware virtualization and a hypervisor present; the Windows feature
states could not be queried without administrator rights. The precise missing
Windows component cannot be established from this user context.

When the Academy files are supplied, keep them unchanged and inspect their
actual service names, environment mapping, PostgreSQL/Redis connectivity,
shared media mounts, worker commands and FFmpeg installation before starting.
Any web and video worker services must share private and public media storage.
Do not treat the local tests as evidence that a missing container setup works.

## Running tests and quality checks

The default test profile uses an isolated in-memory SQLite database, local
memory cache, in-memory email backend and temporary media folders. It never
uses production DB data, Redis or SMTP. SQLite is limited to this test profile.
RQ integration uses the real Queue/SimpleWorker with fakeredis and a portable
timeout implementation; this does not verify a separate production worker.

```powershell
python manage.py test tests --settings=config.test_settings --noinput --exclude-tag=browser
python manage.py test tests --settings=config.test_settings --exclude-tag=ffmpeg --exclude-tag=browser
python manage.py test tests --settings=config.test_settings --tag=ffmpeg
python -m coverage run --source=accounts,videos,config manage.py test tests --settings=config.test_settings --noinput --exclude-tag=browser
python -m coverage report -m
python -m ruff check .
python -m ruff format --check .
python scripts/check_code_rules.py
python manage.py check --settings=config.test_settings
python manage.py check --deploy --settings=config.deploy_check_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
```

FFmpeg tests generate a short 1080p video with audio, produce all three variants,
inspect the codecs, decode playlists, fetch segment references via the API,
check failure handling and verify variant reuse. They skip explicitly only if
FFmpeg/FFprobe are unavailable. All nine ran successfully in the recorded run.

To verify the same suite against PostgreSQL, use a dedicated non-production
database configuration and a role allowed to create its `test_` database:

```powershell
python manage.py test tests --settings=config.postgres_test_settings --noinput
```

Django creates and destroys only the test database. Do not point these commands
at production infrastructure. Real Redis queue/worker and SMTP acceptance are
separate operational checks; they have not been run on this machine.

## Official frontend and real browser integration

The official repository is cloned separately at `../Videoflix-Frontend`:
[Academy frontend](https://github.com/Developer-Akademie-Backendkurs/project.Videoflix),
verified commit `eec23e014aabefacb22c02dbf1532aa3857ddd75`. Its tracked files are
unchanged. The backend contains no frontend application files; the official
logo is used only as an explicitly requested backend email asset.

Eight application JavaScript files, nine HTML pages and generated JSDoc were
inspected. JSDoc source pages still mention CSRF headers that are absent from
the actual shipped request helpers; execution follows the actual JavaScript.
See `VIDEOFLIX_DOD_REPORT.md` for the request mapping and identified UI defects.

Optional browser prerequisites are the cloned frontend, Node.js, the installed
VS Code Live Server extension and an installed Microsoft Edge browser. Install
only test dependencies in the backend environment:

```powershell
python -m pip install -r requirements-browser.txt
$env:VIDEOFLIX_BROWSER_TESTS='1'
python manage.py test tests.test_browser_integration --settings=config.test_settings --noinput
python -m coverage run --source=accounts,videos,config manage.py test tests --settings=config.test_settings --noinput
python -m coverage report -m
```

The browser suite starts the existing Live Server module on `127.0.0.1:5500`
and Django's isolated live test server on `127.0.0.1:8000`. Both ports must be
free. It uses Playwright with `channel=msedge`; override `PLAYWRIGHT_CHANNEL`
when needed. `VIDEOFLIX_FRONTEND_DIR` can select another unchanged checkout.
The current harness locates Live Server at its installed extension version
`ritwickdey.liveserver-5.7.10`. It does not write to the frontend checkout.

Browser requests, CORS, cookies, actual HLS.js 1.6.7 from the official CDN, decoded
480p/720p/1080p playback, virtual-time refresh and logout are exercised. The reset
flow verifies that old credentials fail and new credentials succeed. Mail jobs
use fakeredis and execute their real tasks against the test email backend;
this is not a separate Redis worker or actual SMTP delivery. ORM helpers run on
an isolated test thread to coexist with Playwright's event loop. No response
interception, fake HLS responses, security-disabling browser flags or frontend
script modifications are used.

The default suite skips the two optional browser tests unless
`VIDEOFLIX_BROWSER_TESTS=1`; `--exclude-tag=browser` excludes them cleanly. The
recorded full acceptance run enabled them. Evidence is written under the
ignored `test-results/browser/` directory, with sensitive token paths redacted.
Email previews at desktop/mobile sizes are under `test-results/email-previews/`.

Known official frontend issue: reset-password blur validation references
`confirmed_password`, while the page defines `repeated_password`. The browser
records an uncaught null-reference error; submission and both login checks
still succeed. This is documented without changing the official client.
The frontend is therefore rated PARTIAL for complete polish, with both required
integration workflows verified.

## Troubleshooting

| Symptom | Check |
|---|---|
| Missing `DJANGO_SECRET_KEY` | Configure `.env` or process environment; no insecure runtime fallback exists |
| Database connection refused | PostgreSQL service, host, port, credentials and database provisioning |
| HTTP redirects to HTTPS locally | Use `DJANGO_DEBUG=true` locally; production requires HTTPS |
| Login returns 403 | Check exact frontend Origin/JSON policy, or bootstrap CSRF and send a valid header |
| Cookies absent on later requests | Secure/SameSite policy, browser credentials, frontend/backend site topology |
| Token refresh returns 401 | Expiry, blacklist, account activation state or changed password |
| Reset response but no email | Response is deliberately generic; check eligibility, worker and `EmailJob` status |
| Video absent from list | Inspect status/error in admin; both ready variants and a thumbnail are required |
| Conversion fails | FFmpeg/FFprobe PATH, source validity, height, writable storage, timeout and disk space |
| Processing stuck after worker death | Confirm job is stopped, then use explicit `--recover-stopped` recovery |
| Redis unavailable | Restore service; durable jobs remain recoverable using `retry_jobs` |
| Manifest works but player cannot fetch segments | Player credentials, segment URL trailing slash, resolution and private storage mount |
| Production thumbnail 404 | Configure the web server to serve only public `MEDIA_ROOT` at `/media/` |
| Docker cannot connect | Start/configure the Docker engine; the missing Academy setup still needs supplying |

Application HTTP logs redact activation/reset token paths. Configure equivalent
redaction or omission in reverse proxy access logs because these links contain
sensitive values. Do not log cookies, SMTP credentials or request passwords.

## Technical references

Implementation was checked against official sources:
[Django signing](https://docs.djangoproject.com/en/5.2/topics/signing/),
[DRF authentication and CSRF](https://www.django-rest-framework.org/api-guide/authentication/),
[Simple JWT blacklist](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/blacklist_app.html),
[Django RQ](https://github.com/rq/django-rq), and
[FFmpeg HLS muxer](https://ffmpeg.org/ffmpeg-formats.html#hls).

## Git history and GitHub preparation

The repository starts on `main`. The initial commits group the existing project
snapshot into application implementation, automated tests and documentation.
They describe the imported project state, not a reconstructed development
chronology. Shared authentication, email, video and queue code is kept together
so partial application snapshots do not break cross-module imports.

Local environments, credentials, databases, uploads, generated HLS media,
caches, coverage and test evidence are excluded by `.gitignore`.
`.env.example` contains placeholders; fixed passwords and signing keys in the
isolated test configuration are synthetic test fixtures, not account secrets.

No GitHub repository was created and no push was performed. Once you have
created or selected an authorized, preferably empty GitHub repository, connect
it using your actual URL:

```bash
git remote add origin <REPOSITORY_URL>
git remote -v
git status
git push -u origin main
```

The final command is documented for your later use and has not been executed.
If the remote already contains commits, fetch and inspect its history before
integrating; do not force-push over existing work. Repository visibility must
also respect the usage restrictions of the supplied Academy assets.
