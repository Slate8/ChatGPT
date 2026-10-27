import { useEffect, useState } from "react";
import { api, formatBytes, type FsListing, type ProjectInfo } from "../api";
import { HelpTooltip } from "../components/HelpTooltip";

const FORMAT_LABELS: Record<string, string> = { auto: "Automatisch", text: "Text", json: "JSON-Dokument", jsonl: "JSON Lines" };

export function FilesTab({ project, onChange }: { project: ProjectInfo; onChange: (p: ProjectInfo) => void }) {
  const [path, setPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [browsing, setBrowsing] = useState(false);
  const [error, setError] = useState("");
  const base = `/projects/${project.slug}`;

  const run = async (action: () => Promise<ProjectInfo>) => {
    setError("");
    try { onChange(await action()); } catch (e) { setError((e as Error).message); }
  };
  const add = (paths: string[]) => run(async () => {
    const result = await api<{ project: ProjectInfo }>("POST", `${base}/sources`, { paths, recursive });
    setPath("");
    return result.project;
  });

  const total = project.sources.reduce((sum, s) => sum + s.size, 0);

  return <div className="stack">
    <section className="panel wide">
      <div className="section-heading"><div><p className="eyebrow">QUELLEN</p><h3>Dateien hinzufügen</h3></div>
        <HelpTooltip label="Hilfe zu Quellen" help="Dateien werden nur gelesen, nie verändert oder verschoben. Große Dateien werden nicht hochgeladen, sondern direkt vom Datenträger gelesen. Ordner können rekursiv eingelesen werden." />
      </div>
      <label htmlFor="source-path">Datei- oder Ordnerpfad</label>
      <div className="row">
        <input id="source-path" value={path} onChange={e => setPath(e.target.value)} placeholder="z. B. D:\Export\Logs" onKeyDown={e => e.key === "Enter" && path.trim() && add([path])} />
        <button className="secondary-button" onClick={() => setBrowsing(true)}>Durchsuchen …</button>
        <button className="primary-button" disabled={!path.trim()} onClick={() => add([path])}>Hinzufügen</button>
      </div>
      <label className="checkbox"><input type="checkbox" checked={recursive} onChange={e => setRecursive(e.target.checked)} /> Unterordner einbeziehen
        <HelpTooltip label="Hilfe zu Unterordnern" help="Bei Ordnern werden auch alle Dateien in Unterordnern hinzugefügt. Die Ordnerstruktur bleibt in der Ausgabe erhalten." /></label>
      {error && <div className="notice error" role="alert">{error}</div>}
    </section>
    {browsing && <FileBrowser onClose={() => setBrowsing(false)} onPick={paths => { setBrowsing(false); add(paths); }} />}
    <section className="panel wide">
      <p className="eyebrow">{project.sources.length} DATEI(EN) · {formatBytes(total)}</p>
      {project.sources.length === 0 ? <p className="muted">Noch keine Dateien.</p> :
        <div className="table-wrap"><table>
          <thead><tr><th>Ausgabepfad</th><th>Größe</th>
            <th>Format <HelpTooltip label="Hilfe zum Format" help="Automatisch erkennt JSON Lines (ein JSON-Objekt pro Zeile), JSON-Dokumente (.json) und Text. Bei JSON werden nur Zeichenketten verändert, die Struktur bleibt exakt erhalten. Binärdateien werden abgelehnt." /></th>
            <th>Kodierung <HelpTooltip label="Hilfe zur Kodierung" help="Automatisch: BOM, UTF-16, UTF-8, sonst Windows-1252. Die Ausgabe verwendet dieselbe Kodierung. Bei Fehlern manuell setzen, z. B. utf-8, cp1252, latin-1, utf-16-le+BOM." /></th><th /></tr></thead>
          <tbody>{project.sources.map(s => <tr key={s.id} className={s.exists ? "" : "missing"}>
            <td title={s.path}><span className="mono">{s.rel}</span>{!s.exists && <span className="badge bad">fehlt</span>}<div className="muted small mono">{s.path}</div></td>
            <td>{formatBytes(s.size)}</td>
            <td><select value={s.format} aria-label={`Format für ${s.rel}`} onChange={e => run(() => api("PATCH", `${base}/sources/${s.id}`, { format: e.target.value }))}>
              {project.formats.map(f => <option key={f} value={f}>{FORMAT_LABELS[f] ?? f}</option>)}</select></td>
            <td><input className="compact" defaultValue={s.encoding} aria-label={`Kodierung für ${s.rel}`} onBlur={e => e.target.value !== s.encoding && run(() => api("PATCH", `${base}/sources/${s.id}`, { encoding: e.target.value.trim() || "auto" }))} /></td>
            <td><button className="link-button" onClick={() => run(() => api("DELETE", `${base}/sources/${s.id}`))}>Entfernen</button></td>
          </tr>)}</tbody>
        </table></div>}
    </section>
  </div>;
}

function FileBrowser({ onClose, onPick }: { onClose: () => void; onPick: (paths: string[]) => void }) {
  const [listing, setListing] = useState<FsListing | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");

  const open = (path: string) => {
    setError("");
    setSelected([]);
    api<FsListing>("GET", `/fs?path=${encodeURIComponent(path)}`).then(setListing).catch(e => setError(e.message));
  };
  useEffect(() => open(""), []);

  const toggle = (path: string) => setSelected(s => s.includes(path) ? s.filter(p => p !== path) : [...s, path]);

  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Dateien auswählen" onKeyDown={e => e.key === "Escape" && onClose()}>
    <div className="modal">
      <div className="section-heading"><div><p className="eyebrow">DURCHSUCHEN</p><h3 className="mono path">{listing?.path || "Laufwerke"}</h3></div>
        <button className="link-button" onClick={onClose} autoFocus>Schließen</button></div>
      {error && <div className="notice error" role="alert">{error}</div>}
      <ul className="browser">
        {listing?.parent !== null && listing?.parent !== undefined && <li><button className="list-item" onClick={() => open(listing.parent ?? "")}>⬑ Übergeordneter Ordner</button></li>}
        {listing?.entries.map(e => <li key={e.path} className="browser-row">
          <input type="checkbox" checked={selected.includes(e.path)} onChange={() => toggle(e.path)} aria-label={`${e.name} auswählen`} disabled={!listing.path} />
          {e.dir ? <button className="list-item" onClick={() => open(e.path)}>📁 {e.name}</button>
            : <span className="list-item static">{e.name}<span className="muted small">{e.size !== null ? formatBytes(e.size) : ""}</span></span>}
        </li>)}
      </ul>
      <div className="row end">
        {listing?.path && <button className="secondary-button" onClick={() => onPick([listing.path])}>Diesen Ordner hinzufügen</button>}
        <button className="primary-button" disabled={!selected.length} onClick={() => onPick(selected)}>{selected.length} Auswahl hinzufügen</button>
      </div>
    </div>
  </div>;
}
