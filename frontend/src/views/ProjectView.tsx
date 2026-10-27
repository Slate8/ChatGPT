import { useCallback, useEffect, useState } from "react";
import { api, type ProjectInfo } from "../api";
import { FilesTab } from "./FilesTab";
import { MappingTab } from "./MappingTab";
import { NamesTab } from "./NamesTab";
import { RulesTab } from "./RulesTab";
import { RunsTab } from "./RunsTab";

const TABS = [
  ["files", "Dateien"],
  ["names", "Namenslisten"],
  ["rules", "Regeln & Vorschau"],
  ["runs", "Läufe"],
  ["mapping", "Zuordnung"],
] as const;
type TabId = typeof TABS[number][0];

export function ProjectView({ slug, onBack }: { slug: string; onBack: () => void }) {
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [tab, setTab] = useState<TabId>("files");
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    api<ProjectInfo>("GET", `/projects/${slug}`).then(setProject).catch(e => setError(e.message));
  }, [slug]);
  useEffect(reload, [reload]);

  if (!project) return <section className="page">{error ? <div className="notice error" role="alert">{error}</div> : <p className="muted">Lade …</p>}</section>;

  return <section className="page">
    <button className="link-button" onClick={onBack}>← Alle Projekte</button>
    <div className="project-head">
      <div><p className="eyebrow">PROJEKT</p><h2>{project.name}</h2></div>
      <p className="muted small">Projektordner (vertraulich): <code>{project.dir}</code></p>
    </div>
    <nav className="sub-tabs" aria-label="Projektbereiche">
      {TABS.map(([id, label]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => { setTab(id); reload(); }}>{label}</button>)}
    </nav>
    {tab === "files" && <FilesTab project={project} onChange={setProject} />}
    {tab === "names" && <NamesTab slug={slug} />}
    {tab === "rules" && <RulesTab slug={slug} />}
    {tab === "runs" && <RunsTab project={project} onChange={reload} />}
    {tab === "mapping" && <MappingTab slug={slug} />}
  </section>;
}
