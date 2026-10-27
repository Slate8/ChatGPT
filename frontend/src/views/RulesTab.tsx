import { useEffect, useState } from "react";
import { api, download, type PreviewHit, type Rule, type RuleSet } from "../api";
import { HelpTooltip } from "../components/HelpTooltip";

const SAMPLE = `Oct 27 10:00:01 srv-app01.beispiel.local sshd[42]: Accepted password for BEISPIEL\\jdoe from 10.20.1.15
{"host": "dc01", "user": "max.muster@beispiel.local", "password": "Geheim123"}`;

const NEW_RULE: Rule = { id: "", name: "", pattern: "", category: "Server", kind: "literal", enabled: true, ignore_case: true, priority: 55, description: "", anchors: [] };

export function RulesTab({ slug }: { slug: string }) {
  const [rules, setRules] = useState<RuleSet | null>(null);
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const base = `/projects/${slug}`;

  useEffect(() => { api<RuleSet>("GET", `${base}/rules`).then(setRules).catch(e => setError(e.message)); }, [base]);
  if (!rules) return error ? <div className="notice error">{error}</div> : <p className="muted">Lade …</p>;

  const update = (next: RuleSet) => { setRules(next); setDirty(true); setMessage(""); };
  const updateRule = (index: number, patch: Partial<Rule>) => update({ ...rules, rules: rules.rules.map((r, i) => i === index ? { ...r, ...patch } : r) });
  const save = async (next = rules, success = "Regeln gespeichert.") => {
    setError(""); setMessage("");
    try {
      setRules(await api<RuleSet>("PUT", `${base}/rules`, next));
      setDirty(false); setEditing(null); setMessage(success);
    } catch (e) { setError((e as Error).message); }
  };
  const reset = async () => {
    if (!window.confirm("Alle Regeln auf die Standardregeln zurücksetzen?")) return;
    setRules(await api<RuleSet>("POST", `${base}/rules/reset`)); setDirty(false); setMessage("Standardregeln wiederhergestellt.");
  };
  const importFile = async (file: File) => {
    try { await save(JSON.parse(await file.text()) as RuleSet, "Regeln importiert."); }
    catch (e) { setError(`Import fehlgeschlagen: ${(e as Error).message}`); }
  };
  const addRule = () => {
    const id = `eigene-${Date.now().toString(36)}`;
    update({ ...rules, rules: [...rules.rules, { ...NEW_RULE, id, name: "Neue Regel" }] });
    setEditing(rules.rules.length);
  };

  return <div className="stack">
    <section className="panel wide">
      <div className="section-heading"><div><p className="eyebrow">ERKENNUNG</p><h3>Regeln</h3></div>
        <HelpTooltip label="Hilfe zu Regeln" help="Alle aktiven Regeln laufen gleichzeitig. Überschneiden sich Treffer, gewinnt die höhere Priorität, dann der längere Treffer. Benannte Gruppen wie (?P<Server>…) ersetzen nur den Gruppeninhalt mit der Gruppe als Kategorie." />
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Aktiv</th><th>Regel</th><th>Kategorie</th><th>Priorität</th><th /></tr></thead>
        <tbody>{rules.rules.map((rule, i) => <RuleRow key={rule.id || i} rule={rule} editing={editing === i}
          onToggleEdit={() => setEditing(editing === i ? null : i)} onChange={patch => updateRule(i, patch)}
          onDelete={() => { update({ ...rules, rules: rules.rules.filter((_, j) => j !== i) }); setEditing(null); }} />)}</tbody>
      </table></div>
      <div className="row"><button className="secondary-button" onClick={addRule}>+ Eigene Regel</button></div>
    </section>

    <section className="panel wide">
      <div className="section-heading"><div><p className="eyebrow">AUSNAHMEN & EINSTELLUNGEN</p><h3>Allowlist und JSON</h3></div></div>
      <div className="names-grid">
        {Object.entries(rules.allowlist).map(([category, values]) => <div key={category} className="names-col">
          <label htmlFor={`allow-${category}`}>Nie ersetzen: {category} <HelpTooltip label={`Hilfe zur Allowlist ${category}`} help="Diese Werte werden erkannt, aber bewusst nicht ersetzt (z. B. 127.0.0.1). Nur unkritische, öffentliche Werte eintragen." /></label>
          <textarea id={`allow-${category}`} rows={4} spellCheck={false} value={values.join("\n")} onChange={e => update({ ...rules, allowlist: { ...rules.allowlist, [category]: e.target.value.split("\n") } })} onBlur={() => update({ ...rules, allowlist: { ...rules.allowlist, [category]: values.map(v => v.trim()).filter(Boolean) } })} />
        </div>)}
        <div className="names-col">
          <label htmlFor="tlds">Top-Level-Domains <HelpTooltip label="Hilfe zu TLDs" help="Hostnamen und Domains werden nur erkannt, wenn sie auf eine dieser Endungen enden. Interne Endungen wie .local, .corp, .intern ergänzen. Dateinamen wie app.log bleiben dadurch unverändert." /></label>
          <textarea id="tlds" rows={4} spellCheck={false} value={rules.tlds.join(" ")} onChange={e => update({ ...rules, tlds: e.target.value.split(/[\s,]+/).filter(Boolean) })} />
        </div>
      </div>
      <label className="checkbox"><input type="checkbox" checked={rules.sanitize_json_keys} onChange={e => update({ ...rules, sanitize_json_keys: e.target.checked })} /> JSON-Schlüssel ebenfalls bereinigen
        <HelpTooltip label="Hilfe zu JSON-Schlüsseln" help="Empfohlen. Manche Exporte verwenden Hostnamen als Schlüssel, z. B. {&quot;dc01&quot;: {…}}. Ohne diese Option würden sie im Restscan gefunden und der Lauf gesperrt." /></label>
      <label htmlFor="secret-keys">JSON-Schlüssel für Geheimnisse (Regex) <HelpTooltip label="Hilfe zu Geheimnis-Schlüsseln" help="Der komplette Wert von JSON-Feldern, deren Name auf dieses Muster passt (z. B. password, token), wird als [Secret_n] ersetzt." /></label>
      <input id="secret-keys" className="mono" value={rules.json_secret_keys} onChange={e => update({ ...rules, json_secret_keys: e.target.value })} />
    </section>

    <div className="row end sticky-actions">
      {message && <span className="ok">{message}</span>}
      {error && <span className="bad" role="alert">{error}</span>}
      <button className="link-button" onClick={reset}>Standard wiederherstellen</button>
      <button className="secondary-button" onClick={() => download(`regeln-${slug}.json`, JSON.stringify(rules, null, 2))} title="Enthält keine Namenslisten und keine Zuordnungen">Exportieren</button>
      <label className="secondary-button file-button">Importieren<input type="file" accept=".json" onChange={e => e.target.files?.[0] && importFile(e.target.files[0])} /></label>
      <button className="primary-button" disabled={!dirty} onClick={() => save()}>Regeln speichern</button>
    </div>

    <Preview slug={slug} rules={dirty ? rules : null} />
  </div>;
}

