from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, content, design, projects
from .provider import ProviderConfig, load_config, save_config, test_connection
from .structures import catalog, outline

ROOT = Path(__file__).resolve().parent
API_VERSION = 2
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/project/new": ("index.html", "text/html; charset=utf-8"),
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/brief": ("index.html", "text/html; charset=utf-8"),
    "/design": ("index.html", "text/html; charset=utf-8"),
    "/export": ("index.html", "text/html; charset=utf-8"),
    "/dashboard": ("index.html", "text/html; charset=utf-8"),
    "/admin-dashboard": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}
MAX_JSON = 2 * 1024 * 1024
PROJECT_ROUTE = re.compile(r"^/api/projects/([a-z0-9-]+)(?:/(generate|check|images)(?:/([a-z0-9-]+\.(?:jpg|png|gif|webp)))?)?$")
SLIDE_ROUTE = re.compile(r"^/api/projects/([a-z0-9-]+)/slides/([a-f0-9]{8})/generate$")
DESIGN_ROUTE = re.compile(r"^/api/projects/([a-z0-9-]+)/design/(analyze|generate)/?$")
V1_PROJECT_ROUTE = re.compile(r"^/api/v1/projects/([a-z0-9-]+)(?:/(generate|check))?$")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "Carouso"

    def _send(self, status: int, body: bytes, content_type: str, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: object) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _local_only(self) -> None:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]"):
            raise ApiError(403, "Carouso only accepts requests to localhost")

    def _require_api_key(self) -> None:
        keys = {key.strip() for key in os.getenv("CAROUSO_API_KEYS", "").split(",") if key.strip()}
        if not keys:
            raise ApiError(503, "CAROUSO_API_KEYS belum diatur. API v1 dinonaktifkan.")
        provided = self.headers.get("X-API-Key", "")
        if not provided or not any(hmac.compare_digest(provided, key) for key in keys):
            raise ApiError(401, "API key tidak valid. Kirim header X-API-Key.")

    def _body(self, limit: int = MAX_JSON) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ApiError(413, "request is too large")
        return self.rfile.read(length) if length else b""

    def _payload(self) -> dict:
        raw = self._body()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise ApiError(400, "invalid JSON") from error
        if not isinstance(data, dict):
            raise ApiError(400, "expected a JSON object")
        return data

    def _project(self, project_id: str) -> dict:
        try:
            return projects.load(project_id)
        except (FileNotFoundError, ValueError) as error:
            raise ApiError(404, "project not found") from error

    def _dispatch(self, method: str) -> None:
        try:
            self._local_only()
            self._route(method, urlparse(self.path).path)
        except ApiError as error:
            self._json(error.status, {"error": str(error)})
        except content.GenerationError as error:
            self._json(502, {"error": str(error)})
        except ValueError as error:
            self._json(400, {"error": str(error)})

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def _route_v1(self, method: str, path: str) -> None:
        if path == "/api/v1/projects" and method == "POST":
            payload = self._payload()
            project = projects.create(payload.get("brief", {}))
            project = content.generate_all(project, load_config())
            projects.save(project)
            self._json(201, {"object": "project", "data": project})
            return
        match = V1_PROJECT_ROUTE.match(path)
        if match:
            project_id, action = match.groups()
            if method == "GET" and not action:
                self._json(200, {"object": "project", "data": projects.load(project_id)})
                return
            if method == "PUT" and not action:
                self._json(200, {"object": "project", "data": projects.update(project_id, self._payload())})
                return
            if method == "POST" and action == "generate":
                self._json(200, {"object": "project", "data": content.generate_all(projects.load(project_id), load_config())})
                return
            if method == "POST" and action == "check":
                project = projects.load(project_id)
                issues = content.check(project)
                self._json(200, {"object": "check", "ok": not any(issue["level"] == "error" for issue in issues), "issues": issues})
                return
        raise ApiError(404, "Unknown endpoint")

    def _route(self, method: str, path: str) -> None:
        if method == "GET" and path in STATIC:
            name, kind = STATIC[path]
            self._send(200, (ROOT / "static" / name).read_bytes(), kind)
            return
        if path == "/api/health" and method == "GET":
            self._json(200, {"app": "carouso", "version": __version__, "api": API_VERSION, "pid": os.getpid()})
            return
        if path == "/api/shutdown" and method == "POST":
            self._json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path.startswith("/api/v1/"):
            self._require_api_key()
            self._route_v1(method, path)
            return
        if path == "/api/catalog" and method == "GET":
            self._json(200, catalog())
            return
        if path == "/api/outline" and method == "GET":
            query = parse_qs(urlparse(self.path).query)
            structure = (query.get("structure") or ["auto"])[0]
            try:
                count = int((query.get("slides") or ["6"])[0])
            except ValueError as error:
                raise ApiError(400, "slides must be a number") from error
            self._json(200, {"roles": outline(structure, count)})
            return
        if path == "/api/config":
            if method == "GET":
                self._json(200, load_config().public())
                return
            if method == "POST":
                self._save_config(self._payload())
                return
        if path == "/api/config/test" and method == "POST":
            ok, message = test_connection(load_config())
            self._json(200 if ok else 502, {"ok": ok, "message": message})
            return
        if path == "/api/projects":
            if method == "GET":
                self._json(200, projects.list_projects())
                return
            if method == "POST":
                self._json(201, projects.create(self._payload().get("brief")))
                return
        match = SLIDE_ROUTE.match(path)
        if match and method == "POST":
            project = self._project(match.group(1))
            project = self._merge(project, self._payload())
            project = content.generate_one(project, match.group(2))
            self._json(200, projects.save(project))
            return
        match = DESIGN_ROUTE.match(path)
        if match and method == "POST":
            project_id, action = match.groups()
            project = self._merge(self._project(project_id), self._payload())
            if action == "analyze":
                result = design.analyze(project)
                self._json(200, {**result, "project": projects.save(project)})
            else:
                self._json(200, projects.save(design.generate(project)))
            return
        match = PROJECT_ROUTE.match(path)
        if match:
            self._project_route(method, *match.groups())
            return
        raise ApiError(404, "not found")

    def _merge(self, project: dict, payload: dict) -> dict:
        """Use the unsaved state the browser sends so a generate never overwrites fresh edits."""
        if isinstance(payload.get("brief"), dict):
            project["brief"] = payload["brief"]
        if isinstance(payload.get("slides"), list):
            project["slides"] = payload["slides"]
        if isinstance(payload.get("design"), dict):
            project["design"] = payload["design"]
        return projects.save(project)

    def _project_route(self, method: str, project_id: str, action: str | None, image: str | None) -> None:
        if action is None:
            if method == "GET":
                self._json(200, self._project(project_id))
                return
            if method == "PUT":
                payload = self._payload()
                self._project(project_id)
                payload["id"] = project_id
                self._json(200, projects.save(payload))
                return
        if action == "generate" and method == "POST":
            project = self._merge(self._project(project_id), self._payload())
            self._json(200, projects.save(content.generate_all(project)))
            return
        if action == "check" and method == "POST":
            project = self._merge(self._project(project_id), self._payload())
            issues = content.check(project)
            self._json(200, {"ok": not any(issue["level"] == "error" for issue in issues), "issues": issues})
            return
        if action == "images":
            if image and method == "GET":
                path = projects.image_path(project_id, image)
                if not path.exists():
                    raise ApiError(404, "image not found")
                kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send(200, path.read_bytes(), kind, cache=True)
                return
            if not image and method == "POST":
                self._project(project_id)
                if (self.headers.get("Content-Type") or "").startswith("application/json"):
                        name = projects.fetch_image(project_id, str(self._payload().get("url", "")))
                else:
                    name = projects.store_image(project_id, self._body(projects.MAX_IMAGE_BYTES))
                self._json(201, {"image": name})
                return
        raise ApiError(405 if action else 404, "not allowed")

    def _save_config(self, payload: dict) -> None:
        current = load_config()
        config = ProviderConfig(
            provider=str(payload.get("provider", current.provider)),
            base_url=str(payload.get("base_url", current.base_url)).strip(),
            model=str(payload.get("model", current.model)).strip(),
            api_key=str(payload.get("api_key") or current.api_key),
            send_images=bool(payload.get("send_images", current.send_images)),
        )
        save_config(config)
        self._json(200, config.public())

    def log_message(self, format: str, *args: object) -> None:
        return


