"""Demonstrate growth across domains without network or model calls."""

from tempfile import TemporaryDirectory
from pathlib import Path
from knowledge_graph.core import Graph, resource
from knowledge_graph.workflow import propose, apply

with TemporaryDirectory() as directory:
    graph = Graph(Path(directory) / "demo.sqlite3")
    graph.import_bundle(resource("demo/base.json"))
    print("1. Start with domain and robotics topics:", graph.catalog()["counts"])
    graph.import_bundle(resource("demo/cross-domain.json"))
    print(
        "2. Add WAM, mathematics, physics, and a cross-domain collection:",
        graph.catalog()["counts"],
    )
    graph.add_node(resource("demo/new-topic.json"), "mathematics")
    node = graph.add_node(resource("demo/new-content.json"), "unclassified")
    proposal = propose(graph, node["id"])
    assert proposal["edges"]
    print("3. New content produces", len(proposal["edges"]), "reviewable suggestions.")
    apply(graph, proposal["id"])
    edge = next(
        e
        for e in graph.snapshot()["edges"]
        if e["source"] == node["id"] and e["type"] == "related_to"
    )
    graph.review_edge(edge["id"], "accepted", graph.snapshot()["revision"])
    graph.revise_node(node["id"], 1, {"body": node["body"] + " Scope revised."})
    assert (
        next(e for e in graph.snapshot()["edges"] if e["id"] == edge["id"])["status"]
        == "stale"
    )
    print("4. Revision invalidates the relationship while retaining history.")
