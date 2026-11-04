# Integration methods

## Standalone local application

Run the CLI server on loopback and explore the browser. It persists changes locally in SQLite. This is the implemented demonstration; no hosting or company login is configured.

## Python library

Use `Graph` for transactions and views, and `workflow.propose` / `workflow.apply` for suggestions. The caller supplies trusted audience labels and, optionally, a trusted profile directory. The application is responsible for authenticating users and determining those labels. Never let an untrusted browser select another user's audiences.

## Local HTTP API

GET `/api/config` returns a per-process local request token. Send it as `X-Graph-Token` with JSON POST requests. This is cross-origin protection for localhost, not user authentication.

| Endpoint | Purpose |
| --- | --- |
| GET `/api/view?focus=ID&mode=children&proposed=true` | Bounded view; modes: children, neighbors, foundations, evidence, search |
| GET `/api/node/ID` | Content and visible relationships for one node |
| GET `/api/review` | First 100 proposed/stale relationships for local review |
| POST `/api/node` | `{node: {...}, parent: "topic-id"}`; create a node |
| POST `/api/revise/ID` | `{revision: 1, changes: {...}}`; optimistic content update |
| POST `/api/propose/ID` | `{}`; create a suggestion artifact |
| POST `/api/apply/PROPOSAL_ID` | `{}`; save its proposed edges |
| POST `/api/review/EDGE_ID` | `{decision: "accepted", revision: GRAPH_REVISION}` |
| POST `/api/edge` | `{edge: {...}}`; direct local-curator placement or semantic proposal |
| GET `/api/export` | Current permitted graph snapshot, without full history |

The process operator chooses database, model, audiences and profile directory. Requests cannot choose those settings. The API accepts no filesystem paths or arbitrary model endpoints. It binds to loopback, checks Host/Origin, applies a content-security policy and disables caching. No CORS is enabled.

## Relationship to the other repositories

- Document Formatter prepares structured documents; a future adapter can publish approved document revisions into this graph.
- Reading Assistant retrieves relevant passages; graph neighborhoods can later improve candidate retrieval. Its keyword suggestions must retain their provisional status.
- Docusaurus presents approved knowledge. Decap or another editing interface can open this component as a separate local companion initially.

These are versioned integration boundaries, not completed automatic integrations. A public static Docusaurus build must not include internal graph data or private graph-derived counts. Hosting will require authenticated APIs, private storage, reviewer identity, appropriate rate limits and access-aware caching.

## Backup and maintenance

Stop the local server and copy the SQLite file plus custom profile files to a controlled backup location. The code repository is not a backup of knowledge data. Test restore periodically. Do not commit live databases, private exports or credentials. The browser Export is a convenient current snapshot, not a full database/history backup.

### Inspection endpoints

- `GET /api/node/<id>`: full selected node, short excerpt, accepted direct-child preview (maximum eight), permitted child count, relationships, graph revision.
- `GET /api/edge/<id>`: one relationship plus short summaries of source and target, from the same authorized snapshot. Use its graph revision for a review decision.
- `GET /api/examples`: synthetic addable records, expected topic fits and whether each ID already exists in the current permitted workspace. Expectations are demonstration guidance, not classifier overrides.

These read endpoints use the same loopback and audience restrictions as the existing demo API.
