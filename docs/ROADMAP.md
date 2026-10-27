# Roadmap

## Meilenstein 0 — Grundgerüst
- [x] Anforderungen v2.7 dokumentieren.
- [x] Health-Endpunkt und Test.
- [x] React/TypeScript-Oberfläche mit lokal eingebundener Hilfe.
- [x] Tests unter Windows und Linux in CI (Python 3.10 und 3.12).

## Meilenstein 1 — Sicherer lokaler Kern
- [x] Projektverwaltung und Arbeitsbereich (JSON + SQLite).
- [x] Einzeldatei-/Ordnerimport (optional rekursiv), Originale bleiben unverändert.
- [x] Format-/Kodierungserkennung, Binärdateien werden abgelehnt, manuelle Auswahl möglich.
- [x] Versionierte Regelkonfiguration mit Schema-, Konflikt- und Regex-Laufzeitprüfung; Import/Export ohne Namen und Zuordnungen.
- [x] Streaming für Text, JSON Lines und JSON-Dokumente mit begrenztem Speicherbedarf; Mehrkernverarbeitung.
- [x] Stabile, reihenfolgeunabhängige Projekt-Zuordnungen, getrennt gespeichert.
- [x] Fortschritt, Abbruch, Bereinigung unvollständiger Ausgaben.
- [x] Pflichtvalidierung und Restscan; Freigabe bei Fehlern gesperrt.
- [x] Portable Pakete (Windows mit eingebettetem Python, Linux), Selbsttest, Offline-Hilfe.
- [ ] Praxistest auf den Zielsystemen (Windows ohne Adminrechte, Linux) mit realen Logformaten.
- [ ] 5-GB-Test auf Zielhardware.

## Meilenstein 2 — Prüfung und kontrollierte Freigabe
- [ ] Lokale Anmeldung und rollenbasierte Rechte.
- [ ] Prüfer-Warteschlange und sichere Suche (Ad-hoc-Literal/Regex mit Limits).
- [ ] Freigabe/Rückgabe mit Kommentar, Laufhistorie und Audit.
- [ ] Begründete, eng begrenzte Ausnahmen.
- [ ] Verschlüsselung der Zuordnungstabelle.

## Meilenstein 3 — Deployment
- [ ] Optionale SMTP-Benachrichtigungen und Konfigurationstest.
- [ ] Optionale LDAP/AD-Integration.
- [ ] Geschützte Netzwerkbindung für den Darksite-Betrieb.
- [ ] Sicherheits- und Performanceprüfung.

## Definition of done
Eine Funktion benötigt Tests, verständliche Offline-Hilfe, sicheres Fehlerverhalten und Dokumentation. Sicherheitsfunktionen müssen auch abgewiesene/unzulässige Pfade testen.