function RuleRow({ rule, editing, onToggleEdit, onChange, onDelete }: {
  rule: Rule; editing: boolean; onToggleEdit: () => void; onChange: (patch: Partial<Rule>) => void; onDelete: () => void;
}) {
  return <>
    <tr className={rule.enabled ? "" : "disabled"}>
      <td><input type="checkbox" checked={rule.enabled} onChange={e => onChange({ enabled: e.target.checked })} aria-label={`${rule.name} aktiv`} /></td>
      <td><strong>{rule.name}</strong>{rule.description && <div className="muted small">{rule.description}</div>}</td>
      <td className="mono small">{rule.category || "(Gruppen)"}</td>
      <td>{rule.priority}</td>
      <td><button className="link-button" onClick={onToggleEdit}>{editing ? "Schließen" : "Bearbeiten"}</button></td>
    </tr>
    {editing && <tr className="edit-row"><td colSpan={5}><div className="edit-grid">
      <label>Name<input value={rule.name} onChange={e => onChange({ name: e.target.value })} /></label>
      <label>Art <HelpTooltip label="Hilfe zur Regelart" help="Literal: fester Text, ganze Wörter. Regex: regulärer Ausdruck (Python-Syntax); {LABEL} und {TLD} sind Platzhalter für Hostnamen-Teile und Domain-Endungen." />
        <select value={rule.kind} onChange={e => onChange({ kind: e.target.value as Rule["kind"] })}><option value="literal">Literal</option><option value="regex">Regex</option></select></label>
      <label>Kategorie <HelpTooltip label="Hilfe zur Kategorie" help="Bestimmt den Platzhalter, z. B. Server → [Server_1]. Nur Buchstaben und Ziffern. Bei Regex mit benannten Gruppen bestimmen die Gruppennamen die Kategorie." />
        <input value={rule.category} onChange={e => onChange({ category: e.target.value.replace(/[^A-Za-z0-9]/g, "") })} /></label>
      <label>Priorität <HelpTooltip label="Hilfe zur Priorität" help="Höhere Werte gewinnen bei überlappenden Treffern. Namenslisten haben 60, gelernte Werte 10." />
        <input type="number" value={rule.priority} onChange={e => onChange({ priority: Number(e.target.value) })} /></label>
      <label className="span-2">Muster<input className="mono" value={rule.pattern} onChange={e => onChange({ pattern: e.target.value })} spellCheck={false} /></label>
      <label className="checkbox"><input type="checkbox" checked={rule.ignore_case} onChange={e => onChange({ ignore_case: e.target.checked })} /> Groß-/Kleinschreibung ignorieren</label>
      <label>Anker (optional) <HelpTooltip label="Hilfe zu Ankern" help="Beschleunigung für große Dateien: kleingeschriebene Zeichenfolgen, von denen jeder Treffer mindestens eine enthält (z. B. @ für E-Mails). Die Regel läuft dann nur auf Zeilen mit Anker. Im Zweifel leer lassen." />
        <input className="mono" value={rule.anchors.join(" ")} onChange={e => onChange({ anchors: e.target.value.toLowerCase().split(/\s+/).filter(Boolean) })} /></label>
      <div className="row end span-2"><button className="link-button bad" onClick={onDelete}>Regel löschen</button></div>
    </div></td></tr>}
  </>;
}

