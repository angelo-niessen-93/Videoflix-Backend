# GitHub-Abgabecheckliste

Stand: 4. November 2026. Kein Push im Release-Auftrag durchgeführt.

- [x] Backend separat vom unveränderten offiziellen Frontend versioniert.
- [x] Branch `main`, bestehende Historie vollständig beibehalten.
- [x] README, API-Vertrag, requirements, Migrationen und `.env.example` vorhanden.
- [x] Eigene Docker-Dateien unter `deploy/` eindeutig gekennzeichnet.
- [x] Alle 122 Tests einschließlich Browser und FFmpeg bestanden; Coverage 96 %.
- [x] Ruff, Format, 14-Zeilen-Regel, Django, Deployment, Migration und pip geprüft.
- [x] Laufzeitdaten, Secrets, Coverage und Testprotokolle vom Commit ausgeschlossen.
- [x] Docker Engine erreichbar: `docker version` liefert Server-Version 29.9.2; Containerabnahme ebenfalls bestanden.
- [x] Container gebaut/gestartet und isolierter Live-Abnahmetest erfolgreich.
- [x] PostgreSQL, Redis, beide Worker, Nginx, Thumbnails und geteilte Medienvolumes live geprüft.
- [ ] Eventuelle zusätzliche Academy-Docker-Vorlage/Abgaberegeln bestätigen.
- [ ] Den dokumentierten Reset-Formularfehler des offiziellen Frontends berücksichtigen.
- [ ] Falls verlangt: SMTP und Mailclient-Rendering nach ausdrücklicher Freigabe prüfen.
- [ ] Sichtbarkeit wegen Academy-Asset-Nutzungsbedingungen passend wählen.
- [x] Lokalen Git-Stand, Historie und Remote geprüft; kein Push.
- [ ] Vor Push erneut auf echte Secrets und unerlaubte Laufzeitdateien prüfen.
- [ ] GitHub-Ziel bestätigen und ausdrückliche Push-Freigabe einholen.
- [ ] Danach bei Bedarf `git fetch origin` und entfernte Historie prüfen; kein Force-Push.
- [ ] Erst mit Freigabe: `git push -u origin main`.
- [ ] Repository-Link, README-Startanleitung und DoD-Bericht für die Abgabe prüfen.

Vorhandenes Ziel: `https://github.com/angelo-niessen-93/Videoflix-Backend.git`.
Es wurde weder angelegt noch verändert. Die lokale Docker-Infrastrukturabnahme
ist bestanden: 29 PASS, 3 PARTIAL,
0 FAIL, 0 BLOCKED. Offen bleiben die oben genannten Kurs-/Abgabevorgaben,
SMTP/Mailclient-Rendering und Produktionshärtung; der bekannte offizielle
Reset-Formularfehler bleibt dokumentiert. Kein Infrastrukturblocker mehr.
