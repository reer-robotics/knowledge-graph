# Data model and decision workflow

## Separate concepts

Nodes have stable IDs and one of five kinds: topic, document, claim, evidence, collection. Node content includes a version, body, tags, aliases, maturity, access labels and a profile-specific `fields` object. Topics are ordinary records, not hard-coded application categories. A document can appear under several topics and collections while retaining one identity.

Edges have a type, reason, evidence excerpts, endpoint revisions, status and review attribution. Supported types are `belongs_to`, `contains`, `in_collection`, `cites`, `related_to`, `supports`, `contradicts`, `depends_on`, and `supersedes`. `belongs_to` points from child to parent; `contains` points from document to claim/evidence. This is a directed multirelational graph, not a strict tree.

## Ranking

The first release uses two lexical lists: overlap with titles/tags/aliases, and overlap with bodies. Each nonzero list is sorted by matched-term count. The candidate score is the sum of `1 / (60 + rank)` across the lists. Up to 12 topic and 12 content candidates are retained. Keyword suggestions need at least two shared terms; at most three memberships and five related-content edges are proposed.

These scores rank relevance; they are not probabilities or authority. The model may assess candidates semantically but does not compute document maturity. Search uses simple term overlap. Centrality, embeddings and community detection are extension points, not implemented features.

## Fixed workflow

1. Normalize and validate a node against its content profile.
2. Retrieve permitted candidates. For generated output, use only context accessible to all audiences of the source node, preventing a broader source from absorbing narrower context.
3. Classify: choose existing topics, or optionally propose one new topic under an existing parent.
4. Relate: propose typed connections using the supplied candidate IDs and source text.
5. Verify: challenge every proposed semantic relationship; keep or reject with a reason.
6. Validate: verify schemas, endpoint kinds, exact quotes, revisions, duplicates and hierarchy constraints.
7. Save a pending proposal. The graph is still unchanged.
8. On explicit application, save provisional topics and proposed edges. Review each edge separately to accept or reject it.

The optional AI passes share one local Ollama model. Skills and the manifest are versioned package resources. No tools, browsing, automatic retry loop or model download are available to the model. Invalid output fails the operation. A 100,000-character AI context limit fails explicitly instead of silently truncating a document. The verifier can still share the first pass's mistakes.

For keyword mode, the classify and relate stages are deterministic; semantic verification is skipped and no factual edge is generated. New topics may be created manually at any time. They do not require another application release.

## Evidence and review

Factual edges (`supports`, `contradicts`, `depends_on`, `supersedes`) require exact quotes from both endpoint revisions. A support edge targets a claim. Contradiction compares two claims. Schema validation cannot establish that a quote logically supports a relationship: human review is still required.

Bundle imports accept explicit structural placements but make semantic edges proposed. Browser-created topic/collection/containment links are direct local-curator actions. The Python API permits an explicit curator to create accepted edges; integrations must authorize that capability themselves. The prototype does not authenticate individual reviewers: `local-curator` identifies the local operation, not a verified employee identity.

An accepted topic membership cannot create a hierarchy cycle. Semantic cycles are not prohibited by this version. Revising content increments its revision and marks touching semantic/citation edges stale. Structural memberships remain intact. Pending proposals use a conservative graph-wide revision check, so even an unrelated graph mutation can require regeneration. This avoids accepting an analysis against an obsolete snapshot.

History records imports, node changes, proposal applications and reviews in SQLite transactions. Failed mutations roll back. Past data stays in the local history table; the current UI does not provide a full revision browser. Pending proposal artifacts and model trace hashes are kept separately.

## Rendering and access

Each view returns compact node summaries, at most 150 nodes and 300 edges. Excerpts and full content are fetched for an inspected node. Removed views are removed from Cytoscape, not merely hidden. The browser retains only ten small position maps; no full-document cache is kept. Deterministic positions and cached coordinates preserve orientation during navigation. Labels hide at very low geometric zoom.

Access filtering happens before views, counts, search and proposal generation. Source excerpts must also be permitted. Profile validation never fetches remote JSON schema references. These are boundaries for a trusted integration, not a replacement for authentication or an assurance against inference by a malicious authorized curator.

The backend currently loads graph records for each operation; large graphs will need indexed filtering and retrieval. The browser limits are a bounded-view design, not a performance benchmark. The map does not yet aggregate relationships between collapsed topic groups; counts are direct permitted children, not all descendants.

## Inspection and example fitting (0.2)

`GET /api/node/<id>` includes a short excerpt, up to eight accepted direct children, and the permitted total child count. Topic cards open the next layer. `GET /api/edge/<id>` returns the edge, current endpoint summaries and graph revision from the same audience-filtered snapshot. Stale edges retain their original endpoint revision references. Summaries are excerpts, not generated interpretations.

Keyword proposal candidates must share a subject tag; an untagged node uses title terms instead. The existing two-term overlap and bounded reciprocal-rank lists still apply. This conservative filter reduces generic/disclaimer-only matches, but does not understand negation or synonyms. Human review remains essential. AI proposals retain the existing classify/relate/verify workflow.

The three examples in `demo/examples.json` describe expected placements without hardcoding those placements into the classifier. `python examples/content_fit.py` adds each to an isolated database, runs the actual keyword workflow, and shows that accepted membership requires a review decision. The browser gallery offers the same records and reopens existing IDs rather than duplicating them.
