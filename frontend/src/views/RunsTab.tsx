import { useCallback, useEffect, useState } from "react";
import { api, formatBytes, formatDate, type ProjectInfo, type RunReport, type RunSummary } from "../api";
import { HelpTooltip } from "../components/HelpTooltip";

export const STATUS_LABELS: Record<string, [string, string]> = {
  ready: ["Freigabefähig", "ok"],
  blocked: ["Gesperrt", "bad"],
  failed: ["Fehlgeschlagen", "bad"],
  cancelled: ["Abgebrochen", "warn"],
  running: ["Läuft", "warn"],
};
const PHASES: Record<string, string> = { start: "Start", scan: "Analyse", write: "Schreiben", validate: "Prüfung", done: "Fertig" };

export function RunsTab({ project, onChange }: { project: ProjectInfo; onChange: () => void }) {
  const base = `/projects/${project.slug}`;
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(project.active_run);
  const [report, setReport] = useState<RunReport | null>(null);
  const [error, setError] = useState("");

  const loadRuns = useCallback(() => api<RunSummary[]>("GET", `${base}/runs`).then(r => {
    setRuns(r);
    setSelected(s => s ?? r[0]?.run_id ?? null);
  }).catch(e => setError(e.message)), [base]);
  useEffect(() => { loadRuns(); }, [loadRuns]);

  useEffect(() => {
    if (!selected) return;
    let timer = 0;
    let stopped = false;
    const poll = async () => {
      try {
        const r = await api<RunReport>("GET", `${base}/runs/${selected}`);
        if (stopped) return;
        setReport(r);
        if (r.status === "running") timer = window.setTimeout(poll, 500);
        else { loadRuns(); onChange(); }
      } catch (e) { setError((e as Error).message); }
    };
    poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [base, selected, loadRuns, onChange]);

  const start = async () => {
    setError("");
    try {
      const { run_id } = await api<{ run_id: string }>("POST", `${base}/runs`);
      setSelected(run_id);
    } catch (e) { setError((e as Error).message); }
  };
  const running = report?.status === "running";

  return <div className="stack">
    <section className="panel wide">
      <div className="section-heading"><div><p className="eyebrow">VERARBEITUNG</p><h3>Neuer Lauf</h3></div>
        <HelpTooltip label="Hilfe zu Läufen" help="Ein Lauf liest alle Dateien zweimal (Werte sammeln, dann ersetzen) und prüft die Ausgabe danach mit einem Restscan. Nur wenn alle Pflichtprüfungen bestehen, entsteht ein Ausgabeordner. Gesperrte Ausgaben dürfen nicht weitergegeben werden." />
      </div>
      <p className="muted">{project.sources.length} Datei(en), {formatBytes(project.sources.reduce((s, f) => s + f.size, 0))}. Originale bleiben unverändert.</p>
      <div className="row">
        <button className="primary-button" disabled={running || !project.sources.length} onClick={start}>Lauf starten</button>
        {running && <button className="secondary-button" onClick={() => api("POST", `${base}/runs/${selected}/cancel`)}>Abbrechen</button>}
      </div>
      {error && <div className="notice error" role="alert">{error}</div>}
    </section>

    {report && <RunDetails report={report} onOpen={() => api("POST", `${base}/runs/${report.run_id}/open`).catch(e => setError(e.message))} />}

    <section className="panel wide">
      <p className="eyebrow">VERLAUF</p>
      {runs.length === 0 ? <p className="muted">Noch keine Läufe.</p> :
        <ul className="list">{runs.map(r => <li key={r.run_id}>
          <button className={`list-item ${r.run_id === selected ? "selected" : ""}`} onClick={() => setSelected(r.run_id)}>
            <StatusBadge status={r.status} /> <span className="mono">{r.run_id}</span>
            <span className="muted small">{formatDate(r.started)}{r.summary ? ` · ${r.summary.files} Dateien · ${r.summary.residual_hits} Restfunde` : ""}</span>
          </button>
        </li>)}</ul>}
    </section>
  </div>;
}

function StatusBadge({ status }: { status: string }) {
  const [label, tone] = STATUS_LABELS[status] ?? [status, ""];
  return <span className={`badge ${tone}`}>{label}</span>;
}

function RunDetails({ report, onOpen }: { report: RunReport; onOpen: () => void }) {
  const progress = report.progress;
  return <section className="panel wide">
    <div className="section-heading"><div><p className="eyebrow">LAUF {report.run_id}</p><h3><StatusBadge status={report.status} /></h3></div>
      {(report.status === "ready" || report.status === "blocked") && <button className="secondary-button" onClick={onOpen}>{report.status === "ready" ? "Ausgabeordner öffnen" : "Gesperrte Ausgabe ansehen"}</button>}
    </div>
    {report.status === "running" && progress && <div className="progress" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-bar" style={{ width: `${progress.percent}%` }} />
      <span>{PHASES[progress.phase] ?? progress.phase} {progress.file ?? ""} · {progress.percent.toFixed(1)} %</span>
    </div>}
    {report.status === "ready" && <div className="notice ok-notice"><strong>Alle Pflichtprüfungen bestanden.</strong><span>Vor der Weitergabe trotzdem stichprobenartig prüfen – der Restscan findet nur, was Regeln, Namenslisten und Zuordnungen kennen.</span></div>}
    {report.status === "blocked" && <div className="notice error"><strong>Nicht freigegeben.</strong><span>Die Ausgabe liegt in „output.blocked“ und darf nicht weitergegeben werden. Regeln oder Namenslisten anpassen und neuen Lauf starten.</span></div>}
    {report.errors.map(e => <div key={e} className="notice error" role="alert">{e}</div>)}
    {report.checks.length > 0 && <ul className="checks">{report.checks.map(c => <li key={c.name} className={c.passed ? "ok" : "bad"}>{c.passed ? "✓" : "✗"} {c.name}: <span className="muted">{c.detail}</span></li>)}</ul>}
    {report.summary && <p className="muted small">Ersetzungen: {Object.entries(report.summary.replacements).map(([c, n]) => `${c} ${n}`).join(" · ") || "keine"} · neue Platzhalter: {report.summary.new_mappings}{report.workers ? ` · ${report.workers} Prozess(e)` : ""}</p>}
    {report.residual_hits.length > 0 && <>
      <p className="eyebrow">RESTFUNDE (VERTRAULICH)</p>
      <div className="table-wrap"><table><thead><tr><th>Datei</th><th>Zeile</th><th>Kategorie</th><th>Wert</th><th>Prüfung</th></tr></thead>
        <tbody>{report.residual_hits.map((h, i) => <tr key={i}><td className="mono small">{h.file}</td><td>{h.line}</td><td>{h.category}</td><td className="mono">{h.value}</td><td className="small">{h.check === "rules" ? "Regel" : "bekannter Wert"}</td></tr>)}</tbody></table></div>
    </>}
    {report.files.length > 0 && <details><summary>Dateien ({report.files.length})</summary>
      <div className="table-wrap"><table><thead><tr><th>Ausgabe</th><th>Format</th><th>Kodierung</th><th>Größe</th><th>Ersetzungen</th></tr></thead>
        <tbody>{report.files.map(f => <tr key={f.output}><td className="mono small">{f.output}</td><td>{f.format}</td><td>{f.encoding}</td><td>{formatBytes(f.bytes)}</td><td>{f.replacements ? Object.values(f.replacements).reduce((a, b) => a + b, 0) : "–"}</td></tr>)}</tbody></table></div>
    </details>}
  </section>;
}
