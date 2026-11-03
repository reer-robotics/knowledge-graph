import argparse
import json
from pathlib import Path

from .core import Graph, resource
from .workflow import propose, apply


def main():
    p = argparse.ArgumentParser(description="Extensible local knowledge graph")
    p.add_argument("--db", default="workspace/graph.sqlite3")
    p.add_argument("--audience", action="append")
    p.add_argument(
        "--profiles", help="Directory of additional trusted JSON content schemas"
    )
    p.add_argument("--model", help="Optional already-installed local Ollama model")
    commands = p.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--minimal", action="store_true")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=4175)
    imp = commands.add_parser("import")
    imp.add_argument("file", type=Path)
    prop = commands.add_parser("propose")
    prop.add_argument("node")
    app = commands.add_parser("apply")
    app.add_argument("proposal")
    view = commands.add_parser("view")
    view.add_argument("--focus", default="knowledge")
    view.add_argument("--mode", default="children")
    view.add_argument("--proposed", action="store_true")
    args = p.parse_args()
    if args.command == "serve":
        from .server import create_app

        create_app(args.db, args.audience or ["demo"], args.model, args.profiles).run(
            host="127.0.0.1", port=args.port, threaded=True
        )
        return
    g = Graph(args.db, args.audience or ["demo"], args.profiles)
    try:
        if args.command == "init":
            g.import_bundle(resource("demo/base.json"))
            if not args.minimal:
                g.import_bundle(resource("demo/cross-domain.json"))
            result = g.catalog()
        elif args.command == "import":
            g.import_bundle(json.loads(args.file.read_text()))
            result = g.catalog()
        elif args.command == "propose":
            result = propose(g, args.node, args.model)
        elif args.command == "apply":
            result = apply(g, args.proposal)
        else:
            result = g.view(args.focus, args.mode, args.proposed)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