class Server(ThreadingHTTPServer):
    allow_reuse_address = False
    allow_reuse_port = False
    daemon_threads = True


def _running_api(url: str) -> int | None:
    """API version of whatever answers on url: an int, 0 for an older Carouso, None if it is not Carouso."""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as response:
            data = json.loads(response.read())
            return int(data.get("api", 0)) if data.get("app") == "carouso" else None
    except urllib.error.HTTPError as error:
        if error.code != 404:
            return None
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 0 if b"carouso" in response.read(4096).lower() else None
    except (urllib.error.URLError, OSError):
        return None


def _stop_running(url: str) -> bool:
    try:
        request = urllib.request.Request(f"{url}/api/shutdown", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=2).close()
    except (urllib.error.URLError, OSError):
        return False
    for _ in range(20):
        time.sleep(0.25)
        if _running_api(url) is None:
            return True
    return False


def _bind(host: str, port: int, open_browser: bool, open_path: str = "") -> Server | None:
    url = f"http://{host}:{port}"
    try:
        return Server((host, port), Handler)
    except OSError:
        pass
    running = _running_api(url)
    if running == API_VERSION:
        print(f"Carouso is already running at {url}.")
        if open_browser:
            webbrowser.open(url + open_path)
        return None
    if running is not None and running > 0 and _stop_running(url):
        print("Stopped an older Carouso server.")
        try:
            return Server((host, port), Handler)
        except OSError:
            pass
    if running is None:
        print(f"Port {port} is used by another program. Start on another port, e.g.: start.bat {port + 1}")
    else:
        print(f"An older Carouso is still running on port {port}.")
        print("Close its window (or run start.bat again, which closes it), then try again.")
    sys.exit(2)


