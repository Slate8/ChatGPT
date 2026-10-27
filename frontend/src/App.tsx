import { useCallback, useEffect, useState } from "react";
import { api, formatDate, type ProjectSummary } from "./api";
import { HelpTooltip } from "./components/HelpTooltip";
import { helpTopics } from "./help/content";
import { ProjectView } from "./views/ProjectView";

type Tab = "projects" | "help";

export default function App() {
  const [tab, setTab] = useState<Tab>("projects");
  const [projectSlug, setProjectSlug] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "F1") { event.preventDefault(); setTab("help"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return <main className="app-shell">
    <header className="topbar">
      <div><p className="eyebrow">LOKAL · OFFLINE</p><h1>LogSanitizer</h1></div>
      <nav aria-label="Hauptnavigation" className="nav-tabs">
        <button className={tab === "projects" ? "active" : ""} onClick={() => { setTab("projects"); setProjectSlug(null); }}>Projekte</button>
        <button className={tab === "help" ? "active" : ""} onClick={() => setTab("help")} title="Hilfe (F1)">Hilfe</button>
      </nav>
    </header>
    {tab === "help" ? <HelpPage /> : projectSlug
      ? <ProjectView slug={projectSlug} onBack={() => setProjectSlug(null)} />
      : <ProjectList onOpen={setProjectSlug} />}
    <footer><span>LogSanitizer · 0.1.0-dev</span><span>Ein bestandener Restscan senkt das Risiko, beweist aber nicht, dass alle sensiblen Daten erkannt wurden.</span></footer>
  </main>;
}

function ProjectList({ onOpen }: { onOpen: (slug: string) => void }) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<ProjectSummary[]>("GET", "/projects").then(setProjects).catch(e => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const create = async () => {
    setError("");
    try {
      const project = await api<{ slug: string }>("POST", "/projects", { name });
      setName("");
      onOpen(project.slug);
    } catch (e) { setError((e as Error).message); }
  };

  return <>
    <section className="hero">
      <span className="status-pill"><span className="status-dot" /> Läuft nur auf diesem Rechner</span>
      <h2>Logs sicher vorbereiten.</h2>
      <p>Interne Namen, IP-Adressen und Zugangsdaten werden durch konsistente Platzhalter ersetzt. Originaldateien bleiben unverändert.</p>
    </section>
    {error && <div className="notice error" role="alert"><strong>Fehler</strong><span>{error}</span></div>}
    <section className="panel">
      <div className="section-heading"><div><p className="eyebrow">NEUES PROJEKT</p><h3>Projekt anlegen</h3></div>
        <HelpTooltip label="Hilfe zu Projekten" help="Ein Projekt bündelt Logdateien, Regeln, Namenslisten und die Zuordnungstabelle. Gleiche Werte erhalten innerhalb eines Projekts immer denselben Platzhalter – auch über spätere Läufe hinweg." />
      </div>
      <label htmlFor="project-name">Projektname</label>
      <div className="row">
        <input id="project-name" value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === "Enter" && name.trim() && create()} placeholder="z. B. Kunde A – Störung Oktober" maxLength={80} />
        <button className="primary-button" disabled={!name.trim()} onClick={create}>Anlegen</button>
      </div>
    </section>
    <section className="panel wide">
      <p className="eyebrow">VORHANDENE PROJEKTE</p>
      {projects === null ? <p className="muted">Lade …</p> : projects.length === 0 ? <p className="muted">Noch keine Projekte.</p> :
        <ul className="list">{projects.map(p => <li key={p.slug}>
          <button className="list-item" onClick={() => onOpen(p.slug)}>
            <strong>{p.name}</strong><span className="muted">{p.sources} Datei(en) · angelegt {formatDate(p.created)}</span>
          </button>
        </li>)}</ul>}
    </section>
  </>;
}

function HelpPage() {
  return <section className="help-page"><p className="eyebrow">OFFLINE-HANDBUCH</p><h2>Hilfe und Grundlagen</h2>
    <p className="intro">Diese Hilfe ist lokal eingebunden und jederzeit mit F1 erreichbar.</p>
    <div className="help-list">{helpTopics.map(topic => <article className="help-topic" key={topic.id} id={`help-${topic.id}`}><h3>{topic.title}</h3><p>{topic.summary}</p><ul>{topic.steps.map(step => <li key={step}>{step}</li>)}</ul></article>)}</div>
  </section>;
}
