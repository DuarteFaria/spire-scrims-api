"""Serve the Swagger UI docs with a same-origin proxy to the Scrims API.

The API doesn't send CORS headers, so "Try it out" in the browser can't call
it directly. This server makes it work by serving docs/ and forwarding any
/api/* request to the real API — the browser only ever talks to one origin.

Usage:
    python3 scripts/serve_docs.py
    python3 scripts/serve_docs.py --port 9000

Environment (read from scripts/.env if present; shell variables take precedence):
    SCRIMS_API_URL   API base URL (required).
    SCRIMS_API_KEY   API bearer token (required).

Then open http://localhost:8000. Proxied requests are authenticated using the
API key on the server; the key is never sent to the browser.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from email.message import Message
from functools import partial
from http.client import HTTPResponse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, cast

from dotenv import load_dotenv

_ = load_dotenv(Path(__file__).parent / ".env")

DOCS_DIR = Path(__file__).parent.parent / "docs"

# Hop-by-hop headers that must not be forwarded either direction.
SKIP_HEADERS = {
    "host",
    "connection",
    "transfer-encoding",
    "content-length",
    "keep-alive",
}
REQUEST_TIMEOUT_SECONDS = 30


class Arguments(argparse.Namespace):
    """Typed command-line arguments."""

    port: int = 8000


class DocsHandler(SimpleHTTPRequestHandler):
    """Serve documentation files and proxy API requests."""

    target: ClassVar[str] = ""
    api_key: ClassVar[str] = ""

    def _proxy(self) -> None:
        url = f"{self.target}{self.path}"
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in SKIP_HEADERS | {"authorization"}
        }
        headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url, data=body, headers=headers, method=self.command
        )
        try:
            response = cast(
                HTTPResponse,
                urllib.request.urlopen(
                    request,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                ),
            )
            with response:
                self._send_upstream(
                    response.status,
                    response.headers,
                    response.read(),
                )
        except urllib.error.HTTPError as error:  # 4xx/5xx from the API
            self._send_upstream(
                error.code,
                error.headers,
                error.read(),
            )
        except urllib.error.URLError as error:
            message = f"Docs proxy could not reach {self.target}: {error.reason}"
            payload = json.dumps({"error": message}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            _ = self.wfile.write(payload)

    def _send_upstream(
        self,
        status: int,
        headers: Message[str, str],
        payload: bytes,
    ) -> None:
        self.send_response(status)  # already emits Server and Date
        for key, value in headers.items():
            if key.lower() not in SKIP_HEADERS | {"date", "server"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        _ = self.wfile.write(payload)

    def do_GET(self) -> None:  # pyright: ignore[reportImplicitOverride]
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve Swagger UI with a same-origin API proxy."
    )
    _ = parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(namespace=Arguments())

    api_url = os.environ.get("SCRIMS_API_URL")
    api_key = os.environ.get("SCRIMS_API_KEY")
    if not api_url or not api_key:
        missing = [
            name
            for name, value in (
                ("SCRIMS_API_URL", api_url),
                ("SCRIMS_API_KEY", api_key),
            )
            if not value
        ]
        names = ", ".join(missing)
        location = (
            "scripts/.env (see scripts/.env.example) or your shell environment"
        )
        sys.exit(f"{names} must be set in {location}.")

    DocsHandler.target = api_url.rstrip("/")
    DocsHandler.api_key = api_key

    print(f"Docs:  http://localhost:{args.port}")
    print(f"Proxy: /api/* -> {DocsHandler.target}")
    handler = partial(DocsHandler, directory=str(DOCS_DIR))
    try:
        with ThreadingHTTPServer(("localhost", args.port), handler) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
