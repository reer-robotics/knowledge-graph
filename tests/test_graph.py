import copy
import json

import httpx
import pytest
from jsonschema import ValidationError

from knowledge_graph.core import Graph, resource
from knowledge_graph.workflow import propose, apply
from knowledge_graph.server import create_app


@pytest.fixture
def graph(tmp_path):
    g = Graph(tmp_path / "graph.sqlite3")
    g.import_bundle(resource("demo/base.json"))
    g.import_bundle(resource("demo/cross-domain.json"))
    return g


def edge(a, b, kind="belongs_to", evidence=None):
    return {
        "source": a,
        "target": b,
        "type": kind,
        "reason": "Explicit test relationship.",
        "evidence": evidence or [],
    }


def test_shared_identity_across_topics_and_collection(graph):
    node = graph.node("optimization-note")["node"]
    assert node["revision"] == 1
    for focus in ["optimization", "planning", "autonomy-reading"]:
        assert "optimization-note" in {n["id"] for n in graph.view(focus)["nodes"]}
    assert len([n for n in graph.snapshot()["nodes"] if n == "optimization-note"]) == 1


def test_new_topic_and_independent_document(graph):
    graph.add_node(resource("demo/new-topic.json"), "mathematics")
    n = resource("demo/new-content.json")
    n["id"] = "independent"
    n["title"] = "New subject"
    graph.add_node(n)
    assert "geometry" in {n["id"] for n in graph.view("mathematics")["nodes"]}
    assert graph.node("independent")["edges"] == []


def test_cycle_rejected_without_mutation(graph):
    before = graph.snapshot()
    with pytest.raises(ValueError, match="cycle"):
        graph.add_edge(edge("knowledge", "world-action-models"), "accepted")
    assert graph.snapshot() == before


def test_import_transaction_rolls_back(graph):
    before = graph.snapshot()
    with pytest.raises(ValueError):
        graph.import_bundle(
            {
                "nodes": [resource("demo/new-topic.json")],
                "edges": [edge("geometry", "missing")],
            }
        )
    assert graph.snapshot() == before


def test_factual_relationship_requires_real_quotes(graph):
    with pytest.raises(ValueError, match="both endpoints"):
        graph.add_edge(edge("toy-evidence", "prediction-claim", "supports"))
    evidence = [
        {
            "node_id": "toy-evidence",
            "revision": 1,
            "quote": "Invented text",
            "locator": "Body",
        },
        {
            "node_id": "prediction-claim",
            "revision": 1,
            "quote": "Synthetic hypothesis",
            "locator": "Body",
        },
    ]
    with pytest.raises(ValueError, match="exactly"):
        graph.add_edge(edge("toy-evidence", "prediction-claim", "supports", evidence))


def test_review_is_separate_from_proposal(graph):
    n = graph.add_node(resource("demo/new-content.json"), "unclassified")
    p = propose(graph, n["id"])
    assert p["mode"] == "lexical" and p["edges"]
    assert all(e["type"] in {"belongs_to", "related_to"} for e in p["edges"])
    assert not any(
        e["source"] == n["id"] and e["type"] == "related_to"
        for e in graph.snapshot()["edges"]
    )
    apply(graph, p["id"])
    item = next(
        e
        for e in graph.snapshot()["edges"]
        if e["source"] == n["id"] and e["status"] == "proposed"
    )
    graph.review_edge(item["id"], "accepted", graph.snapshot()["revision"])
    assert (
        next(e for e in graph.snapshot()["edges"] if e["id"] == item["id"])["reviewer"]
        == "local-curator"
    )
    with pytest.raises(ValueError):
        apply(graph, p["id"])


def test_stale_proposal_cannot_apply(graph):
    n = graph.add_node(resource("demo/new-content.json"))
    p = propose(graph, n["id"])
    graph.revise_node(n["id"], 1, {"body": n["body"] + " Additional evidence."})
    with pytest.raises(ValueError, match="Stale"):
        apply(graph, p["id"])


