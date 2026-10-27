# Frontend

Requires Node.js 20 or later for development only. The built files in `dist/` are served by the Python backend; Node.js is not needed on the target systems.

```bash
npm ci
npm test
npm run build
```

For UI work, run `npm run build -- --watch` and start the backend (`python -m logsanitizer serve`). The session token in the start link is required for all API calls.

All help texts are bundled locally (`src/help/content.ts`, `HelpTooltip`); no external assets.
