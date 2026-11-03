"""Versioned SQLite graph, evidence validation, and bounded authorized views."""

import copy
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from jsonschema import validate

KINDS = {"topic", "document", "claim", "evidence", "collection"}
TYPES = {
    "belongs_to",
    "contains",
    "in_collection",
    "cites",
    "related_to",
    "supports",
    "contradicts",
    "depends_on",
    "supersedes",
}
FACTUAL = {"supports", "contradicts", "depends_on", "supersedes"}
ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,79}$")
STOP = set(
    "a about an and are as at be been before by can for from has have in into is it its no not of on or that the their this to was were with would example synthetic".split()
)


def now():
    return datetime.now(timezone.utc).isoformat()


def resource(name):
    return json.loads(files("knowledge_graph").joinpath(name).read_text())


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def terms(text):
    return set(
        t
        for t in re.findall(r"[^\W_]+", text.casefold())
        if len(t) > 2 and t not in STOP
    )


def visible(node, audiences):
    return "public" in node["access"] or bool(set(node["access"]) & set(audiences))


def profile_schemas(extra=None):
    paths = list(files("knowledge_graph").joinpath("profiles").iterdir())
    if extra:
        paths += list(Path(extra).glob("*.json"))
    result = {}
    for path in paths:
        value = json.loads(path.read_text())
        if not ID.fullmatch(value["id"]) or value["id"] in result:
            raise ValueError("Profile IDs must be unique safe identifiers")
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(value["schema"])
        # Only self-contained schemas; validation must not fetch a URL.
        if any(
            key in json.dumps(value["schema"])
            for key in ["$ref", "$dynamicRef", "$recursiveRef"]
        ):
            raise ValueError(
                "Profiles must be self-contained; references are not supported"
            )
        result[value["id"]] = value
    return result