def test_node_edit_invalidates_edges_and_preserves_history(graph):
    old = graph.node("wam-survey")["node"]
    graph.revise_node("wam-survey", 1, {"body": old["body"] + " New scope."})
    edges = graph.node("wam-survey")["edges"]
    assert all(
        e["status"] == "stale"
        for e in edges
        if e["type"] in {"depends_on", "related_to"}
    )
    assert all(
        e["status"] == "accepted"
        for e in edges
        if e["type"] in {"contains", "belongs_to", "in_collection"}
    )
    with graph.connect() as db:
        audit = json.loads(
            db.execute(
                "SELECT payload FROM history WHERE action='revise_node'"
            ).fetchone()[0]
        )
        assert audit["before"] == old and audit["after"]["revision"] == 2
    with pytest.raises(ValueError, match="Stale"):
        graph.revise_node("wam-survey", 1, {"title": "Lost update"})


def test_access_filters_graph_and_counts(graph):
    node = resource("demo/new-topic.json")
    node["access"] = ["secret"]
    admin = Graph(graph.path, audiences=["demo", "secret"])
    admin.add_node(node, "mathematics")
    assert "geometry" not in graph.snapshot()["nodes"]
    assert "geometry" not in json.dumps(graph.view("mathematics"))
    assert "geometry" not in json.dumps(graph.catalog())
    with pytest.raises(ValueError):
        graph.node("geometry")


def test_bounded_views_omit_bodies(graph):
    template = resource("demo/new-topic.json")
    nodes = [
        {**template, "id": f"topic{i}", "title": f"Topic {i:03}"} for i in range(160)
    ]
    graph.import_bundle(
        {"nodes": nodes, "edges": [edge(n["id"], "mathematics") for n in nodes]}
    )
    view = graph.view("mathematics")
    assert len(view["nodes"]) == 150 and view["omitted_nodes"] > 0
    assert len(view["edges"]) <= 300
    assert all("body" not in n and "fields" not in n for n in view["nodes"])


def test_profiles_enforce_theoretical_metadata(graph):
    n = resource("demo/new-content.json")
    n.update(profile="theorem", fields={})
    with pytest.raises(ValidationError):
        graph.add_node(n)
    n["fields"] = resource("profiles/theorem.json")["example"]
    n["fields"]["proof_status"] = "machine_checked"
    with pytest.raises(ValidationError):
        graph.add_node(n)


def test_external_profile_without_core_change(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "question.json").write_text(
        json.dumps(
            {
                "id": "question",
                "version": 1,
                "description": "Open question",
                "schema": {
                    "type": "object",
                    "required": ["question"],
                    "additionalProperties": False,
                    "properties": {"question": {"type": "string"}},
                },
                "example": {"question": "What remains unknown?"},
            }
        )
    )
    g = Graph(tmp_path / "custom.sqlite3", profiles=profiles)
    n = resource("demo/new-content.json")
    n.update(profile="question", fields={"question": "What changes?"})
    assert g.add_node(n)["profile"] == "question"


def test_lexical_mode_makes_no_network_calls(graph, monkeypatch):
    def fail(*a, **kw):
        raise AssertionError("Unexpected network call")

    monkeypatch.setattr(httpx.Client, "post", fail)
    propose(graph, "wam-survey")


def test_one_model_three_passes(graph, monkeypatch):
    calls = []

    def handler(request):
        data = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        context = json.loads(data["messages"][-1]["content"])
        skill = context["skill"]["id"]
        calls.append((skill, data["model"]))
        if skill == "classify":
            out = {"topics": ["planning"], "new_topic": None}
        elif skill == "relate":
            out = {"edges": [edge("wam-survey", "algebra-note", "related_to")]}
        else:
            out = {
                "decisions": [
                    {
                        "index": 0,
                        "keep": False,
                        "reason": "The topics alone do not justify this connection.",
                    }
                ]
            }
        return httpx.Response(200, json={"message": {"content": json.dumps(out)}})

    # Use a valid candidate from the retrieved pool for the rejected relation.
    original = httpx.Client

    def handler_valid(request):
        if request.url.path == "/api/chat":
            data = json.loads(request.content)
            context = json.loads(data["messages"][-1]["content"])
            if context["skill"]["id"] == "relate":
                calls.append(("relate", data["model"]))
                target = context["input"]["candidates"][0]["id"]
                return httpx.Response(
                    200,
                    json={
                        "message": {
                            "content": json.dumps(
                                {"edges": [edge("wam-survey", target, "related_to")]}
                            )
                        }
                    },
                )
        return handler(request)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handler_valid), **kw),
    )
    p = propose(graph, "wam-survey", "test-local")
    assert calls == [
        ("classify", "test-local"),
        ("relate", "test-local"),
        ("verify", "test-local"),
    ]
    assert all(e["type"] != "related_to" for e in p["edges"])
    assert len(p["trace"]) == 3


