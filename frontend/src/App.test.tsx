import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import App from "./App";

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = url.replace(/^\/api/, "");
    const body = routes[path];
    return { ok: body !== undefined, status: body !== undefined ? 200 : 404, json: async () => body ?? { error: "nicht gefunden" } };
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("LogSanitizer app", () => {
  it("lists projects from the local API", async () => {
    mockApi({ "/projects": [{ slug: "kunde-a", name: "Kunde A", created: "2026-10-27T10:00:00+00:00", sources: 3 }] });
    render(<App />);
    expect(await screen.findByText("Kunde A")).toBeInTheDocument();
    expect(screen.getByText(/3 Datei\(en\)/)).toBeInTheDocument();
  });

  it("shows API errors", async () => {
    mockApi({});
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("nicht gefunden");
  });

  it("opens the offline help with F1", async () => {
    mockApi({ "/projects": [] });
    render(<App />);
    fireEvent.keyDown(window, { key: "F1" });
    expect(await screen.findByRole("heading", { name: "Hilfe und Grundlagen" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Was wird erkannt?" })).toBeInTheDocument();
  });
});
