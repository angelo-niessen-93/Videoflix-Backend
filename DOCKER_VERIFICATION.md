# Mentor follow-up: 10 November 2026

A separate stack `videoflix-mentor-20261110` passed Compose validation, image
builds, healthy startup, real PostgreSQL/Redis and independent RQ acceptance,
custom-thumbnail byte preservation, concurrent admin/worker row locking, real
HTTP admin/static assets/API/HLS and account/media persistence across container
recreation. The existing `videoflix` project was not reconfigured. The temporary
stack was stopped with `down`; its volumes were retained. See the
[current DoD report](VIDEOFLIX_DOD_REPORT.md) for commands and evidence.

The sections below document the earlier Docker setup review.

---

# Docker-Korrektur und Abnahme – 9. November 2026

Die Bereitstellung verwendet jetzt die Akademie-Dateinamen im Repository-Root,
eine zentrale `.env` und die normalen `docker compose`-Befehle. Die bestehende
Anwendung, ihre Migrationen und alle 129 vorhandenen Tests sind unverändert.
Die vollständige Testsuite einschließlich Browserprüfungen besteht mit
**129/129 Tests, ohne Skips, 97 % Coverage** (777 Statements, 26 nicht ausgeführt).
Die separate Live-Abnahme mit PostgreSQL, Redis und echten RQ-Workern besteht.

## Referenz und vollständiger Dateivergleich