def test_model_failure_does_not_mutate_graph(graph, monkeypatch):
    before = graph.snapshot()

    def fail(*a, **kw):
        raise ValueError("Invalid output")

    monkeypatch.setattr("knowledge_graph.workflow.LocalModel.run", fail)
    with pytest.raises(ValueError):
        propose(graph, "wam-survey", "local")
    assert graph.snapshot() == before


def test_http_tokens_hosts_and_mutation(graph):
    client = create_app(graph.path).test_client()
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/", environ_base={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
    assert client.post("/api/propose/wam-survey", json={}).status_code == 403
    token = client.get("/api/config").json["token"]
    headers = {"X-Graph-Token": token}
    assert (
        client.post(
            "/api/propose/wam-survey",
            json={},
            headers={**headers, "Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/propose/wam-survey", json={"model": "other"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post("/api/propose/wam-survey", json={}, headers=headers).status_code
        == 200
    )
    assert client.get("/api/view").headers["Cache-Control"] == "no-store"


def test_assets_and_schema_are_text_safe(graph):
    client = create_app(graph.path).test_client()
    for url in [
        "/",
        "/assets/app.js",
        "/assets/state.js",
        "/assets/style.css",
        "/assets/vendor/cytoscape.min.js",
    ]:
        assert client.get(url).status_code == 200
    assert "innerHTML" not in client.get("/assets/app.js").text
    assert client.get("/assets/../../core.py").status_code == 404


def test_model_new_topic_is_provisional_until_review(graph, monkeypatch):
    def run(self, skill, context, schema):
        if skill == "classify":
            return {
                "topics": [],
                "new_topic": {
                    "title": "Adaptive world models",
                    "description": "Synthetic topic proposal.",
                    "parent": "ai",
                },
            }
        return {"edges": []}

    monkeypatch.setattr("knowledge_graph.workflow.LocalModel.run", run)
    p = propose(graph, "wam-survey", "test-local")
    assert len(p["new_topics"]) == 1
    new_id = p["new_topics"][0]["id"]
    assert new_id not in graph.snapshot()["nodes"]
    apply(graph, p["id"])
    assert graph.node(new_id)["node"]["maturity"] == "provisional"
    assert all(e["status"] == "proposed" for e in graph.node(new_id)["edges"])


def test_broader_source_cannot_absorb_narrower_context(graph, monkeypatch):
    admin = Graph(graph.path, audiences=["demo", "secret"])
    secret = resource("demo/new-content.json")
    secret.update(
        id="secret-node", title="Secret dynamics optimization", access=["secret"]
    )
    admin.add_node(secret)
    seen = []

    def run(self, skill, context, schema):
        seen.append(json.dumps(context))
        if skill == "classify":
            return {"topics": [], "new_topic": None}
        return {"edges": []}

    monkeypatch.setattr("knowledge_graph.workflow.LocalModel.run", run)
    propose(admin, "wam-survey", "test-local")
    assert seen and all("secret-node" not in text for text in seen)


def test_model_rejects_cloud_metadata(graph, monkeypatch):
    def handler(request):
        return httpx.Response(
            200, json={"capabilities": ["completion"], "remote_host": "remote.example"}
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    with pytest.raises(ValueError, match="locally"):
        propose(graph, "wam-survey", "remote")


def test_pending_classification_becomes_stale_on_revision(graph):
    n = graph.add_node(resource("demo/new-content.json"), "unclassified")
    p = propose(graph, n["id"])
    apply(graph, p["id"])
    graph.revise_node(n["id"], 1, {"body": "Changed scope: abstract algebra study."})
    relations = graph.node(n["id"])["edges"]
    assert all(
        e["status"] == "stale" for e in relations if e["target"] != "unclassified"
    )
    assert (
        next(e for e in relations if e["target"] == "unclassified")["status"]
        == "accepted"
    )
