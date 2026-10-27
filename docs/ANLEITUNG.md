# LogSanitizer – Anleitung

LogSanitizer ersetzt in Logdateien interne Namen, IP-Adressen, Konten und Zugangsdaten durch Platzhalter wie `[Server_1]`, `[IP_3]` oder `[User_2]`. Die bereinigten Dateien können dann weitergegeben werden, z. B. an einen Hersteller-Support, ohne dass interne Informationen das Netz verlassen.

- Die Originaldateien werden **nie verändert**. Bereinigte Kopien entstehen in einem eigenen Ordner.
- Gleiche Werte bekommen **immer denselben Platzhalter**, über alle Dateien und alle späteren Läufe eines Projekts hinweg. Steht `srv01` in zwei Logs, heißt er in beiden `[Server_1]`.
- Text- und JSON-Dateien behalten ihre **Struktur** (Zeilen, Kodierung, JSON-Aufbau).
- Alles läuft **lokal** auf dem Rechner. Kein Internet, keine Installation und keine Administratorrechte nötig.

---

## 1. Paket besorgen und übertragen

1. Auf einem Rechner mit GitHub-Zugang unter **Releases** die passende Datei herunterladen:
   - **Windows:** `LogSanitizer-<Version>-windows-x64.zip`. Python ist enthalten.
   - **Linux:** `LogSanitizer-<Version>-portable.zip`. Benötigt Python 3.10 oder neuer, das bei aktuellen Distributionen meist vorinstalliert ist.
   - Außerdem `SHA256SUMS.txt`.
2. Die ZIP-Datei auf dem freigegebenen Weg auf das Zielsystem kopieren.
3. **Prüfsumme kontrollieren** (stellt sicher, dass die Datei unverändert angekommen ist):
   - Windows (PowerShell): `Get-FileHash .\LogSanitizer-<Version>-windows-x64.zip`
   - Linux: `sha256sum LogSanitizer-<Version>-portable.zip`
   - Der angezeigte Wert muss mit der Zeile in `SHA256SUMS.txt` übereinstimmen.
4. **Nur Windows:** Rechtsklick auf die ZIP-Datei → *Eigenschaften* → unten bei *Sicherheit* den Haken **„Zulassen“** setzen → *OK*. Sonst warnt Windows bei jedem Start („Der Computer wurde durch Windows geschützt“).
5. ZIP in einen Ordner entpacken, in dem du Schreibrechte hast, z. B. `C:\Users\<Name>\LogSanitizer` oder `D:\Tools\LogSanitizer`.

## 2. Funktionstest (einmalig empfohlen)

Bevor echte Logs bearbeitet werden, prüfen, ob das Programm auf diesem Rechner funktioniert. Der Test verwendet nur erfundene Daten:

- **Windows:** Doppelklick auf `selbsttest.bat`
- **Linux:** `./cli.sh selftest`

Erwartete Ausgabe: `Selbsttest bestanden: 7 Dateien, … keine Restfunde.`

## 3. Starten und Beenden

- **Windows:** Doppelklick auf `start.bat`
- **Linux:** `./start.sh` im entpackten Ordner

Ein Konsolenfenster öffnet sich und der Browser startet automatisch mit der Oberfläche. Öffnet sich kein Browser, den im Fenster angezeigten Link (`http://127.0.0.1:8765/#token=…`) kopieren und im Browser (Edge, Firefox, Chrome) öffnen.

- Das **Konsolenfenster offen lassen**, solange gearbeitet wird.
- **Beenden:** Fenster schließen oder darin `Strg+C` drücken.
- Die Oberfläche ist nur auf diesem Rechner erreichbar und nur über den Startlink. Er enthält einen zufälligen Sitzungsschlüssel (`#token=…`), damit keine andere Webseite und kein anderer Benutzer auf die Daten zugreifen kann.
- Nach dem ersten Öffnen merkt sich der Browser den Schlüssel. Neue Tabs und Neuladen funktionieren dann ohne den Link.
- **Bei jedem Programmstart entsteht ein neuer Schlüssel.** Alte Links und Lesezeichen gelten danach nicht mehr. Zeigt der Browser „Bitte über den Startlink öffnen“, einfach den aktuellen Link aus dem Konsolenfenster öffnen.

