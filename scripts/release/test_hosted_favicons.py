"""Hosted frontend branding regressions against a local SPA server."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import unittest

from oracle_drone import FAVICON_TYPES, verify_hosted_favicons


PUBLIC = Path(__file__).resolve().parents[2] / "frontend/drone/web/public"
SHELL = PUBLIC.parent.joinpath("index.html").read_bytes().replace(b"%BASE_URL%", b"/")


@contextmanager
def site(changes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            mime, content = "text/html", SHELL
            if self.path.lstrip("/") in FAVICON_TYPES:
                name = self.path[1:]
                mime, content = sorted(FAVICON_TYPES[name])[0], PUBLIC.joinpath(name).read_bytes()
            mime, content = changes.get(self.path, (mime, content))
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield "http://127.0.0.1:" + str(server.server_port)
        finally:
            server.shutdown()
            thread.join()


class HostedFaviconTests(unittest.TestCase):
    def test_branded_files_and_absolute_links_on_both_pages(self):
        with site({}) as origin:
            verify_hosted_favicons(origin, PUBLIC)

    def test_missing_links_nested_relative_url_html_fallback_and_wrong_brand(self):
        cases = [
            ({"/": ("text/html", b"<html><head></head></html>")}, "links on /"),
            ({"/track/favicon-check": ("text/html", SHELL.replace(b'href="/favicon', b'href="favicon'))},
             "links on /track"),
            ({"/favicon.ico": ("text/html", SHELL)}, "media type"),
            ({"/favicon.png": ("image/png", b"unrelated")}, "bytes"),
        ]
        for changes, message in cases:
            with self.subTest(case=message), site(changes) as origin:
                with self.assertRaisesRegex(ValueError, message):
                    verify_hosted_favicons(origin, PUBLIC)

    def test_staging_protection_can_never_be_sent_to_another_origin(self):
        with self.assertRaisesRegex(ValueError, "staging origin"):
            verify_hosted_favicons("https://example.invalid", PUBLIC, "synthetic")
