# Docker deployment and existing data

Use the root [docker-compose.yml](../docker-compose.yml) and
[English quickstart](../README.md). Earlier `deploy/compose.yaml`, Dockerfile and
Nginx files were replaced. Reports dated 4 November describe the earlier stack.

## Preserve existing data

The Docker template uses `COMPOSE_PROJECT_NAME=videoflix-academy`, separate from
the previous project named `videoflix`. Existing volume keys `database`, `redis`,
`media`, `private_media`, `static` and `test_mail`, PostgreSQL 17 and its data path
remain unchanged. Starting a new empty project does not delete the old data.

Before adopting existing volumes, create and verify database and media backups.
Stop the old web, gateway and both workers in an orderly manner. The old Compose
file is available at Git revision `df7010286bc370c0b9dad19b7dafea0211724653`.
Then set `COMPOSE_PROJECT_NAME=videoflix` and retain the existing database
credentials before starting the root stack. Never run parallel writers against
those volumes. Existing user data has not been migrated during this quality pass.

Environment aliases remain supported: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` and
`DJANGO_ALLOWED_HOSTS` map to `SECRET_KEY`, `DEBUG` and `ALLOWED_HOSTS`.
`POSTGRES_DB/USER/PASSWORD/HOST/PORT` map to `DB_NAME/USER/PASSWORD/HOST/PORT`.
The newer names take precedence. For queues use `REDIS_HOST`, `REDIS_PORT` and
`REDIS_DB`; the legacy `REDIS_URL` remains a fallback. `REDIS_LOCATION` configures
the cache. Preserve existing values when changing variable names.

`docker compose down` retains volumes. Avoid `down -v` and volume pruning.
Changing `.env` does not reset existing PostgreSQL or superuser passwords.
Admin login uses the email address. The current migration changes video field
labels only; the normal entrypoint applies migrations before starting the web.

WhiteNoise serves collected admin assets; Django serves public thumbnails.
Originals and HLS stay private and require API authentication. Thumbnail changes
preserve source and HLS files. If adding a static media proxy, forward missing
thumbnail requests to Django so its recovery endpoint can regenerate images.

See [Docker verification](../DOCKER_VERIFICATION.md), the
[current quality report](../VIDEOFLIX_DOD_REPORT.md), and
[Windows engine diagnosis](WINDOWS_DOCKER_DIAGNOSIS.md).
