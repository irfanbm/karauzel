from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .engine import Brief, compose, render_html
from .provider import ProviderConfig, load_config, save_config, test_connection

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            target, content_type = ROOT / "static" / "index.html", "text/html; charset=utf-8"
        elif path == "/app.js":
            target, content_type = ROOT / "static" / "app.js", "text/javascript; charset=utf-8"
        elif path == "/app.css":
            target, content_type = ROOT / "static" / "app.css", "text/css; charset=utf-8"
        elif path == "/api/config":
            self._send(200, json.dumps(load_config().public()).encode(), "application/json; charset=utf-8")
            return
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        self._send(200, target.read_bytes(), content_type)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/config":
                current = load_config()
                config = ProviderConfig(
                    provider=str(payload.get("provider", current.provider)),
                    base_url=str(payload.get("base_url", current.base_url)).strip(),
                    model=str(payload.get("model", current.model)).strip(),
                    api_key=str(payload.get("api_key", "")),
                    send_images=bool(payload.get("send_images", current.send_images)),
                )
                if not config.api_key:
                    config.api_key = current.api_key
                save_config(config)
                self._send(200, json.dumps(config.public()).encode(), "application/json; charset=utf-8")
                return
            if self.path == "/api/config/test":
                ok, message = test_connection(load_config())
                self._send(200 if ok else 502, json.dumps({"ok": ok, "message": message}).encode(), "application/json; charset=utf-8")
                return
            if self.path != "/api/generate":
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            brief = Brief.from_dict(payload)
            plan = compose(brief)
            response = {"plan": plan.to_dict(), "html": render_html(plan)}
            self._send(200, json.dumps(response).encode(), "application/json; charset=utf-8")
        except (ValueError, json.JSONDecodeError) as error:
            self._send(400, json.dumps({"error": str(error)}).encode(), "application/json; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        return

def serve(host: str = "127.0.0.1", port: int = 4173) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Carouso running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m carouso")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=4173)
    generate = sub.add_parser("generate")
    generate.add_argument("--brief", required=True)
    generate.add_argument("--out", default="output")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.host, args.port)
        return
    data = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    plan = compose(Brief.from_dict(data))
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    (output / "carousel.html").write_text(render_html(plan), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    print(f"Generated {len(plan.slides)} slides ({plan.signature}) in {output}")

if __name__ == "__main__":
    main()