function Preview({ slug, rules }: { slug: string; rules: RuleSet | null }) {
  const [text, setText] = useState(SAMPLE);
  const [result, setResult] = useState<{ output: string; hits: PreviewHit[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      api<{ output: string; hits: PreviewHit[] }>("POST", `/projects/${slug}/preview`, { text, rules })
        .then(r => { setResult(r); setError(""); }).catch(e => setError(e.message));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [slug, text, rules]);

  return <section className="panel wide">
    <div className="section-heading"><div><p className="eyebrow">TESTEN</p><h3>Vorschau</h3></div>
      <HelpTooltip label="Hilfe zur Vorschau" help="Testet die (auch ungespeicherten) Regeln an einem Beispieltext. Die Zuordnungstabelle wird dabei nicht verändert: bekannte Werte zeigen ihren Platzhalter, neue Werte erscheinen als [Kategorie_neu]. Möglichst synthetische Beispiele verwenden." />
    </div>
    <label htmlFor="preview-input">Beispieltext</label>
    <textarea id="preview-input" className="mono" rows={6} value={text} onChange={e => setText(e.target.value)} spellCheck={false} />
    {error && <div className="notice error" role="alert">{error}</div>}
    {result && <>
      <p className="eyebrow">ERGEBNIS</p>
      <pre className="preview-output">{result.output}</pre>
      <p className="eyebrow">TREFFER ({result.hits.length})</p>
      <ul className="hit-list">{result.hits.map((h, i) => <li key={i}>
        <span className="badge">{h.category}</span> <code>{h.text}</code> <span className="muted small">Regel {h.rule}{h.allowed ? " · Allowlist, bleibt" : h.known ? " · bekannt" : " · neu"}</span>
      </li>)}</ul>
    </>}
  </section>;
}
