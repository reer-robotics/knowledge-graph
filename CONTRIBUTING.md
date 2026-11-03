# Contributing

This repository owns graph classification, relationship review and visualization. Keep formatter and reading-assistant work in their separate repositories.

1. Fork and clone this repository, then create a focused branch.
2. Use Python 3.11+, create `.venv`, and install `python -m pip install -e '.[dev]'`.
3. Run `knowledge-map serve --port 4175`. Use the bundled synthetic examples; no model is required.
4. Make the smallest useful change. Include a concrete example of the new behavior.
5. Run `pytest -q`, `node --test tests/state.test.mjs` with Node 22+, and `python examples/run_demo.py`.
6. For packaging changes, build `python -m pip wheel --no-deps . -w dist` and verify resource inclusion. For visual changes, test in the browser and include a screenshot containing only synthetic/public material.
7. Update docs, contracts and CHANGELOG as appropriate. Open a pull request explaining the problem, change and verification.

## Areas to improve

- **Topic classification:** evaluate missed relevant categories, inappropriate assignments and handling of genuinely new subjects. Keep unclassified content possible. Similarity does not establish scientific support.
- **Evidence relationships:** test wrong scope, missing assumptions, stale evidence, duplicate nodes and fabricated quotations. Keep factual edges reviewable.
- **Content profiles:** follow `docs/extending.md`; make assumptions and missing information explicit. Do not claim theorem proving or dimensional analysis from field validation.
- **Model skills:** bump versions when behavior changes. Preserve the fixed classify/relate/verify sequence and one optional local model. Use synthetic mocked fixtures; real-model evaluations must report model, environment, failures and limitations.
- **Visualization:** preserve the bounded view, keyboard-accessible list, cache limit and clear proposed/accepted status. Measure browser memory and interaction latency before claiming scale improvements.
- **Integrations:** keep identity and authorization on the trusted backend. Include provenance and exact source revisions. Never publish real company datasets in this repository.

## Review expectations

Explain schema compatibility, migration needs and validation limits. A maintainer should review access behavior, evidence provenance and user-visible changes before merging. These are contributor expectations; the repository does not itself guarantee a branch approval policy is configured.

## Renderer updates

`vendor-lock.json` pins Cytoscape and records npm integrity. To intentionally upgrade, change the pinned version, run `python scripts/vendor_cytoscape.py`, inspect the vendor diff/license, and run browser tests. The script copies only the known JS and license archive entries; it never extracts an arbitrary tarball into the project.
