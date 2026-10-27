# LogSanitizer — Anforderungen v2.7

Status: Planungsbaseline; Meilenstein 1 (lokaler Kern) umgesetzt, siehe ROADMAP.md.

## Plattform und Betrieb
- Portable lokale Anwendung für Windows und Linux; macOS ist nicht vorgesehen.
- Vollständig offline, ohne Cloud, externe APIs, CDN oder Internetabhängigkeit im Betrieb.
- Primär Anwendungslogs; einzelne Dateien und Ordner importieren, optional rekursiv. Import startet keine Verarbeitung.
- Quelldateien niemals automatisch ändern, verschieben oder löschen.
- Getrennter Arbeitsbereich für Quellen, temporäre Daten, geschützte Zuordnungen und Ausgaben.
- Standardmäßig nur an 127.0.0.1 binden. Netzwerkzugriff nur auf explizit konfigurierter IP und erst mit Authentifizierung/Berechtigungen.

## Stack und Skalierung
- Python (≥ 3.10, nur Standardbibliothek – keine Paketinstallation vor Ort), React/TypeScript (vorab gebaut), SQLite-Metadaten, versionierte JSON-Konfigurationen.
- Ohne Installation und ohne Administratorrechte lauffähig (Windows-Paket mit eingebettetem Python).
- Dateien von mindestens 5 GB streamend verarbeiten; gesamte Datei nicht in RAM laden.
- Streaming plus temporäre Indizes; temporäre und dauerhaft speicherbare Projekte.

## Regeln und Mappings
- Projekte können mehrere Logdateien und Quellenprofile enthalten; globale und profilspezifische Regeln.
- Format automatisch erkennen, manuelle Auswahl ermöglichen; unbekannte Formate nicht stillschweigend zuordnen.
- Strukturierte Erkennung (einschließlich JSON) und Text-/Regex-Regeln kombinieren; Multiline-Events und Stacktraces nach Möglichkeit erhalten.
- Regeln mit Name, aktiv/inaktiv, Literal oder Regex, Groß-/Kleinschreibung, Ersetzungsvorlage, Priorität und Profil.
- Regeln über GUI bearbeiten sowie versionierte JSON-Konfigurationen importieren/exportieren; Konflikte prüfen.
- Gleicher Originalwert muss innerhalb eines Projekts über Dateien und spätere Läufe konsistent ersetzt werden. Zuweisung unabhängig von Dateireihenfolge. Zuordnungen separat und geschützt speichern; allgemeine Regel-Exporte enthalten keine Mapping-Daten.
- Beispiel: [IP_1]; FQDN-Komponenten konfigurierbar, z. B. [Server_1].[Domain_1]. Doppelte Ersetzung vermeiden.

## Verarbeitung, Prüfung und Freigabe
- Regeltests, Vorschau, Fortschritt, Abbruch und klare Statusanzeigen.
- Unvollständige oder fehlgeschlagene Läufe dürfen nicht freigegeben werden.
- Pflichtprüfungen: technische/strukturelle Integrität und Suche nach verbliebenen sensiblen Mustern. Eine erfolgreiche Suche beweist nicht, dass alle sensiblen Daten erkannt wurden.
- Technische Validierung, menschliche Freigabe und Ausnahmen sind getrennte Zustände.
- Rollen: Administrator, Rule Owner, Processor, Reviewer/Releaser; eine Person kann anfangs mehrere Rollen übernehmen.
- Wenn ein Prüfer zugewiesen ist, ist eine bewusste Freigabe durch einen autorisierten Prüfer erforderlich. Ohne Prüfer nur automatische Freigabe nach allen Pflichtprüfungen.
- Prüfersuche unterstützt Ad-hoc-Literal/Regex und gespeicherte Muster; Regex braucht Ressourcenlimits.
- Rückgabe mit optionalem Kommentar sperrt regulären Export; erneute Verarbeitung erzeugt verknüpften Lauf.
- Ausnahmen nur mit Begründung, enger Gültigkeit und Auditierung; sie übergehen keine unabhängigen fehlgeschlagenen Pflichtprüfungen.

## Audit, Integration und Hilfe
- Audit protokolliert Benutzer, Zeitpunkt, Aktion, Entscheidung, Kommentar und Datei-/Lauf-/Regelbezüge, ohne Loginhalte zu kopieren.
- SMTP optional: Benachrichtigungen bei anstehender Prüfung und Rückgabe; E-Mails ohne Loginhalte, Geheimnisse, Zugangsdaten oder Mappings. SMTP-Ausfall darf Arbeitsabläufe nicht blockieren.
- Lokale Benutzer standardmäßig; LDAP/AD optional. SMTP-Zugangsdaten nicht exportieren oder protokollieren.
- Moderne, schlichte GUI; jede Option erhält verständliche MouseOver-Hilfe und tastaturzugängliche Erklärung.
- Ausführliche Hilfe vollständig offline, über Hilfemenü, F1 und kontextbezogene Hilfe. Keine externen Assets als Voraussetzung.

## Kern-Abnahmekriterien
- Lokal startbarer Backend-/Frontend-Kern mit Tests und Dokumentation.
- Mindestens 5-GB-Streaming wird später mit repräsentativen Tests nachgewiesen.
- Quelldateien bleiben unverändert; fehlgeschlagene/unkomplette Ausgabe ist nicht freigabefähig.
- Windows/Linux und Offline-Betrieb sind Zielanforderungen.

## Noch nicht implementiert
Authentifizierung/RBAC, Prüfer-Workflow mit Freigabe/Rückgabe, Ausnahmen, Audit, SMTP/LDAP, Netzwerkmodus und Verschlüsselung der Zuordnungen sind geplante Funktionen, keine vorhandenen Fähigkeiten. Umgesetzt sind Projekte, Import, Regel-Engine, Streaming, dauerhafte Zuordnungen, Pflichtprüfungen mit Restscan und portable Paketierung.
