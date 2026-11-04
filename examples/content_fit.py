"""Run the gallery's examples through actual proposals and review, in a temporary DB."""

from pathlib import Path
from tempfile import TemporaryDirectory
from knowledge_graph.core import Graph, resource
from knowledge_graph.workflow import propose, apply

with TemporaryDirectory() as directory:
    graph = Graph(Path(directory) / "examples.sqlite3")
    for name in ["base", "cross-domain"]:
        graph.import_bundle(resource("demo/" + name + ".json"))
    for sample in resource("demo/examples.json"):
        node = graph.add_node(sample["node"], "unclassified")
        proposal = propose(graph, node["id"])
        placements = [
            e["target"] for e in proposal["edges"] if e["type"] == "belongs_to"
        ]
        assert set(sample["expected_topics"]).issubset(placements)
        print(node["title"] + "\n  Proposed topics: " + ", ".join(placements))
        apply(graph, proposal["id"])
        for target in sample["expected_topics"]:
            assert node["id"] not in {n["id"] for n in graph.view(target)["nodes"]}
            edge = next(
                e
                for e in graph.snapshot()["edges"]
                if e["source"] == node["id"]
                and e["target"] == target
                and e["type"] == "belongs_to"
            )
            # Simulated curator acceptance only for this disposable demonstration.
            graph.review_edge(edge["id"], "accepted", graph.snapshot()["revision"])
            assert node["id"] in {n["id"] for n in graph.view(target)["nodes"]}
            print("  After simulated review: visible inside " + target)
        if node["id"] == "example-group-questions":
            assert "robotics" not in placements
            print("  No forced Robotics membership.")
