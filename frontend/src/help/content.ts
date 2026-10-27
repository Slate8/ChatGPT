/** Locally bundled offline help. Use synthetic examples only. */
export const helpTopics = [
  { id: "getting-started", title: "Erste Schritte", summary: "LogSanitizer arbeitet nur auf diesem Rechner; Originaldateien werden nie verändert.", steps: [
    "Projekt anlegen – ein Projekt pro Kunde bzw. Vorgang, damit Platzhalter dauerhaft gleich bleiben.",
    "Unter „Dateien“ Logdateien oder ganze Ordner hinzufügen (Pfad eingeben oder „Durchsuchen“).",
    "Unter „Namenslisten“ interne Kurznamen (Server, Dienstkonten, Firmenname) eintragen.",
    "Unter „Regeln & Vorschau“ mit einem Beispieltext prüfen, ob alles erkannt wird.",
    "Unter „Läufe“ einen Lauf starten. Nur ein freigabefähiger Lauf erzeugt einen Ausgabeordner.",
    "Ausgabe vor der Weitergabe stichprobenartig ansehen." ] },
  { id: "detection", title: "Was wird erkannt?", summary: "Standardregeln erkennen strukturierte Werte automatisch; interne Kurznamen brauchen Namenslisten.", steps: [
    "Automatisch: IPv4/IPv6, MAC, E-Mail, vollqualifizierte Hostnamen (server.domain.local), DOMAIN\\Benutzer, UNC-Pfade, Domänen-SIDs, Hostnamen in URLs, Passwörter/Token in Zuweisungen und JSON-Feldern.",
    "Nicht automatisch: kurze Hostnamen wie dc01 oder fileserver, Dienstkonten, Firmennamen im Fließtext. Diese in Namenslisten eintragen.",
    "Einmal erkannte Werte (z. B. jdoe aus NORDWERK\\jdoe) werden im selben Lauf auch an allen anderen Stellen ersetzt.",
    "Hostnamen und Domains werden nur mit bekannten Endungen erkannt (Liste unter „Regeln“), damit Dateinamen wie app.log unverändert bleiben." ] },
  { id: "rules", title: "Regeln und Muster", summary: "Regeln können feste Texte (Literal) oder reguläre Ausdrücke (Python-Syntax) sein.", steps: [
    "Literal passt auf ganze Wörter, Groß-/Kleinschreibung wird standardmäßig ignoriert.",
    "Regex: benannte Gruppen wie (?P<Server>…) ersetzen nur den Gruppeninhalt; der Gruppenname ist die Kategorie.",
    "Überlappen sich Treffer, gewinnt die höhere Priorität, danach der längere Treffer. Nichts wird doppelt ersetzt.",
    "Neue Regex-Regeln werden beim Speichern auf extreme Laufzeiten geprüft.",
    "Regel-Exporte enthalten weder Namenslisten noch Zuordnungen und können zwischen Projekten geteilt werden." ] },
  { id: "mappings", title: "Platzhalter und Zuordnungen", summary: "Gleiche Werte erhalten im ganzen Projekt immer denselben Platzhalter – über Dateien und Läufe hinweg.", steps: [
    "Beispiel: srv01.corp.local → [Server_1].[Domain_1], 10.0.0.5 → [IP_1].",
    "Die Nummerierung hängt nicht von der Reihenfolge der Dateien ab: neue Werte werden sortiert nummeriert.",
    "Die Zuordnungstabelle ist streng vertraulich und verlässt nie den Projektordner, außer durch bewussten CSV-Export." ] },
  { id: "validation", title: "Prüfung und Freigabe", summary: "Nach jedem Lauf wird die Ausgabe automatisch geprüft. Nur bei bestandenen Pflichtprüfungen entsteht der Ordner „output“.", steps: [
    "Restscan: alle Regeln laufen erneut über die Ausgabe, zusätzlich wird nach allen bekannten Originalwerten gesucht.",
    "Weitere Prüfungen: gleiche Zeilenanzahl, gültige Kodierung und Struktur, Quelldateien unverändert.",
    "Gesperrte Läufe legen ihre Ausgabe in „output.blocked“ ab – nicht weitergeben.",
    "Abgebrochene oder fehlgeschlagene Läufe hinterlassen keine Ausgabe.",
    "Ein bestandener Restscan beweist nicht, dass jedes sensible Datum erkannt wurde." ] },
  { id: "offline", title: "Betrieb und Sicherheit", summary: "Die Anwendung benötigt kein Internet und keine Installation.", steps: [
    "Der Server ist nur auf diesem Rechner erreichbar (127.0.0.1) und nur über den Startlink mit Sitzungsschlüssel.",
    "Ohne Browser: Befehlszeile „python -m logsanitizer sanitize --project NAME PFAD“.",
    "„python -m logsanitizer selftest“ prüft mit erfundenen Daten, ob alles auf diesem Rechner funktioniert.",
    "Große Dateien werden blockweise und auf mehreren Prozessorkernen verarbeitet; der Speicherbedarf bleibt gering." ] },
] as const;