Maßgebliche Quelle:
[Developer-Akademie-Backendkurs/material.videoflix-docker-files](https://github.com/Developer-Akademie-Backendkurs/material.videoflix-docker-files/tree/4796b17de2b7656d62b6904d4d04e5b74cbc41c6).
Der rekursiv abgefragte Git-Baum enthält genau sechs Dateien, keine Unterordner.
Alle sechs Dateien wurden vollständig gelesen; der geprüfte Stand ist
`4796b17de2b7656d62b6904d4d04e5b74cbc41c6`.

| Offizielle Datei | Vorlage | Bisheriger Projektstand | Umsetzung |
|---|---|---|---|
| `backend.Dockerfile` | Python 3.12 Alpine, `/app`, PostgreSQL-Client, FFmpeg, requirements, ausführbarer Entrypoint | Debian-Image unter `deploy/`, kein Entrypoint | Offizielle Alpine-Grundlage, Pakete und Entrypoint übernommen; LF-Normalisierung ergänzt |
| `backend.entrypoint.sh` | PostgreSQL abwarten, collectstatic, makemigrations, migrate, Superuser, Hintergrundworker, Gunicorn | Separater Migrationsdienst; Superuser nur manuell | Offizielle Startfolge mit versionierten Migrationen und automatischem Superuser; bestehende zwei Worker bleiben getrennte Prozesse |
| `docker-compose.yml` | Root; `db`, `redis`, `web`; `env_file: .env`; persistente Volumes; Port 8000 | Nur mit `-f deploy/compose.yaml`; sieben Dienste; harte Origin-/Mailwerte | Root-Datei, gleiche drei Kerndienste plus zwei vorhandene Worker; alle Anwendungseinstellungen aus `.env`; fünf Dienste |
| `.env.template` | Superuser, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_*`, `REDIS_*`, `EMAIL_*` | `.env.example` mit anderen Namen; Compose überschreibt SMTP | Sämtliche offiziellen Namen erhalten; vorhandene Videoflix-Optionen ergänzt; ausschließlich Platzhalter |
| `.dockerignore` | Ausschlussliste unter anderem für `.git`, `.env`, virtuelle Umgebungen | Strenge Positivliste | Positivliste zum Schutz vorhandener Secrets/Medien erhalten; Root-Dockerdateien und containerbasierte Testwerkzeuge ergänzt |
| `README.md` | Einrichtung, Root-Start, Variablennamen, automatischer Superuser, LF-Hinweis | Einstieg mit lokaler Python-Installation und separatem deploy-Setup; falsche Aussage, es gebe keine Vorlagen | Docker-Quickstart ganz oben; Container-Tests und sichere Datenübernahme dokumentiert; frühere Berichte als historisch eingeordnet |

Die Vorlage enthält keinen separaten Frontend-Dienst. Das offizielle Frontend
bleibt in seinem eigenen Repository unverändert. Sein geprüfter Stand ist
`eec23e014aabefacb22c02dbf1532aa3857ddd75`.

## Technisch notwendige Abweichungen

1. **Projektmodul `config` statt `core`.** Gunicorn startet die vorhandene
   `config.wsgi:application`. Die Anwendung wird nicht umbenannt.
2. **Zwei bestehende Worker statt eines Shell-Hintergrundprozesses.**
   `worker-default` und `worker-video` bedienen `default` und `video`, jeweils
   mit Scheduler für bestehende Wiederholungen. Der Entrypoint führt übergebene
   Befehle unmittelbar mit `exec` aus. Nur Web migriert und erstellt den Admin;
   Worker starten nach dessen erfolgreichem Healthcheck. Dadurch gibt es keine
   konkurrierenden Migrationen oder unüberwachten Worker im Webcontainer.
3. **Kein `makemigrations` beim Start.** Vorhandene versionierte Migrationen
   werden mit `migrate --noinput` angewendet. Automatisch erzeugte Änderungen an
   der Anwendungsstruktur beim Start wären für vorhandene Daten unzuverlässig.
4. **Bestehende PostgreSQL-Version und Volumenschlüssel bleiben erhalten.**
   PostgreSQL `17-bookworm` mit `/var/lib/postgresql/data` ersetzt das bewegliche
   `latest` und dessen anderen Mountpfad. Redis bleibt `7.4-bookworm` und nutzt
   AOF. `database`, `redis`, `media`, `private_media`, `static`, `test_mail`
   behalten ihre bisherigen Schlüssel; `private_media` schützt Originale/HLS,
   `test_mail` unterstützt die vorhandene Offline-Abnahme. Es findet kein
   automatisches Daten- oder Volume-Upgrade statt.
5. **Keine festen Containernamen und kein Quellcode-Bind-Mount.**
   Projektnamen trennen Installationen und schützen die vorhandene Umgebung.
   Der Code liegt vollständig im Image; Host-Pfade, Windows-Ausführungsrechte
   oder ein Bind-Mount können den Entrypoint nicht überdecken. `.gitattributes`
   erzwingt LF; der Build normalisiert vorhandene CRLF zusätzlich.
6. **WhiteNoise gemäß offizieller README, mit aktueller Django-Konfiguration.**
   `STORAGES` verwendet `CompressedManifestStaticFilesStorage`, da das alte
   `STATICFILES_STORAGE` nicht die aktuelle Django-5.2-Konfiguration ist.
   Admin-CSS/JS benötigt keinen Nginx-Dienst. Der bisherige Gateway entfällt.
   Öffentliche Thumbnails werden durch Djangos pfadgeprüfte Datei-View bedient,
   auch bei `DEBUG=False`. Sie ist ausschließlich auf `MEDIA_ROOT` beschränkt;
   HLS und Originale bleiben im separaten privaten Speicher und hinter den
   vorhandenen API-Berechtigungen. Diese einfache Auslieferung ist für den
   lokalen Akademie-Betrieb geprüft, nicht für ein Lastprofil großer Installationen.
7. **Videoflix-Einstellungen zusätzlich in `.env.template`.** Origins,
   Cookie-/HTTP-Optionen, Frontend-Routen, FFmpeg, Speicher und ein eigener
   Compose-Projektname erhalten vorhandene Funktionen. SMTP ist standardmäßig
   aktiv; der Datei-Mailbackend ist eine ausdrücklich auswählbare Offline-Option.
   Die alten Variablennamen bleiben Anwendungs-Fallbacks; offizielle Namen
   haben Vorrang. `REDIS_LOCATION` steuert den Cache, Host/Port/DB die Queues.
8. **Superuser-Kollisionen werden nicht stillschweigend übergangen.**
   Der offizielle Erstellungsansatz bleibt erhalten. Ein bestehender Superuser
   wird weder neu angelegt noch dessen Passwort überschrieben. Kollisionen mit
   regulären Konten führen zu einer eindeutigen Fehlermeldung. Die bestehende
   Anmeldung mit E-Mail-Adresse bleibt erhalten.

Die bisherigen drei Deployment-Dateien unter `deploy/` wurden durch den einen
Root-Einstieg ersetzt. [deploy/README.md](deploy/README.md) dokumentiert die
Datenübernahme und den alten gesicherten Git-Stand. Es wurden keine Accounts-,
Video-, Authentifizierungs-, Mail-, FFmpeg- oder Queue-Funktionen entfernt.

## Sicherung und Isolation

Vor der ersten Änderung war der Git-Arbeitsbaum sauber, HEAD:
`df7010286bc370c0b9dad19b7dafea0211724653`. Vollständige Historie und versionierte
Dateien wurden gesichert; `git bundle verify` bestätigte die Sicherung:

```text
C:/Users/MCFLY/AppData/Local/Temp/videoflix-before-docker-20261109-085647/
  repository.bundle
  worktree.zip
  status.txt
```

Die Neuinstallation erfolgte in einer separaten Dateikopie unter
`test-results/academy-clean-install/`, mit eigener privater `.env`, zufällig
generierten Passwörtern, `COMPOSE_PROJECT_NAME=videoflix-clean-20261109`,
`DB_NAME=videoflix_clean_acceptance` und Host-Port `18081`.
Vor dem Erststart existierte keines der sechs zugehörigen Volumes. PostgreSQL
initialisierte eine neue Datenbank. Die normalen Befehle wurden direkt in
diesem Verzeichnis ohne `-f`, `--env-file` oder `-p` ausgeführt.

Das simuliert eine datenfreie Neuinstallation auf dem vorhandenen Docker-Host;
es ist keine frisch installierte VM. Vorhandene PostgreSQL-/Redis-Images konnten
wiederverwendet werden, die Anwendung wurde neu gebaut. Die bisherigen
Anwendungsvolumes wurden niemals in den Teststack eingebunden.

Docker Engine: 29.9.2, Compose: v5.6.1, Linux-Container/amd64 auf Windows.
Anwendungsimage: Python 3.12 Alpine, Django 5.2.19, WhiteNoise 6.12.0,
Gunicorn 23.0.0, django-rq 4.2.0, RQ 3.0.0, FFmpeg 8.1.3.
Keine lokal installierte Python-Version wurde für Build oder Abnahme verwendet.

## Tatsächlich ausgeführte Prüfungen

| Prüfung | Durchführung und Ergebnis |
|---|---|
| Standardstart | `docker compose up --build`: Build, Migrationen, collectstatic, automatischer Superuser, fünf laufende Dienste; DB/Redis/Web gesund |
| Standardbedienung | `docker compose ps`, `docker compose logs`, `docker compose down` und anschließend `docker compose up` ohne zusätzliche Argumente erfolgreich |
| Superuser | Beim leeren Erststart automatisch erstellt; echte HTTP-Admin-Anmeldung mit der `.env`-E-Mail und dem Passwort erfolgreich; Hash nach Container-Neuerstellung unverändert |
| Admin-Statik | Alle CSS-/JS-Verweise von Login und Dashboard über echtes Gunicorn-HTTP abgerufen; Status 200, nichtleerer Inhalt, korrekte Content-Types; `DEBUG=False` |
| Host-Port | Admin-Loginseite über `http://127.0.0.1:18081/admin/login/` vom Windows-Host: 200 |
| Registrierung/API | Echte HTTP-Registrierung 201, Worker-Mailstatus `sent`, Aktivierung 200, Cookie-Login 200, Video-API 200, Refresh/Logout 200; nach Logout API 401 |
| PostgreSQL/Redis | Reale Datenbank, echter Redis-PING und Cache-Roundtrip, registrierte Worker beider Queues; separater dauerhafter Redis-Prüfwert |
| Video-Upload | Vorhandene Live-Abnahme erzeugt synthetisches 1080p-Video und lädt es über das Admin-Formular hoch; echter Video-Worker erreicht `ready` |
| FFmpeg/HLS | Echte 480p-/720p-/1080p-Konvertierung und Thumbnail; jede Variante erneut mit FFmpeg decodiert; authentifizierte Manifeste und MPEG-TS-Segmente über echtes HTTP erfolgreich |
| Medienschutz | Anonymes HLS: 401; direkter privater Originalpfad: 404; öffentliches Thumbnail auch bei `DEBUG=False`: 200 |
| Beide Queues | `default` verarbeitet Mail asynchron, `video` konvertiert Video asynchron; echte RQ-Job-IDs und Scheduler nachgewiesen |
| SMTP | Ausschließlich die isolierte `.env` auf Django-SMTP, `EMAIL_HOST=web`, Port 1025, leere Test-Credentials und TLS/SSL false umgestellt; echter Default-Worker stellt eine Nachricht an internen SMTP-Sink zu; keine externe Nachricht |
| SMTP-Variablen | Zusätzlich Host, Port-Konvertierung, Benutzer, Passwort, TLS/SSL-Booleans und Absender mit synthetischen Werten geprüft; offizielle Variablen und Legacy-Fallbacks einschließlich Redis getestet |
| Persistenz | Vor `down` IDs, Superuser-Passworthash und SHA-256 von Original, Thumbnail, Playlists und Segmenten gesichert; nach neuem Build und nach normalem `up` identisch; Redis-Prüfwert erhalten |
| Reguläre Container-Tests | Vorhandene Suite mit `config.test_settings`: 129 entdeckt, 125 bestanden, vier ausdrücklich optionale Browserprüfungen übersprungen; 97 % Coverage |
| Vollständige Browser-Suite | Separater Debian/Python-3.12-Container mit Chromium und Live Server; Frontend read-only; **129 bestanden, keine Skips, Exit-Code 0**; finaler Lauf 30,212 Sekunden; **97 % Coverage** |
| Browser-Inhalte | Bestehende Registrierung/Aktivierung/Login/HLS-Wiedergabe/Refresh/Logout- und Reset-/Login-Flows sowie mobile/desktop Mail-Layouts unverändert erfolgreich |
| Projektprüfungen | Django `check`: keine Probleme; `makemigrations --check --dry-run`: keine Änderungen; `sh -n backend.entrypoint.sh`, Ruff-Lint, Formatter und bestehende 14-Zeilen-/Namensregeln erfolgreich |
| Schutz des Bestands | Alle zwölf vorherigen Volumes und alle 14 vorherigen Container-IDs weiter vorhanden; `git diff` für `accounts/`, `videos/` und `tests/` leer; Frontend-Arbeitsbaum sauber |

Die Browser-Suite verwendet wie zuvor ihren isolierten Django-Testserver und
Test-Mailjobs. Sie ersetzt nicht die separate Live-Abnahme mit Gunicorn,
PostgreSQL, Redis und unabhängigen Workern; beide Prüfwege wurden ausgeführt.
SMTP-Provider-Authentifizierung und tatsächliches STARTTLS/SSL gegen einen
externen Anbieter wurden mangels Provider-Zugangsdaten nicht geprüft.
Native macOS-/ARM-Hosts wurden nicht ausgeführt; getestet wurde die
plattformunabhängige Docker-Startstrecke auf Windows mit Linux-Containern.

## Fehlversuche und ihre Einordnung

- Der erste zusätzliche Versuch, die gesamte vorhandene Suite über
  `config.postgres_test_settings` auszuführen, scheiterte mit zwei Assertions,
  16 Verbindungsfehlern und vier Skips. Die Suite enthält ausdrücklich einen
  SQLite-Schutztest; einige Testtransaktionen kollidieren mit PostgreSQL und
  dem Schließen von Streaming-Responses. Außerdem war zunächst ein zusätzlicher
  JSON-Origin aus der Test-`.env` aktiv, den ein vorhandener Test absichtlich
  als nicht vertrauenswürdig erwartet. Keine Tests wurden angepasst oder
  entfernt. Der vorgesehene SQLite-Lauf und die unabhängige Live-PostgreSQL-
  Abnahme bestehen. Es wird kein erfolgreicher vollständiger PostgreSQL-
  Unit-Testlauf behauptet.
- Beim SMTP-Vorversuch fehlte nach Container-Neuerstellung eine zuvor nur mit
  `docker compose cp` eingespielte neue Prüfhilfe im alten Image. Nach regulärem
  Image-Build lief der SMTP-Test erfolgreich. Das endgültige Image enthält die
  versionierten Prüfhilfen; eine manuelle Nachinstallation ist dafür unnötig.
- Ruff konnte zunächst im read-only Prüfmount keinen Cache schreiben. Der
  abschließende Lauf verwendet `--no-cache`. Formatierungsbefunde der neuen
  Dateien wurden behoben. PowerShell stellt native stderr-Testausgaben teils
  als `NativeCommandError` dar; maßgeblich sind das Testresultat und der separat
  geprüfte Docker-Container-Exit-Code 0.

## Wiederholen und lokale Belege

Nur auf einer neuen isolierten Installation mit Datenbanknamen auf
`_acceptance` und Datei-Mailbackend ausführen:

```bash
docker compose up --build
docker compose exec web python manage.py shell -c "from scripts.verify_infrastructure import main; main()"
docker compose exec web python manage.py shell -c "from scripts.verify_docker_http import main; main()"
```

Für den SMTP-Prüfschritt in dieser isolierten `.env` den SMTP-Backend,
`EMAIL_HOST=web`, `EMAIL_PORT=1025`, leere `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`,
`EMAIL_USE_TLS=False` und `EMAIL_USE_SSL=False` setzen. Container mit
`docker compose up -d` neu erstellen, dann:

```bash
docker compose exec web python manage.py shell -c "from scripts.verify_docker_smtp import main; main()"
```

Der Sink ist nur während dieses Prüfschritts aktiv und hat keinen veröffentlichten
Host-Port. Anschließend wieder den Datei-Mailbackend wählen. Für reguläre
Tests und den separaten vollständigen Browser-Testcontainer siehe den
[README-Quickstart](README.md). `scripts/browser-tests.Dockerfile` wurde separat
erfolgreich gebaut und gehört ausschließlich zum optionalen Testwerkzeug.

Lokale Rohbelege liegen absichtlich unter dem Git-ignorierten `test-results/`:

- `docker-browser-final-tests.txt`, `docker-browser-final-coverage.txt`
- `docker-sqlite-tests.txt`, `docker-postgres-tests.txt` (fehlgeschlagener Zusatzlauf)
- `docker-infrastructure-final.txt`, `docker-http-final.txt`, `docker-smtp.txt`
- `docker-persistence-final.txt`, `docker-environment.txt`
- `docker-final-build.log`, `docker-final-runtime.log`, `docker-startup.log`
- `docker-volumes-before.txt`, `docker-containers-before.txt`
- `browser/` und `email-previews/` aus den bestehenden Browsertests
- `verify_persistence.py` und `check_environment.py` für die lokalen Zusatzprüfungen

Private `.env`, Maildateien, Uploads und Volumes sind keine Git-Artefakte.
Es wurden keine vorhandenen Volumes gelöscht, keine bestehenden Daten migriert,
keine Commits erstellt und nichts gepusht. Der isolierte Teststack wurde
abschließend mit `docker compose down` geordnet heruntergefahren. Seine sechs
Testvolumes bleiben erhalten; sämtliche zwölf vorherigen Volumes und alle
14 ursprünglichen Container-IDs wurden danach erneut bestätigt.
