"""Single-user loopback demo. No internet deployment or identity provider."""

import json
import secrets
import threading
from importlib.resources import files

import httpx
from flask import Flask, abort, jsonify, request
from jsonschema import ValidationError
from werkzeug.exceptions import HTTPException

from .core import Graph, resource
from .workflow import propose, apply


def create_app(path, audiences=("demo",), model=None, profiles=None):
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=200_000, TRUSTED_HOSTS=["127.0.0.1", "localhost"]
    )
    graph = Graph(path, audiences, profiles)
    with graph.connect() as db:
        empty = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 0
    if empty:
        for name in ["base", "cross-domain"]:
            bundle = resource("demo/" + name + ".json")
            for node in bundle["nodes"]:
                node["access"] = list(audiences)
            graph.import_bundle(bundle)
    token = secrets.token_urlsafe(32)
    busy = threading.Lock()

    @app.before_request
    def protect():
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            abort(403)
        if request.method == "POST":
            if request.headers.get("X-Graph-Token") != token or not request.is_json:
                abort(403)
            if request.headers.get("Origin") not in {
                None,
                request.host_url.rstrip("/"),
            }:
                abort(403)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        if isinstance(exc, (ValueError, ValidationError, KeyError, TypeError)):
            return jsonify(
                error=str(exc)[:220]
                if isinstance(exc, ValueError)
                else "Invalid input or model response; check the schema."
            ), 400
        if isinstance(exc, httpx.HTTPError):
            return jsonify(
                error="Local Ollama request failed; check the installed model and local service."
            ), 502
        app.logger.error("Graph request failed: %s", type(exc).__name__)
        return jsonify(error="Request failed. No partial transaction was saved."), 500

    @app.get("/")
    def index():
        return files("knowledge_graph").joinpath("web/index.html").read_text()

    @app.get("/assets/<path:name>")
    def asset(name):
        allowed = {
            "app.js": "application/javascript",
            "state.js": "application/javascript",
            "style.css": "text/css",
            "vendor/cytoscape.min.js": "application/javascript",
        }
        if name not in allowed:
            abort(404)
        return app.response_class(
            files("knowledge_graph").joinpath("web/" + name).read_bytes(),
            mimetype=allowed[name],
        )

    @app.get("/api/config")
    def config():
        return jsonify(
            token=token,
            model=model,
            **graph.catalog(),
            samples={
                "document": resource("demo/new-content.json"),
                "topic": resource("demo/new-topic.json"),
            },
        )

    @app.get("/api/view")
    def view():
        return jsonify(
            graph.view(
                request.args.get("focus", "knowledge"),
                request.args.get("mode", "children"),
                request.args.get("proposed") == "true",
                request.args.get("q", ""),
            )
        )

    @app.get("/api/node/<node_id>")
    def node(node_id):
        return jsonify(graph.node(node_id))

    @app.get("/api/review")
    def review():
        g = graph.snapshot()
        return jsonify(
            revision=g["revision"],
            edges=[e for e in g["edges"] if e["status"] in {"proposed", "stale"}][:100],
            nodes={k: n["title"] for k, n in g["nodes"].items()},
        )

    def data(keys):
        value = request.get_json()
        if not isinstance(value, dict) or set(value) != set(keys):
            raise ValueError("Unexpected request fields")
        return value

    @app.post("/api/node")
    def add_node():
        d = data(["node", "parent"])
        n = d["node"]
        if not isinstance(n, dict) or set(n) - {
            "id",
            "title",
            "kind",
            "body",
            "tags",
            "aliases",
            "profile",
            "fields",
        }:
            raise ValueError("Unsupported node fields")
        return jsonify(graph.add_node(n, d["parent"] or None))

    @app.post("/api/revise/<node_id>")
    def revise(node_id):
        d = data(["revision", "changes"])
        return jsonify(graph.revise_node(node_id, d["revision"], d["changes"]))

    @app.post("/api/edge")
    def add_edge():
        d = data(["edge"])
        # A human explicitly chooses collection/topic placement; other relations await review.
        status = (
            "accepted"
            if d["edge"].get("type") in {"in_collection", "belongs_to", "contains"}
            else "proposed"
        )
        return jsonify(graph.add_edge(d["edge"], status))

    @app.post("/api/propose/<node_id>")
    def proposals(node_id):
        data([])
        if not busy.acquire(blocking=False):
            return jsonify(error="An analysis request is already running."), 409
        try:
            return jsonify(propose(graph, node_id, model))
        finally:
            busy.release()

    @app.post("/api/apply/<proposal_id>")
    def apply_proposal(proposal_id):
        data([])
        return jsonify(apply(graph, proposal_id))

    @app.post("/api/review/<edge_id>")
    def review_edge(edge_id):
        d = data(["decision", "revision"])
        return jsonify(graph.review_edge(edge_id, d["decision"], d["revision"]))

    @app.get("/api/export")
    def export():
        g = graph.snapshot()
        return jsonify(schema_version=1, **g)

    return app