## 4. Arbeitsablauf in der Oberfläche

### 4.1 Projekt anlegen
Auf der Startseite einen Projektnamen eingeben (z. B. „Kunde A – Störung Oktober“) und **Anlegen** klicken.

Faustregel: **ein Projekt pro Vorgang bzw. Empfänger.** Innerhalb eines Projekts bleiben die Platzhalter dauerhaft gleich. Werden später weitere Logs zum selben Vorgang nachgeliefert, dasselbe Projekt verwenden.

### 4.2 Dateien hinzufügen (Reiter „Dateien“)
- Pfad einer Datei oder eines Ordners eingeben, z. B. `D:\Export\Logs`, oder über **Durchsuchen …** auswählen.
- **Unterordner einbeziehen** übernimmt auch alle Dateien in Unterordnern. Die Ordnerstruktur bleibt in der Ausgabe erhalten.
- Die Dateien werden nicht kopiert, sondern beim Lauf direkt gelesen. Auch sehr große Dateien (mehrere GB) sind kein Problem.
- **Format** und **Kodierung** werden automatisch erkannt. Nur ändern, wenn ein Lauf mit einer Fehlermeldung dazu abbricht (siehe Abschnitt 8).

### 4.3 Namenslisten pflegen (Reiter „Namenslisten“) – wichtig!
Vieles wird automatisch erkannt, zum Beispiel IP-Adressen, `server.firma.local`, `FIRMA\benutzer` und E-Mail-Adressen. **Kurze interne Namen erkennt aber kein Programm von allein**, z. B. `dc01`, `fileserver`, `svc_backup` oder den Firmennamen im Fließtext.

- Unter **Server**, **User** und **Domain** je einen Namen pro Zeile eintragen. Groß- und Kleinschreibung ist egal.
- **Aus Datei ergänzen** liest TXT- oder CSV-Listen ein, z. B. einen Export aller Rechnernamen.
- Bei Bedarf eigene Kategorien anlegen (z. B. „Kunde“). Daraus werden Platzhalter wie `[Kunde_1]`.
- **Namenslisten speichern** nicht vergessen.

Je vollständiger die Listen, desto sicherer das Ergebnis. Die Listen sind vertraulich und bleiben im Projektordner.

### 4.4 Regeln prüfen (Reiter „Regeln & Vorschau“)
- Unten in der **Vorschau** einen typischen Logauszug einfügen. Das Ergebnis erscheint sofort, darunter steht die Liste aller Treffer. Neue Werte werden als `[Kategorie_neu]` angezeigt, bekannte mit ihrem Platzhalter.
- Die **Standardregeln** reichen meist aus. Sie lassen sich ein- und ausschalten oder bearbeiten, und über **+ Eigene Regel** kommen neue hinzu (fester Text oder regulärer Ausdruck).
- **Nie ersetzen (Allowlist):** Werte, die bewusst stehen bleiben sollen, z. B. `127.0.0.1`.
- **Top-Level-Domains:** Hostnamen werden nur mit diesen Endungen erkannt. Interne Endungen ergänzen, falls sie fehlen (z. B. `.firma`).
- **Exportieren/Importieren** überträgt Regeln in andere Projekte. Exporte enthalten weder Namenslisten noch Zuordnungen.
- Nach Änderungen **Regeln speichern**.

### 4.5 Lauf starten (Reiter „Läufe“)
**Lauf starten** klicken. Der Fortschrittsbalken zeigt drei Phasen:
1. **Analyse:** Alle Dateien werden gelesen und alle sensiblen Werte gesammelt.
2. **Schreiben:** Die bereinigten Kopien werden erstellt.
3. **Prüfung:** Die Ausgabe wird noch einmal komplett nach Resten durchsucht.

