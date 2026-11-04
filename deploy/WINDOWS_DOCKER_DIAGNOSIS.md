# Windows-/WSL-/Docker-Diagnose

Historischer Diagnosebefund vom 4. November 2026, Europe/Berlin.
Zum Diagnosezeitpunkt konnte die Linux-Engine nicht gestartet werden.

Aktualisierung vor dem Dokumentationscommit: `docker version` liefert
inzwischen erfolgreich die Server-Version 29.9.2. Die folgenden Befunde und
bedingten Reparaturschritte beschreiben den damaligen Zustand. Eine weitere
Systemreparatur ist daraus aktuell nicht abzuleiten. Die anschließende
Videoflix-Container- und Infrastrukturabnahme war erfolgreich; siehe
[aktuellen Prüfbericht](../VIDEOFLIX_DOD_REPORT.md).

## Befund

| Prüfung | Nachweis |
|---|---|
| WSL | 3.0.3.0, Kernel 6.18.54.1-1, Standardversion 2 |
| Distributionen | Keine registriert; WSL2 meldet fehlende Virtualisierungs-Voraussetzungen |
| Docker Desktop | 4.96.3.244472, CLI-Plugin 4.96.3 |
| Docker CLI / Compose | Zuvor CLI 29.9.2; Compose erneut v5.6.1 |
| Docker Backend | stopped; WslVirtualMachinePlatformNotEnabled |
| WSL-Dienst | WslService läuft |
| Fehlende Dienste | vmcompute und hns nicht registriert |
| Fehlende Dateien | System32/vmcompute.exe, System32/drivers/vmswitch.sys und System32/hns.dll nicht vorhanden |
| Vorhandene Infrastruktur | computecore.dll, vid.dll und drivers/vid.sys vorhanden |
| Benutzerkonfiguration | Keine .wslconfig gefunden; kein Nachweis eines problematischen Overrides |
| Lokale Projektkonfiguration | Keine .env vorhanden; keine Secrets ausgegeben oder überschrieben |

Der angehaltene com.docker.service ist allein kein Beweis für den Fehler:
Docker verwendet hier das WSL-Backend. Auch das Fehlen einer separat
installierten Ubuntu-Distribution ist allein keine Ursache; Docker verwaltet
seine eigene interne WSL-Umgebung.

## Konkret eingegrenzte Ursache

Docker beendet den Linux-/WSL-Start bereits bei der Prüfung der Windows-
Voraussetzungen mit `WslVirtualMachinePlatformNotEnabled`. HTTP 500 an der
Docker-Pipe ist damit ein Folgefehler und kein hinreichender Beleg für eine
falsch gewählte Docker-API-Version.

Die Windows-Komponentenwartung ist nachweislich nicht abgeschlossen:

- Der CBS-Registry-Schlüssel RebootPending ist vorhanden.
- PackagesPending enthält HyperV-Compute-Host- und Containers-Server-HNS-Pakete.
- C:/Windows/WinSxS/pending.xml enthält noch Hardlink-/Dateiaktionen für
  System32/vmcompute.exe und System32/drivers/vmswitch.sys.
- CBS.log meldet eine ausstehende Neustartverarbeitung:
  `RebootPending volatile key indicates that a reboot is pending, skip startup processing.`
- Die VirtualMachinePlatform-Pakete der Revision 9711 zeigen CurrentState 96
  (0x60); dieser Rohwert wurde erfasst, nicht als erfolgreicher Feature-Start
  interpretiert.

Damit ist die unvollendete Windows-Komponentenbereitstellung der derzeit am
besten belegte Startblocker. Warum die ausstehenden Aktionen bisher nicht
abgeschlossen wurden und ob danach zusätzlich eine Beschädigung verbleibt,
ist noch nicht festgestellt. Eine abgeschlossene Korruptionsprüfung liegt
nicht vor. Einzelne CBS-Meldungen zu nicht anwendbaren älteren KB-Paketen
werden nicht als Beweis für beschädigte Hyper-V-Komponenten gewertet.

Die CPU-Abfragen SLAT=False und VMMonitorModeExtensions=False beweisen in
diesem Zustand keine fehlende Hardwarefähigkeit. Der tatsächlich laufende
Hypervisor und das erfolgreiche Start-Ereignis sprechen gegen die pauschale
Behauptung, SVM sei ausgeschaltet. BIOS-/Boot-Änderungen sind nicht begründet.

## Bereits ausgeführt

1. Versionen, Dienst-/Datei-/Registryzustand, Docker-Logs, Systemereignisse,
   CBS-/DISM-Protokolle und ausstehende Komponentenaktionen lesend untersucht.
2. `docker desktop diagnose` ohne Upload erfolgreich abgeschlossen. Das lokale
   Paket enthält 145 abgeschlossene Gatherer; Linux-/Engine-Abfragen enthalten
   erwartungsgemäß Timeouts. Ein vollständiger Diagnoseablauf ist kein
   erfolgreicher Engine-Test.
3. `docker desktop restart --timeout 45` kontrolliert versucht. Exitcode 1,
   `Docker Desktop is still starting: context deadline exceeded`.
4. Backend danach weiterhin stopped mit demselben Voraussetzungskonflikt.
5. `docker version` und `docker info` nach dem Neustart jeweils nach 20 Sekunden
   ohne Ergebnis abgebrochen. Kein erfolgreicher Server-/Info-Nachweis.
