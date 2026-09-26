"""Static status pages served by the console."""

import os

from .http import Response, error_response, html_response

PAGE_NAMES: tuple[str, ...] = (
    "index.html",
    "operations.html",
    "curves.html",
    "audit.html",
)


def page_names() -> tuple[str, ...]:
    return PAGE_NAMES


def read_page(web_dir: str, name: str) -> Response:
    """Load a status page from the configured web directory."""
    path = os.path.join(web_dir, name)
    if not os.path.isfile(path):
        return error_response(f"page {name} is not available", status=404)
    with open(path, "r", encoding="utf-8") as handle:
        return html_response(handle.read())
