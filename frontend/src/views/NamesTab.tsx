import { useEffect, useState } from "react";
import { api } from "../api";
import { HelpTooltip } from "../components/HelpTooltip";

const DEFAULT_CATEGORIES = ["Server", "User", "Domain"];
const CATEGORY_HELP: Record<string, string> = {
  Server: "Kurze Hostnamen ohne Domain, z. B. dc01, fileserver. Sie sind nicht automatisch erkennbar.",
  User: "Benutzer- und Dienstkonten, z. B. svc_backup, die nicht als DOMAIN\\Benutzer oder E-Mail vorkommen.",
  Domain: "Interne Domain- oder Firmennamen, z. B. NORDWERK oder nordwerk.",
};

export function NamesTab({ slug }: { slug: string }) {
  const [texts, setTexts] = useState<Record<string, string> | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Record<string, string[]>>("GET", `/projects/${slug}/names`).then(names => {
      const merged: Record<string, string> = {};
      for (const c of [...DEFAULT_CATEGORIES, ...Object.keys(names)]) merged[c] = (names[c] ?? []).join("\n");
      setTexts(merged);
    }).catch(e => setError(e.message));
  }, [slug]);

  if (!texts) return error ? <div className="notice error">{error}</div> : <p className="muted">Lade …</p>;

  const save = async () => {
    setError(""); setMessage("");
    const body = Object.fromEntries(Object.entries(texts).map(([c, t]) => [c, t.split(/\r?\n/).map(v => v.trim()).filter(Boolean)]));
    try {
      await api("PUT", `/projects/${slug}/names`, body);
      setMessage("Gespeichert.");
    } catch (e) { setError((e as Error).message); }
  };

  const importFile = async (category: string, file: File) => {
    const content = await file.text();
    const values = content.split(/\r?\n/).map(l => l.split(/[;,\t]/)[0].trim()).filter(l => l && !l.startsWith("#"));
    setTexts(t => ({ ...t!, [category]: [t![category], ...values].filter(Boolean).join("\n") }));
  };

  return <div className="stack">
    <div className="notice warn"><strong>Vertraulich</strong><span>Namenslisten enthalten interne Namen. Sie bleiben im Projektordner und sind nie Teil von Regel-Exporten oder Ausgaben.</span></div>
    <section className="panel wide">
      <div className="section-heading"><div><p className="eyebrow">BEKANNTE NAMEN</p><h3>Namenslisten</h3></div>
        <HelpTooltip label="Hilfe zu Namenslisten" help="Ein Eintrag pro Zeile, Groß-/Kleinschreibung egal. Jeder Treffer wird durch einen Platzhalter der Kategorie ersetzt, z. B. [Server_3]. Werte, die einmal erkannt wurden, werden zusätzlich automatisch überall ersetzt." />
      </div>
      <div className="names-grid">
        {Object.entries(texts).map(([category, text]) => <div key={category} className="names-col">
          <label htmlFor={`names-${category}`}>{category} <span className="muted small">({text.split("\n").filter(v => v.trim()).length})</span>
            {CATEGORY_HELP[category] && <HelpTooltip label={`Hilfe zu ${category}`} help={CATEGORY_HELP[category]} />}</label>
          <textarea id={`names-${category}`} rows={10} value={text} spellCheck={false} onChange={e => setTexts({ ...texts, [category]: e.target.value })} />
          <label className="file-input small">Aus Datei ergänzen (TXT/CSV)
            <input type="file" accept=".txt,.csv" onChange={e => e.target.files?.[0] && importFile(category, e.target.files[0])} /></label>
        </div>)}
      </div>
      <div className="row">
        <input value={newCategory} onChange={e => setNewCategory(e.target.value.replace(/[^A-Za-z0-9]/g, ""))} placeholder="Weitere Kategorie, z. B. Kunde" aria-label="Neue Kategorie" maxLength={32} />
        <button className="secondary-button" disabled={!/^[A-Za-z]/.test(newCategory) || newCategory in texts} onClick={() => { setTexts({ ...texts, [newCategory]: "" }); setNewCategory(""); }}>Kategorie hinzufügen</button>
      </div>
      <div className="row end">
        {message && <span className="ok">{message}</span>}
        {error && <span className="bad" role="alert">{error}</span>}
        <button className="primary-button" onClick={save}>Namenslisten speichern</button>
      </div>
    </section>
  </div>;
}