Ein Lauf kann jederzeit **abgebrochen** werden. Dabei bleibt keine halbfertige Ausgabe zurück.

### 4.6 Ergebnis verstehen

| Status | Bedeutung | Was tun? |
| --- | --- | --- |
| **Freigabefähig** | Alle Pflichtprüfungen bestanden. | **Ausgabeordner öffnen**, Stichprobe ansehen, dann weitergeben. |
| **Gesperrt** | Die Prüfung hat Reste gefunden (Tabelle „Restfunde“). | Fehlende Namen in die Namenslisten eintragen oder Regeln anpassen, dann **neuen Lauf** starten. Die gesperrte Ausgabe **nicht** weitergeben. |
| **Fehlgeschlagen** | Eine Datei konnte nicht verarbeitet werden (Meldung beachten). | Siehe Abschnitt 8, dann neuen Lauf starten. |
| **Abgebrochen** | Manuell gestoppt. | – |

Weitergegeben wird **nur der Ordner `output`** eines freigabefähigen Laufs. Am besten packst du ihn als ZIP.

> Ein bestandener Restscan senkt das Risiko deutlich, ist aber **kein Beweis**, dass jede sensible Angabe gefunden wurde. Vor der Weitergabe immer eine Stichprobe ansehen, besonders Freitextfelder und Kommentare.

### 4.7 Zuordnung nachschlagen (Reiter „Zuordnung“)
Fragt der Empfänger später z. B. nach „[Server_3]“, lässt sich hier nachsehen, welcher echte Name dahintersteht. Die Tabelle ist **streng vertraulich**. Der CSV-Export ist nur für die interne Ablage gedacht.

## 5. Ablage der Daten

Alles liegt im Ordner `workspace` neben den Startdateien:

```text
workspace/projects/<projekt>/
    project.json        Projekt und Dateiliste
    rules.json          Regeln
    names.json          Namenslisten              (VERTRAULICH)
    mapping.sqlite      Zuordnungstabelle         (VERTRAULICH)
    runs/<lauf>/
        report.json     Prüfbericht mit Restfunden (VERTRAULICH)
        output/         bereinigte Dateien → darf weitergegeben werden
        output.blocked/ gesperrte Ausgabe → NICHT weitergeben
```

Der `workspace`-Ordner darf das interne Netz nicht verlassen. Wird das Programm aktualisiert (neue ZIP-Version), den alten `workspace`-Ordner in den neuen Programmordner kopieren. Dann bleiben Projekte und Platzhalter erhalten.

## 6. Kommandozeile (ohne Browser)

Alle Funktionen gibt es auch ohne Oberfläche. Unter Windows wird `cli.bat` verwendet, unter Linux `./cli.sh`:

```text
cli.bat selftest
cli.bat sanitize --project "Kunde A" -r D:\Export\Logs
cli.bat sanitize --project "Kunde A" --names Server=server.txt --names User=konten.txt -r D:\Export\Logs
cli.bat sanitize --project "Kunde A"                      (erneuter Lauf mit den bereits erfassten Dateien)
cli.bat projects
cli.bat export-rules --project "Kunde A" regeln.json
cli.bat import-rules --project "Kunde B" regeln.json
cli.bat export-mapping --project "Kunde A" zuordnung.csv  (VERTRAULICH)
cli.bat serve --port 9000 --no-browser
```

`sanitize` zeigt am Ende den Status, die Prüfergebnisse und den Pfad zur Ausgabe an. Der Rückgabewert ist `0` nur bei „freigabefähig“.

## 7. Was wird erkannt?

