# Architektur

```text
Browser (React, vorab gebaut) ──HTTP 127.0.0.1 + Sitzungstoken──▶ server.py (http.server)
CLI (cli.py) ─────────────────────────────────────────────────────▶ pipeline.py
                                                                     │
  project.py   Arbeitsbereich: project.json, rules.json, names.json, mapping.sqlite, runs/
  rules.py     versionierte Regeln, Standardregeln, Regex-Laufzeitprüfung
  engine.py    Erkennung (alle Regeln, Überlappungsauflösung), Normalisierung, Ersetzung
  formats.py   Kodierung/Format-Erkennung, Block-Streaming, JSON-String-Rewriter
  blocks.py    Blockverarbeitung inline oder in Worker-Prozessen (geordnet, begrenzt)
  mapping.py   SQLite-Zuordnung Original → Platzhalter (vertraulich)
  validate.py  Restscan der Ausgabe
  samples.py   synthetische Testdaten, Selbsttest
```

Laufzeit nur Python-Standardbibliothek (≥ 3.10). Das Frontend wird in CI gebaut und als statische Dateien ausgeliefert.

## Ablauf eines Laufs

1. **Auflösen**: Kodierung (BOM, UTF-16-Heuristik, UTF-8, sonst cp1252) und Format (JSON Lines, JSON-Dokument, Text) je Datei; Binärdateien → Fehler.
2. **Phase 1 – Sammeln**: alle Dateien blockweise lesen, alle Treffer sammeln.
3. **Zuordnen**: neue Werte sortiert nummerieren (unabhängig von Dateireihenfolge), bestehende behalten ihre Nummer.
4. **Phase 2 – Schreiben**: Ersetzung nach `runs/<id>/output.partial/`. Zusätzlich werden alle bekannten Werte als Literale mit niedriger Priorität gesucht, damit z. B. `jdoe` aus `CORP\jdoe` auch allein ersetzt wird.
5. **Phase 3 – Prüfen**: Restscan (Regeln + alle bekannten Originalwerte), Zeilenanzahl, Quelldateien unverändert (Größe/mtime).
6. **Abschluss**: bestanden → `output/`; Funde → `output.blocked/` mit Hinweisdatei; Fehler/Abbruch → keine Ausgabe. `report.json` (vertraulich) im Laufordner.

## Erkennung

- Regex-Regeln mit benannten Gruppen: Gruppenname = Kategorie, nur Gruppeninhalt wird ersetzt (`(?P<Server>…)\.(?P<Domain>…)` → `[Server_1].[Domain_1]`).
- Überlappungen: höhere Priorität, dann längerer Treffer, dann früherer Start gewinnt; jede Stelle wird höchstens einmal ersetzt. Vorhandene Platzhalter werden nie erneut ersetzt (Idempotenz).
- Normalisierung für die Zuordnung: IPv4 ohne führende Nullen, IPv6 komprimiert, MAC kleingeschrieben mit `:`, sonst `casefold()`.
- FQDN/Domain nur mit konfigurierten TLDs, damit Dateinamen und Java-Pakete nicht getroffen werden.
- JSON: Ein Tokenizer verändert nur String-Inhalte (dekodiert, bereinigt, neu escaped); Werte unter Schlüsseln wie `password`/`token` werden vollständig als `[Secret_n]` ersetzt.

## Leistung

- Blöcke von ~1 Mio. Zeichen enden an Zeilenumbrüchen (überlange Zeilen an Leerraum), daher konstanter Speicherbedarf.
- Text- und JSON-Lines-Blöcke werden ab 16 MB Gesamtgröße auf `CPU-Kerne − 1` (max. 8) Prozesse verteilt; Reihenfolge bleibt erhalten, höchstens 2 Blöcke je Prozess sind unterwegs. `LOGSANITIZER_WORKERS` überschreibt die Anzahl.
- Regex-Optimierungen: Namenslisten laufen als exakter Vergleich auf kleingeschriebenem Text; Regeln mit seltenen Ankern (`@`, `\`, `://`, …) laufen nur auf passenden Zeilen; IPv4/MAC/IPv6-Muster beginnen mit einer Zeichenklasse.
- Messung (synthetisches Syslog, 200 MB, Apple M-Serie): 1 Prozess ~110 s, 9 Prozesse ~20 s, ~70 MB RAM im Hauptprozess.

## Sicherheit

1. Server bindet nur an 127.0.0.1; Host-Header muss Loopback sein (DNS-Rebinding); API nur mit zufälligem Sitzungstoken aus dem Startlink; keine CORS-Header; CSP und `X-Frame-Options`.
2. Quelldateien werden nur lesend geöffnet; Ausgaben entstehen ausschließlich im Laufordner.
3. Vertraulich und nie in Ausgaben oder Regel-Exporten: `names.json`, `mapping.sqlite`, `report.json` (enthält Restfunde).
4. Regex-Regeln werden beim Speichern in einem separaten Prozess gegen Backtracking-Muster mit Zeitlimit getestet.
5. Validierung reduziert Risiken, garantiert aber nicht die Erkennung jedes sensiblen Werts.

## Offene Entscheidungen

- Verschlüsselung der Zuordnung: Die Standardbibliothek bietet keine; derzeit Schutz über Dateisystemrechte und ggf. BitLocker.
- Rollen, Prüfer-Workflow, Ausnahmen, SMTP und LDAP (siehe Roadmap).
- Einzelne riesige JSON-Dokumente werden sequenziell (ein Kern) verarbeitet.
