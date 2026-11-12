"""Dependency-free Python server for the Mesh Lab architecture simulator."""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from demo import DEMO, get_state

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/styles.css": ("styles.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}


class Handler(BaseHTTPRequestHandler):
    def respond(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, value: object, status: int = 200) -> None:
        self.respond(json.dumps(value).encode(), "application/json", status)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/api/demo":
            self.json(DEMO)
        elif url.path == "/api/state":
            params = parse_qs(url.query)
            try:
                scenario = params.get("scenario", ["traffic"])[0]
                step = int(params.get("step", ["0"])[0])
                site = params.get("site", ["a"])[0]
                weight = int(params.get("weight", ["10"])[0])
                self.json(get_state(scenario, step, site, weight))
            except (ValueError, KeyError, IndexError):
                self.json({"error": "Choose a valid scenario, step and failure context (site a/b, weight 10/50)."}, HTTPStatus.BAD_REQUEST)
        elif url.path == "/healthz":
            self.json({"status": "ok", "mode": "simulation"})
        elif url.path in ASSETS:
            filename, mime = ASSETS[url.path]
            self.respond((STATIC / filename).read_bytes(), mime)
        else:
            self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mesh Lab interactive architecture demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mesh Lab → http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMesh Lab stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
