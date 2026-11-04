# Docker Desktop: allgemeine Diagnose unter Windows

Diese Anleitung enthält keine lokalen Rechnerbefunde, Gerätekennungen,
Systemprotokolle oder Diagnosepaketpfade. Den aktuellen Projektstatus nennt
[FINAL_ACADEMY_ACCEPTANCE.md](../FINAL_ACADEMY_ACCEPTANCE.md).

## Nur lesend prüfen

```powershell
docker version
docker compose version
docker context show
docker compose ls --all
docker ps -a
docker volume ls
wsl --status
wsl --list --verbose
```

Eine gestartete Desktop-Oberfläche allein belegt keine erreichbare Engine.
Entscheidend sind eine erfolgreiche Docker-Serverantwort und anschließend
die Healthchecks des eigenen Compose-Projekts. Für dessen Start und die
isolierte Live-Abnahme gilt die [Docker-Anleitung](README.md).

Falls Docker fehlende WSL-/Virtualisierungsvoraussetzungen oder eine
unvollständige Windows-Komponentenbereitstellung meldet, zunächst die genaue
Fehlermeldung lokal erfassen und die offiziellen Diagnoseanleitungen prüfen.
Diagnosepakete können persönliche Daten enthalten und bleiben außerhalb von Git.

Systemreparaturen, Windows-Features, Boot-/BIOS-Änderungen oder ein Neustart
gehören nicht zur Backend-Abnahme und werden nicht automatisch ausgeführt.
Vorhandene Container und Volumes zunächst zuordnen; keine Factory Resets,
Prune-Befehle oder Volume-Löschungen zur allgemeinen Fehlerbehebung verwenden.

## Offizielle Referenzen

- [Docker: Diagnose und Protokolle](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/)
- [Docker: WSL2-Backend](https://docs.docker.com/desktop/features/wsl/)
- [Microsoft: WSL-Fehlerbehebung](https://learn.microsoft.com/en-us/windows/wsl/troubleshooting)
