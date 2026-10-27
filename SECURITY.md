# Security policy

## Status
LogSanitizer is a pre-release that has not been independently security-reviewed. Check sanitized output by sample before sharing it.

## Reporting
Report suspected vulnerabilities privately to the repository owner. Do not create issues containing secrets, log excerpts, credentials, mapping tables, or personal data.

## Principles
- Processing stays local; the server binds to 127.0.0.1 and requires a per-start session token.
- Never commit real logs, credentials, tokens, name lists, mappings, databases, or generated outputs.
- The `workspace/` folder (name lists, mapping, run reports) is confidential and must not leave the internal network.
- Do not include sensitive content in diagnostics or audit metadata.
- Preserve source files and block incomplete or failed outputs from release.
- A successful validation scan does not prove every sensitive value was detected.
