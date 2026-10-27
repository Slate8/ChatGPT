import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Simulates opening the app via its start link (read when api.ts is imported).
window.location.hash = "#token=test-token";

afterEach(cleanup);