def serve(host: str = "127.0.0.1", port: int = 4173, open_browser: bool = False, open_path: str = "") -> None:
    url = f"http://{host}:{port}"
    server = _bind(host, port, open_browser, open_path)
    if server is None:
        return
    print(f"Carouso running at {url}")
    print("Close this window or press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url + open_path,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _print_project(project: dict) -> None:
    print(f"Project: {project['id']}  ({projects.project_dir(project['id']) / 'project.json'})")
    for index, slide in enumerate(project["slides"], 1):
        print(f"{index:>2}. [{slide['role']}] {slide['headline'] or '(empty)'}")
        if slide["body"]:
            print(f"    {slide['body']}")
        for bullet in slide["bullets"]:
            print(f"    - {bullet}")
        if slide["notes"]:
            print(f"    ! {slide['notes']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m carouso", description="Carouso: local carousel studio.")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve", help="start the local web UI")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=4173)
    serve_parser.add_argument("--open", action="store_true", help="open the UI in the default browser")
    serve_parser.add_argument("--open-path", default="", help="path to open with --open")
    new = sub.add_parser("new", help="create a project from a brief JSON file and write its content")
    new.add_argument("--brief", required=True, help="JSON file with topic, audience, structure, slides, ...")
    new.add_argument("--no-generate", action="store_true", help="only create the empty outline")
    regen = sub.add_parser("generate", help="(re)write the content of an existing project; locked slides stay")
    regen.add_argument("project")
    regen.add_argument("--slide", help="regenerate only this slide id")
    show = sub.add_parser("show", help="print a project")
    show.add_argument("project")
    sub.add_parser("list", help="list projects")
    args = parser.parse_args()

    if args.command == "serve":
        serve(args.host, args.port, args.open, args.open_path)
        return
    try:
        if args.command == "list":
            for item in projects.list_projects():
                print(f"{item['id']}  {item['updated']}  {item['topic']}")
            return
        if args.command == "new":
            project = projects.create(json.loads(Path(args.brief).read_text(encoding="utf-8-sig")))
            if not args.no_generate:
                project = projects.save(content.generate_all(project))
        elif args.command == "generate":
            project = projects.load(args.project)
            project = content.generate_one(project, args.slide) if args.slide else content.generate_all(project)
            project = projects.save(project)
        else:
            project = projects.load(args.project)
        _print_project(project)
        for issue in content.check(project):
            print(f"[{issue['level']}] {issue['message']}")
    except (content.GenerationError, ValueError, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
