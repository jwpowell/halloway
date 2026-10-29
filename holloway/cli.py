import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser(prog="holloway")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="view a scene script in the browser, rebuilding on save")
    p.add_argument("script")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-open", action="store_true", help="don't open a browser tab")

    p = sub.add_parser("build", help="build a scene script once and print stats")
    p.add_argument("script")

    args = parser.parse_args()
    if args.command == "serve":
        from .server import serve

        serve(args.script, args.port, not args.no_open)
    else:
        from .build import load_scene

        t0 = time.perf_counter()
        data = load_scene(args.script).to_json()
        print(f"built in {time.perf_counter() - t0:.2f}s: {data['stats']}")