| Automatisch | Beispiel | Ergebnis |
| --- | --- | --- |
| IPv4 / IPv6 | `10.20.1.15`, `fd00::5` | `[IP_1]`, `[IPv6_1]` |
| Hostnamen mit Domain | `srv01.firma.local` | `[Server_1].[Domain_1]` |
| Domains | `firma.local` | `[Domain_1]` |
| Windows-Konten | `FIRMA\m.muster` | `[Domain_2]\[User_1]` |
| E-Mail | `m.muster@firma.local` | `[User_1]@[Domain_1]` |
| UNC-Pfade | `\\fileserver\share` | `\\[Server_2]\share` |
| MAC-Adressen | `00:1a:2b:3c:4d:5e` | `[MAC_1]` |
| Domänen-SIDs | `S-1-5-21-…` | `[SID_1]` |
| Hostnamen in URLs | `http://intranet:8080/` | `http://[Server_3]:8080/` |
| Passwörter/Token | `password=Geheim1`, `"token": "…"`, `Authorization: Bearer …` | `[Secret_1]` |

**Nur über Namenslisten:** kurze Rechnernamen, Dienstkonten, Benutzernamen ohne Domain und Firmen- oder Projektnamen im Text.

Werte, die einmal erkannt wurden (z. B. `m.muster` aus `FIRMA\m.muster`), werden automatisch auch überall dort ersetzt, wo sie allein stehen.

## 8. Fehlerbehebung

| Problem | Lösung |
| --- | --- |
| Windows warnt beim Start („Computer wurde geschützt“) | ZIP vor dem Entpacken freigeben (Abschnitt 1, Schritt 4) oder *Weitere Informationen → Trotzdem ausführen*. |
| Programm startet nicht, Meldung zu blockierter Anwendung | Die IT-Richtlinie (z. B. AppLocker) verbietet eigene Programme. Mit der IT klären oder den Linux-Weg nutzen. |
| Linux: „Python 3.10 oder neuer wurde nicht gefunden“ | `python3 --version` prüfen. Auf älteren Systemen das Paket `python3.10` (oder neuer) installieren lassen. |
| Browser öffnet sich nicht | Link aus dem Konsolenfenster manuell öffnen. |
| „Bitte über den Startlink öffnen“ bzw. „Sitzung ungültig“ | Das Programm wurde neu gestartet, oder die Seite wurde ohne Startlink geöffnet (z. B. über ein Lesezeichen). Den aktuellen Link aus dem Konsolenfenster vollständig kopieren und öffnen. Ist das Fenster geschlossen, `start.bat` bzw. `start.sh` neu starten. |
| Port belegt | Das Programm nimmt automatisch den nächsten freien Port. Der Link im Fenster zeigt, welchen. |
| Lauf fehlgeschlagen: „Zeichenkodierung passt nicht“ | Im Reiter *Dateien* die Kodierung der Datei setzen, z. B. `cp1252` (ältere Windows-Programme), `latin-1` oder `utf-16-le+BOM`. |
| Lauf fehlgeschlagen: „vermutlich binär“ | Die Datei ist kein Textlog (z. B. `.evtx`, `.zip`). Vorher als Text exportieren oder aus dem Projekt entfernen. |
| Lauf fehlgeschlagen: JSON-Fehler | Im Reiter *Dateien* das Format auf **Text** stellen. Ersetzt wird dann trotzdem, nur ohne JSON-Strukturprüfung. |
| Status „Gesperrt“ | Restfunde ansehen. Fehlende Namen in die Namenslisten eintragen oder die Allowlist prüfen, dann neu laufen lassen. |
| Zu viel wird ersetzt (z. B. Produktnamen) | Wert in die Allowlist der passenden Kategorie eintragen, oder die Regel deaktivieren. |
| Sehr lange Laufzeit | Normal bei mehreren GB. Es werden alle Prozessorkerne genutzt (Richtwert: 5 GB in ca. 10–45 Minuten). |

## 9. Grundregeln

1. Nur Ausgaben mit Status **freigabefähig** weitergeben, und zwar nur den Ordner `output`.
2. Vor der Weitergabe eine **Stichprobe** ansehen.
3. Den `workspace`-Ordner, die Namenslisten und Zuordnungs-Exporte **nie** weitergeben.
4. Für Tests und Vorschau möglichst erfundene Beispieltexte verwenden.