6. `wsl --status` und `wsl --list --verbose` erneut ausgeführt; unverändert
   keine nutzbare WSL2-Umgebung bzw. registrierte Distribution.
7. Isoliertes Compose-Projekt mit nur im Prozess erzeugten Zufallswerten durch
   `docker compose ... config --quiet` erneut statisch validiert.

Der Online-DISM-Featurecheck wurde mit Fehler 740 abgewiesen. Für eine
verbindliche Online-Feature-/Komponentenspeicherprüfung ist ein erhöhter
Administratorprozess nötig. Sandbox-Eskalation allein verleiht dem Prozess
keinen erhöhten Windows-Administratortoken.

Keine Features, Boot-Konfiguration, BIOS-Einstellungen oder Diensteinstellungen
geändert. Keine Installation, kein Factory Reset, kein Unregister, keine
Bereinigung oder Datenlöschung und kein automatischer Windows-Neustart.
Das Diagnosepaket wurde nicht hochgeladen.

## Damals empfohlener nächster Schritt: manueller Neustart

Arbeit speichern und Windows selbst über **Start → Ein/Aus → Neu starten**
neu starten. Kein automatischer Neustartbefehl wird ausgeführt. Danach zuerst
die tatsächliche Bereitstellung prüfen:

```powershell
Get-Service vmcompute,hns,WslService -ErrorAction SilentlyContinue
Test-Path C:/Windows/System32/vmcompute.exe
Test-Path C:/Windows/System32/drivers/vmswitch.sys
wsl --status
wsl --list --verbose
docker desktop start --timeout 60
docker version
docker info
docker compose version
```

Keine neue Ubuntu-Distribution installieren, nur um die leere Distributionsliste
zu ändern. Entscheidend ist eine funktionierende WSL2-/Docker-Linux-Engine.
Falls der manuelle Neustart die Komponentenbereitstellung abschließt, ist
keine zusätzliche Systemreparatur nötig.

## Nur falls der Fehler nach dem Neustart bleibt

Diese Befehle sind vorbereitet, **nicht ausgeführt**. Zuerst nach Freigabe eine
PowerShell als Administrator öffnen und ausschließlich Diagnose ausführen:

```powershell
Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
DISM.exe /Online /Cleanup-Image /CheckHealth
DISM.exe /Online /Cleanup-Image /ScanHealth
sfc.exe /verifyonly
```

Ergebnisse auswerten, bevor etwas geändert wird. Falls eine Beschädigung
bestätigt wird, wären nach ausdrücklicher Reparaturfreigabe die üblichen
Microsoft-Reparaturschritte:

```powershell
DISM.exe /Online /Cleanup-Image /RestoreHealth
sfc.exe /scannow
```

RestoreHealth kann Windows Update als Reparaturquelle verwenden. Falls das
Feature nachweislich deaktiviert ist, wäre stattdessen nach ausdrücklicher
Feature-Freigabe die gezielte Aktivierung vorzubereiten:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
```

Die WSL-Komponente nur bei bestätigtem Bedarf separat behandeln. Keine
pauschale Deaktivierung/Reaktivierung von Features, keine vollständige
Hyper-V-Rolleninstallation und keine Dienstregistrierung aus fremden Dateien.
Ein eventuell nötiger weiterer Neustart bleibt eine manuelle Benutzeraktion.

## Videoflix nach erfolgreichem Engine-Test

Die Abnahmebefehle stehen in [README.md](README.md#dedicated-live-infrastructure-acceptance).
Ein frisches Compose-Projekt mit eigener `_acceptance`-Datenbank verwenden;
bereits vorhandene Projektvolumes vorher prüfen und nicht löschen. Dann Build,
Migrationen, Web/Gateway, PostgreSQL, Redis und beide RQ-Worker starten und
`scripts.verify_infrastructure.main()` wie dokumentiert ausführen. Erst nach
erfolgreicher Prüfung DoD-Statuswerte hochstufen.

Zum Diagnosezeitpunkt: keine erfolgreich gestarteten Videoflix-Container nachgewiesen;
PostgreSQL, Redis, getrennte Worker und FFmpeg/HLS innerhalb Docker offen.
Die früheren lokalen 122 Tests und 96 % Anwendungscoverage werden nicht als
Nachweis für einen erfolgreichen Containerbetrieb ausgegeben.

## Lokale Nachweise

Die Diagnose- und Neustartprotokolle unter `test-results/` sowie das
Diagnosepaket im lokalen Temp-Verzeichnis bleiben lokal und werden nicht
versioniert. Rechnerbezogene Paketkennungen und absolute Diagnosepfade
werden hier nicht dokumentiert. Diese Datei fasst nur technische Befunde
zusammen.

## Offizielle Referenzen

- [Microsoft: WSL-Fehlerbehebung](https://learn.microsoft.com/en-us/windows/wsl/troubleshooting).
- [Microsoft: Systemdateien mit DISM/SFC prüfen und reparieren](https://support.microsoft.com/en-us/windows/experience/backup-recovery/use-the-system-file-checker-tool-to-repair-missing-or-corrupted-system-files).
- [Docker: Diagnose und Protokolle](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/).
- [Docker: WSL2-Backend](https://docs.docker.com/desktop/features/wsl/).