class Graph:
    def __init__(self, path, audiences=("demo",), profiles=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audiences = tuple(audiences)
        self.profiles = profile_schemas(profiles)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS edges (id TEXT PRIMARY KEY, source TEXT, target TEXT, kind TEXT, status TEXT, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS edge_source ON edges(source);
                CREATE INDEX IF NOT EXISTS edge_target ON edges(target);
                CREATE TABLE IF NOT EXISTS history (seq INTEGER PRIMARY KEY, at TEXT, action TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, status TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER);
                INSERT OR IGNORE INTO meta VALUES ('revision',0);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def snapshot(self, db=None):
        if db is None:
            with self.connect() as connection:
                connection.execute("BEGIN")
                return self.snapshot(connection)
        nodes = {
            r["id"]: json.loads(r["payload"])
            for r in db.execute("SELECT id,payload FROM nodes")
        }
        nodes = {k: n for k, n in nodes.items() if visible(n, self.audiences)}
        edges = [
            json.loads(r["payload"]) for r in db.execute("SELECT payload FROM edges")
        ]
        edges = [
            e
            for e in edges
            if e["source"] in nodes
            and e["target"] in nodes
            and all(x["node_id"] in nodes for x in e["evidence"])
        ]
        revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[
            0
        ]
        return {"revision": revision, "nodes": nodes, "edges": edges}

    def log(self, db, action, payload):
        db.execute(
            "INSERT INTO history(at,action,payload) VALUES (?,?,?)",
            (now(), action, json.dumps(payload)),
        )
        db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")

    def normalize_node(self, value):
        n = {
            "tags": [],
            "aliases": [],
            "profile": "note",
            "fields": {},
            "access": list(self.audiences),
            "maturity": "observation",
            **copy.deepcopy(value),
        }
        n.pop("revision", None)
        validate(n, resource("schemas/node.json"))
        if n["profile"] not in self.profiles:
            raise ValueError("Unknown content profile")
        validate(n["fields"], self.profiles[n["profile"]]["schema"])
        if not visible(n, self.audiences):
            raise ValueError("Node is outside the configured audiences")
        return n

    def add_node(self, value, parent=None):
        n = self.normalize_node(value)
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM nodes WHERE id=?", (n["id"],)).fetchone():
                raise ValueError(
                    "Node ID already exists; revise the existing node instead"
                )
            n["revision"] = 1
            db.execute("INSERT INTO nodes VALUES (?,?)", (n["id"], json.dumps(n)))
            if parent:
                self._edge(
                    db,
                    {
                        "source": n["id"],
                        "target": parent,
                        "type": "belongs_to",
                        "reason": "Placement chosen by the local curator.",
                        "evidence": [],
                    },
                    "accepted",
                    "local-curator",
                )
            self.log(db, "add_node", n)
        return n

    def revise_node(self, node_id, expected_revision, changes):
        if set(changes) - {"title", "body", "tags", "aliases", "fields", "maturity"}:
            raise ValueError(
                "Only content metadata can be revised; identity, profile and access remain fixed"
            )
        with self.transaction() as db:
            current = self.snapshot(db)["nodes"].get(node_id)
            if not current:
                raise ValueError("Node not available")
            if current["revision"] != expected_revision:
                raise ValueError("Stale node revision; reload before editing")
            updated = self.normalize_node({**current, **changes})
            updated["revision"] = current["revision"] + 1
            db.execute(
                "UPDATE nodes SET payload=? WHERE id=?", (json.dumps(updated), node_id)
            )
            for row in db.execute("SELECT id,payload FROM edges").fetchall():
                edge = json.loads(row["payload"])
                affected = node_id in {edge["source"], edge["target"]} or any(
                    x["node_id"] == node_id for x in edge["evidence"]
                )
                if (
                    affected
                    and (
                        edge["type"] not in {"belongs_to", "contains", "in_collection"}
                        or edge["status"] == "proposed"
                    )
                    and edge["status"] != "rejected"
                ):
                    edge["status"] = "stale"
                    db.execute(
                        "UPDATE edges SET status=?,payload=? WHERE id=?",
                        ("stale", json.dumps(edge), edge["id"]),
                    )
            self.log(db, "revise_node", {"before": current, "after": updated})
        return updated

    def _edge(self, db, data, status, reviewer):
        validate(data, resource("schemas/edge-proposal.json"))
        graph = self.snapshot(db)
        nodes = graph["nodes"]
        a, b, kind = data["source"], data["target"], data["type"]
        if a == b or a not in nodes or b not in nodes:
            raise ValueError("Relationship endpoints must be distinct permitted nodes")
        if kind == "belongs_to" and (
            nodes[a]["kind"] not in {"topic", "document"} or nodes[b]["kind"] != "topic"
        ):
            raise ValueError("Membership connects a topic/document to a topic")
        if kind == "contains" and (
            nodes[a]["kind"] != "document"
            or nodes[b]["kind"] not in {"claim", "evidence"}
        ):
            raise ValueError("Containment connects a document to a claim/evidence node")
        if kind == "in_collection" and (
            nodes[b]["kind"] != "collection" or nodes[a]["kind"] == "collection"
        ):
            raise ValueError("Collection membership must target a collection")
        if kind == "supports" and (
            nodes[b]["kind"] != "claim"
            or nodes[a]["kind"] not in {"document", "claim", "evidence"}
        ):
            raise ValueError("Support must target a specific claim")
        if kind == "contradicts" and {nodes[a]["kind"], nodes[b]["kind"]} != {"claim"}:
            raise ValueError("Contradiction compares two claims")
        for item in data["evidence"]:
            source = nodes.get(item["node_id"])
            if (
                not source
                or source["revision"] != item["revision"]
                or item["quote"] not in source["body"]
            ):
                raise ValueError(
                    "Evidence must quote a permitted current node revision exactly"
                )
        if kind in FACTUAL and not {a, b}.issubset(
            {e["node_id"] for e in data["evidence"]}
        ):
            raise ValueError(
                "Factual relationship proposals require evidence from both endpoints"
            )
        # Validate the active topic hierarchy for cycles, including this edge.
        if (
            kind == "belongs_to"
            and nodes[a]["kind"] == "topic"
            and status == "accepted"
        ):
            adjacency = {}
            for edge in graph["edges"]:
                if edge["type"] == "belongs_to" and edge["status"] == "accepted":
                    adjacency.setdefault(edge["source"], []).append(edge["target"])
            frontier, visited = [b], set()
            while frontier:
                node = frontier.pop()
                if node == a:
                    raise ValueError("Topic hierarchy cannot contain a cycle")
                if node not in visited:
                    visited.add(node)
                    frontier.extend(adjacency.get(node, []))
        edge_id = "e-" + fingerprint([a, b, kind])[:20]
        prior = db.execute(
            "SELECT payload FROM edges WHERE id=?", (edge_id,)
        ).fetchone()
        if (
            prior
            and json.loads(prior[0])["status"] == "accepted"
            and status == "proposed"
        ):
            raise ValueError("An accepted relationship already exists")
        edge = {
            **copy.deepcopy(data),
            "id": edge_id,
            "status": status,
            "reviewer": reviewer,
            "revisions": {a: nodes[a]["revision"], b: nodes[b]["revision"]},
            "updated_at": now(),
        }
        db.execute(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?)",
            (edge_id, a, b, kind, status, json.dumps(edge)),
        )
        return edge

    def add_edge(self, data, status="proposed"):
        if status not in {"accepted", "proposed"}:
            raise ValueError("Unsupported initial status")
        with self.transaction() as db:
            edge = self._edge(
                db, data, status, "local-curator" if status == "accepted" else None
            )
            self.log(db, "add_edge", edge)
        return edge

    def review_edge(self, edge_id, decision, expected_revision):
        if decision not in {"accepted", "rejected"}:
            raise ValueError("Choose accepted or rejected")
        with self.transaction() as db:
            graph = self.snapshot(db)
            if graph["revision"] != expected_revision:
                raise ValueError("Graph changed; reload the review before deciding")
            edge = next((e for e in graph["edges"] if e["id"] == edge_id), None)
            if not edge or edge["status"] != "proposed":
                raise ValueError("Only a current proposed edge can be reviewed")
            data = {
                k: edge[k] for k in ["source", "target", "type", "reason", "evidence"]
            }
            reviewed = self._edge(db, data, decision, "local-curator")
            self.log(db, "review_edge", {"before": edge, "after": reviewed})
        return reviewed

    def import_bundle(self, bundle):
        # Validate everything in one transaction; rejected imports leave no partial graph.
        if (
            set(bundle) != {"nodes", "edges"}
            or len(bundle["nodes"]) > 500
            or len(bundle["edges"]) > 1000
        ):
            raise ValueError("Bundle must contain nodes and edges within import limits")
        with self.transaction() as db:
            for value in bundle["nodes"]:
                n = self.normalize_node(value)
                n["revision"] = 1
                if db.execute("SELECT 1 FROM nodes WHERE id=?", (n["id"],)).fetchone():
                    raise ValueError("Duplicate node ID in import")
                db.execute("INSERT INTO nodes VALUES (?,?)", (n["id"], json.dumps(n)))
            for edge in bundle["edges"]:
                # Import only explicit curator choices; semantic relations start proposed.
                self._edge(
                    db,
                    edge,
                    "proposed"
                    if edge["type"] in FACTUAL | {"related_to"}
                    else "accepted",
                    "import-curator",
                )
            self.log(db, "import", bundle)

    def node(self, node_id):
        graph = self.snapshot()
        node = graph["nodes"].get(node_id)
        if not node:
            raise ValueError("Node not available")
        return {
            "node": node,
            "edges": [
                e for e in graph["edges"] if node_id in {e["source"], e["target"]}
            ],
            "revision": graph["revision"],
        }

    def view(
        self, focus="knowledge", mode="children", include_proposed=False, query=""
    ):
        graph = self.snapshot()
        nodes = graph["nodes"]
        allowed = [
            e
            for e in graph["edges"]
            if e["status"] == "accepted"
            or (include_proposed and e["status"] == "proposed")
        ]
        if focus not in nodes:
            raise ValueError("Focus node not available")
        selected = {focus}
        if mode == "children":
            for e in allowed:
                if (
                    e["type"] in {"belongs_to", "in_collection"}
                    and e["target"] == focus
                ):
                    selected.add(e["source"])
                if e["type"] == "contains" and e["source"] == focus:
                    selected.add(e["target"])
        elif mode in {"neighbors", "foundations", "evidence"}:
            kinds = (
                TYPES
                if mode == "neighbors"
                else (
                    {"depends_on", "cites", "belongs_to"}
                    if mode == "foundations"
                    else {"contains", "supports", "contradicts", "cites"}
                )
            )
            for e in allowed:
                if e["type"] in kinds and focus in {e["source"], e["target"]}:
                    selected.update([e["source"], e["target"]])
        elif mode == "search":
            if len(query) > 500:
                raise ValueError("Search query too long")
            q = terms(query)
            ranked = sorted(
                nodes,
                key=lambda i: (
                    -len(
                        q
                        & terms(
                            nodes[i]["title"]
                            + " "
                            + nodes[i]["body"]
                            + " "
                            + " ".join(nodes[i]["tags"] + nodes[i]["aliases"])
                        )
                    ),
                    nodes[i]["title"],
                ),
            )
            selected.update(
                i
                for i in ranked
                if q
                & terms(
                    nodes[i]["title"]
                    + " "
                    + nodes[i]["body"]
                    + " "
                    + " ".join(nodes[i]["tags"] + nodes[i]["aliases"])
                )
            )
        else:
            raise ValueError("Unknown view")
        all_count = len(selected)
        order = [focus] + (
            [i for i in ranked if i in selected and i != focus]
            if mode == "search"
            else sorted(
                selected - {focus},
                key=lambda i: (nodes[i]["kind"] != "topic", nodes[i]["title"]),
            )
        )
        selected = set(order[:150])
        edges = [
            e for e in allowed if e["source"] in selected and e["target"] in selected
        ]
        cards = []
        for node_id in order[:150]:
            n = nodes[node_id]
            child_ids = {
                e["source"]
                for e in allowed
                if e["target"] == node_id
                and e["type"] in {"belongs_to", "in_collection"}
            }
            child_ids.update(
                e["target"]
                for e in allowed
                if e["source"] == node_id and e["type"] == "contains"
            )
            cards.append(
                {k: n[k] for k in ["id", "title", "kind", "maturity", "revision"]}
                | {"child_count": len(child_ids)}
            )
        return {
            "revision": graph["revision"],
            "focus": focus,
            "mode": mode,
            "nodes": cards,
            "edges": [
                {k: e[k] for k in ["id", "source", "target", "type", "status"]}
                for e in edges[:300]
            ],
            "omitted_nodes": max(0, all_count - 150),
            "omitted_edges": max(0, len(edges) - 300),
        }

    def catalog(self):
        graph = self.snapshot()
        return {
            "revision": graph["revision"],
            "topics": [
                {"id": n["id"], "title": n["title"]}
                for n in graph["nodes"].values()
                if n["kind"] == "topic"
            ],
            "collections": [
                {"id": n["id"], "title": n["title"]}
                for n in graph["nodes"].values()
                if n["kind"] == "collection"
            ],
            "counts": {
                k: sum(n["kind"] == k for n in graph["nodes"].values())
                for k in sorted(KINDS)
            },
            "profiles": [
                {
                    "id": p["id"],
                    "description": p["description"],
                    "example": p["example"],
                }
                for p in self.profiles.values()
            ],
        }
