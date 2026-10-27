/** Client for the local LogSanitizer API. The session token comes from the start URL. */

const TOKEN_KEY = "logsanitizer-token";

function readToken(): string {
  const match = window.location.hash.match(/token=([\w-]+)/);
  if (match) {
    try { sessionStorage.setItem(TOKEN_KEY, match[1]); } catch { /* storage unavailable */ }
    history.replaceState(null, "", window.location.pathname);
    return match[1];
  }
  try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}

const token = readToken();

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { "X-Session-Token": token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.error ?? `Fehler ${response.status}`, response.status);
  return data as T;
}

export type Source = { id: string; path: string; rel: string; format: string; encoding: string; size: number; exists: boolean };
export type ProjectInfo = {
  slug: string; name: string; created: string; dir: string; formats: string[];
  sources: Source[]; names: Record<string, number>; mapping: Record<string, number>; active_run: string | null;
};
export type ProjectSummary = { slug: string; name: string; created: string; sources: number };
export type Rule = {
  id: string; name: string; pattern: string; category: string; kind: "regex" | "literal";
  enabled: boolean; ignore_case: boolean; priority: number; description: string; anchors: string[];
};
export type RuleSet = {
  format: string; version: number; rules: Rule[]; tlds: string[];
  allowlist: Record<string, string[]>; json_secret_keys: string; sanitize_json_keys: boolean;
};
export type PreviewHit = { start: number; end: number; category: string; text: string; rule: string; allowed: boolean; known: boolean };
export type Check = { name: string; passed: boolean; detail: string };
export type RunFile = { source: string; output: string; format: string; encoding: string; bytes: number; lines?: number; replacements?: Record<string, number>; residual_hits?: number };
export type ResidualHit = { file: string; line: number; category: string; value: string; check: string };
export type RunReport = {
  run_id: string; status: string; started: string; finished: string | null; workers?: number;
  files: RunFile[]; checks: Check[]; residual_hits: ResidualHit[]; errors: string[];
  summary?: { files: number; bytes: number; replacements: Record<string, number>; new_mappings: number; residual_hits: number };
  progress?: { phase: string; file?: string; percent: number };
};
export type RunSummary = Pick<RunReport, "run_id" | "status" | "started" | "finished" | "summary">;
export type MappingRow = { placeholder: string; category: string; original: string; run_id: string; created: string };
export type FsEntry = { name: string; path: string; dir: boolean; size: number | null };
export type FsListing = { path: string; parent: string | null; entries: FsEntry[] };

export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return `${value.toLocaleString("de-DE", { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
}

export function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("de-DE") : "–";
}

export function download(filename: string, content: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
