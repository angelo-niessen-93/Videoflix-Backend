# Docker: Umstieg auf die Akademie-Konfiguration

Der aktuelle Einstieg ist ausschließlich [docker-compose.yml](../docker-compose.yml)
im Repository-Root. Siehe [Quickstart](../README.md). Die früheren eigenen Dateien
`deploy/compose.yaml`, `deploy/Dockerfile` und `deploy/nginx.conf` wurden ersetzt.
Historische Berichte vom 4. November beschreiben noch diesen früheren Stand.

## Vorhandene Daten erhalten

Die neue `.env.template` verwendet `COMPOSE_PROJECT_NAME=videoflix-academy`.
Das alte Projekt `videoflix` und seine Volumes bleiben davon getrennt.
Die Volumenschlüssel `database`, `redis`, `media`, `private_media`, `static`,
`test_mail` sowie PostgreSQL 17 und dessen Datenpfad bleiben erhalten.
Es gibt kein automatisches Umbenennen, Kopieren oder Löschen bestehender Daten.
Ein leerer neuer Admin bedeutet deshalb nicht, dass alte Daten gelöscht wurden.

Wer vorhandene Daten übernehmen möchte, muss zuerst eine PostgreSQL-Sicherung
und eine Sicherung der Medien erstellen und prüfen. Danach beide alten Worker,
Web und Gateway geordnet stoppen. Die alte Compose-Datei ist im gesicherten
Git-Stand `df7010286bc370c0b9dad19b7dafea0211724653` verfügbar. Erst anschließend
`COMPOSE_PROJECT_NAME=videoflix` und die bisherigen DB-Zugangsdaten in `.env`
setzen und den neuen Root-Stack starten. Keine parallelen Schreiber auf dieselben
Datenvolumes starten. Die Migration wurde in dieser Aufgabe nicht an vorhandenen
Nutzerdaten ausgeführt; geprüft wurde ausschließlich die isolierte Neuinstallation.

Variablen umbenennen: `DJANGO_SECRET_KEY` → `SECRET_KEY`, `DJANGO_DEBUG` → `DEBUG`,
`DJANGO_ALLOWED_HOSTS` → `ALLOWED_HOSTS`, `POSTGRES_DB/USER/PASSWORD/HOST/PORT` →
`DB_NAME/USER/PASSWORD/HOST/PORT`. Bestehende Werte beibehalten. Die Anwendung
akzeptiert alte Namen weiterhin als Fallback. Bei gemeinsamem Vorkommen haben
Akademie-Namen Vorrang. Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` für Queues,
`REDIS_LOCATION` für den Cache; der alte `REDIS_URL` bleibt als Queue-Fallback.

`docker compose down` erhält Volumes. Weder `down -v` noch Volume-Pruning nutzen.
Passwörter bestehender Datenbanken werden durch Änderungen in `.env` nicht
geändert. Auch bestehende Superuser-Passwörter werden nicht automatisch ersetzt.
Admin-Anmeldung erfolgt wie bisher mit der E-Mail-Adresse.

Der frühere Gateway entfällt: WhiteNoise liefert Admin-CSS/JS, Django liefert
öffentliche Thumbnails. Originale und HLS bleiben ausschließlich im privaten
Speicher und werden weiterhin nur nach API-Authentifizierung ausgeliefert.

[Vergleich und aktuelle Prüfergebnisse](../DOCKER_VERIFICATION.md).
[Windows-Diagnose](WINDOWS_DOCKER_DIAGNOSIS.md).