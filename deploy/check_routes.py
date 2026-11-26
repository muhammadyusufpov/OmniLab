#!/usr/bin/env python3
"""Check that a deployed OmniLab serves its three main entry routes."""

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, build_opener


ROUTES = (
    ("Homepage", "/"),
    ("Chemistry lab", "/lab/"),
    ("Reaction guide", "/guides/sodium-and-chlorine-reaction/"),
)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Origin to check, such as https://omnilab-bk8q.onrender.com")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path not in ("", "/"):
        parser.error("base_url must be an http(s) origin without a path")

    opener = build_opener(NoRedirects)
    failed = False
    for label, path in ROUTES:
        url = urljoin(args.base_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            with opener.open(url, timeout=10) as response:
                status = response.status
            if status != 200:
                raise ValueError(f"HTTP {status}")
            print(f"PASS {label}: {url} (HTTP 200)")
        except (HTTPError, URLError, ValueError, TimeoutError) as error:
            detail = f"HTTP {error.code}" if isinstance(error, HTTPError) else str(error)
            print(f"FAIL {label}: {url} ({detail})", file=sys.stderr)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
