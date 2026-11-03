"""Local HTTP server for the DIP and CHS-DRG 3.0 rule demos."""

from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from drg_grouping import catalog as drg_catalog
from drg_grouping import group_case as drg_group_case
from drg_grouping import search_catalog
from grouping import ROOT, catalog, group_case, load_rules

PUBLIC_FILES = {
    "/", "/index.html", "/flow.html", "/styles.css", "/flow.css",
    "/app.js", "/assets/pku-logo.png",
    "/flow.js",
}


class DemoHandler(SimpleHTTPRequestHandler):
    rules = load_rules()
    suggestions = catalog(rules)
    drg_summary = drg_catalog()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path)
        params = parse_qs(route.query)
        if route.path == "/api/catalog":
            self._json(200, self.drg_summary if params.get("mode") == ["drg"] else self.suggestions)
        elif route.path == "/api/search":
            if params.get("mode") != ["drg"]:
                self._json(400, {"error": "仅 DRG 模式使用此查询接口"})
                return
            kind = params.get("kind", [""])[0]
            if kind not in ("dx", "op"):
                self._json(400, {"error": "kind 必须是 dx 或 op"})
                return
            query = params.get("q", [""])[0][:100]
            self._json(200, {"suggestions": search_catalog(kind, query)})
        elif route.path.startswith("/api/"):
            self._json(404, {"error": "接口不存在"})
        elif urlsplit(self.path).path in PUBLIC_FILES:
            super().do_GET()
        else:
            self.send_error(404, "Not Found")

    def do_HEAD(self):
        if urlsplit(self.path).path in PUBLIC_FILES:
            super().do_HEAD()
        else:
            self.send_error(404, "Not Found")

    def end_headers(self):
        if urlsplit(self.path).path in PUBLIC_FILES:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_POST(self):
        if self.path != "/api/group":
            self._json(404, {"error": "接口不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 64 * 1024:
                raise ValueError("请求体大小不符合要求")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("请求内容必须是病例对象")
            for key in ("diagnoses", "operations"):
                if key in payload and (not isinstance(payload[key], list) or
                                       len(payload[key]) > 100 or
                                       any(not isinstance(code, str) or len(code) > 100 for code in payload[key])):
                    raise ValueError(f"{key} 必须是编码列表")
            mode = payload.get("mode", "dip")
            if mode == "drg":
                self._json(200, drg_group_case(payload))
            elif mode == "dip":
                self._json(200, group_case(self.rules, payload))
            else:
                raise ValueError("mode 必须是 dip 或 drg")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="DIP / DRG 3.0 分组演示服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"DIP / DRG 3.0 demo: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
