# Extending the knowledge atlas

## New topics without code changes

Use Add knowledge → Topic. Choose a stable ID, title, description, useful tags and optional existing parent. For example, Geometry can be added under Mathematics; a new independent discipline can be added directly under Knowledge atlas. If there is no appropriate location, leave the content unplaced or use Unclassified.

An item may have multiple `belongs_to` relationships. Select it and use Add another topic membership. The graph stores one node, so revisions and evidence remain consistent across browsing views. Research collections use `in_collection` links and do not reorganize the subject hierarchy.

Titles can be revised without changing IDs. The library supports alias lists for search; the current browser revision form preserves existing aliases. Automated alias resolution, topic deduplication, merging and redirect management are not included. Resolve proposed duplicates deliberately before adding them.

## Content profiles

A profile is a self-contained JSON Schema plus example fields. It validates domain-specific metadata while leaving node identity and graph behavior unchanged. The built-in profiles cover general notes, experiments, theorem worksheets and physics models.

Create a directory outside the checkout, add a file such as `question.json`, then start with `knowledge-map --profiles /absolute/path/profiles serve`:

```json
{
  "id": "research-question",
  "version": 1,
  "description": "Questions and their unresolved assumptions",
  "schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["question", "unknowns"],
    "properties": {
      "question": {"type": "string", "minLength": 1},
      "unknowns": {"type": "array", "items": {"type": "string"}}
    }
  },
  "example": {"question": "What should be investigated?", "unknowns": []}
}
```

The new profile appears in Add knowledge, including editable JSON fields. No renderer or database migration is needed. Profile IDs must be unique; remote schema references are prohibited. Changes to an existing profile require a deliberate compatibility plan for stored records. Keep the profile files with your database backups.

Validation checks required fields and types only. It does not establish scientific correctness. The current theorem profile only permits unverified proof status; a real proof-checking integration would need evidence and a separate reviewed contract.

## New relationship types

Relationship types are deliberately bounded. To add one, update `core.TYPES`, the edge schema, endpoint/evidence validation, view filters, model output constraints and tests. Explain its direction, evidence requirements, review policy and invalidation rules. Do not quietly overload `supports` to mean “looks similar”.

## Importing existing content

The `import` command accepts a bundle with `nodes` and `edges`; see `demo/base.json` and `demo/cross-domain.json`. It validates the entire bundle in one SQLite transaction. IDs must not already exist. There is no destructive replace option.

An adapter from Document Formatter or the company journal should retain original document IDs, revisions and source provenance. Generated prose is not automatically original evidence. An adapter from Reading Assistant should treat matches as candidate `related_to` links, never as accepted support.
