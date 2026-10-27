import { useState } from "react";
import { api, download, type MappingRow } from "../api";
import { HelpTooltip } from "../components/HelpTooltip";

export function MappingTab({ slug }: { slug: string }) {
  const [rows, setRows] = useState<MappingRow[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  const reveal = () => api<MappingRow[]>("GET", `/projects/${slug}/mapping`).then(setRows).catch(e => setError(e.message));
  const exportCsv = () => {
    if (!rows || !window.confirm("Die Zuordnungstabelle enthält alle Originalwerte. Datei wirklich speichern? Sie darf das interne Netz nicht verlassen.")) return;
    const quote = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const csv = ["Platzhalter;Kategorie;Original;Lauf;Erstellt", ...rows.map(r => [r.placeholder, r.category, r.original, r.run_id, r.created].map(quote).join(";"))].join("\r\n");
    download(`zuordnung-${slug}-VERTRAULICH.csv`, "﻿" + csv, "text/csv");
  };

  const needle = filter.toLowerCase();
  const visible = rows?.filter(r => !needle || r.placeholder.toLowerCase().includes(needle) || r.original.includes(needle));

  return <div className="stack">
    <div className="notice warn"><strong>Streng vertraulich</strong><span>Die Zuordnung verbindet Platzhalter mit Originalwerten. Sie wird nur lokal angezeigt und ist nie Teil von Ausgaben oder Regel-Exporten.</span></div>
    <section className="panel wide">
      <div className="section-heading"><div><p className="eyebrow">ZUORDNUNG</p><h3>Platzhalter ↔ Original</h3></div>
        <HelpTooltip label="Hilfe zur Zuordnung" help="Hiermit lassen sich Rückfragen zu bereinigten Logs intern beantworten, z. B. welcher Server [Server_3] ist. Platzhalter bleiben im Projekt dauerhaft gleich." />
      </div>
      {!rows ? <button className="secondary-button" onClick={reveal}>Zuordnung anzeigen</button> : <>
        <div className="row">
          <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Suchen, z. B. [Server_3] oder dc01" aria-label="Zuordnung durchsuchen" />
          <button className="secondary-button" onClick={() => setRows(null)}>Ausblenden</button>
          <button className="secondary-button" onClick={exportCsv}>CSV exportieren</button>
        </div>
        <p className="muted small">{visible!.length} von {rows.length} Einträgen</p>
        <div className="table-wrap"><table><thead><tr><th>Platzhalter</th><th>Original</th><th>Lauf</th></tr></thead>
          <tbody>{visible!.slice(0, 1000).map(r => <tr key={r.placeholder}><td className="mono">{r.placeholder}</td><td className="mono">{r.original}</td><td className="mono small">{r.run_id}</td></tr>)}</tbody></table></div>
      </>}
      {error && <div className="notice error" role="alert">{error}</div>}
    </section>
  </div>;
}
