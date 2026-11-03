# Security and limitations

This is a single-user local prototype. Do not expose the Flask server online. The `local-curator` audit label is not an authenticated employee identity, and audience labels are not SSO.

The process operator selects the SQLite file, audience labels and trusted profile directory. Browsers cannot select filesystem paths, model endpoints or user groups. Loopback/Host/Origin checks, a per-process request token, no-store headers and a content-security policy limit the local attack surface; they do not provide a production security architecture.

Data and model output are untrusted. UI text is rendered using text nodes. JSON schemas forbid extra fields and remote references. Factual edge proposals require exact source excerpts and matching revisions; this does not prove logical validity. The optional local model has no tool access, download permission, web search or cloud fallback. Ollama is a separately administered local service; check its own logging and model configuration.

Source access is filtered before views, counts and candidate retrieval. Generated classifications use context accessible to all audiences of the source. A malicious authorized curator can still type or copy information into a broader node; preventing deliberate disclosure requires real organizational controls. The prototype is not a multi-tenant authorization product.

SQLite workspaces, exports and custom profile files may contain sensitive material. Keep them outside public Git commits and back them up under appropriate access controls. Use only the synthetic demo in screenshots and public bug reports.

Report vulnerabilities privately to repository maintainers or through GitHub Security advisories if enabled. Do not publish real internal content or credentials in an issue.
