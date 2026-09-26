"""Request and response types used by the console."""

import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

JSON_CONTENT_TYPE = "application/json; charset=utf-8"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"


@dataclass(frozen=True)
class Request:
    """A parsed console request, independent of the transport."""

    method: str
    path: str
    query: Mapping[str, str]
    body_text: str = ""

    @classmethod
    def parse(cls, method: str, target: str, body_text: str = "") -> "Request":
        split = urlsplit(target)
        raw = parse_qs(split.query, keep_blank_values=True)
        query = {key: values[-1] for key, values in raw.items()}
        return cls(
            method=method.upper(),
            path=split.path or "/",
            query=query,
            body_text=body_text,
        )

    def param(self, name: str, default: str | None = None) -> str | None:
        value = self.query.get(name)
        if value is None or value == "":
            return default
        return value

    def integer(self, name: str, default: int = 0) -> int:
        raw = self.param(name)
        if raw is None:
            return default
        return int(raw)

    def number(self, name: str, default: float = 0.0) -> float:
        raw = self.param(name)
        if raw is None:
            return default
        return float(raw)

    def body(self) -> dict[str, Any]:
        """Decoded JSON body; an absent body decodes to an empty mapping."""
        if not self.body_text.strip():
            return {}
        decoded = json.loads(self.body_text)
        if not isinstance(decoded, dict):
            raise ValueError("request body has to be a JSON object")
        return decoded


@dataclass(frozen=True)
class Response:
    """A console response."""

    status: int
    body: Any
    content_type: str = JSON_CONTENT_TYPE

    def to_bytes(self) -> bytes:
        if self.content_type == JSON_CONTENT_TYPE:
            text = json.dumps(self.body, sort_keys=True, ensure_ascii=False)
            return text.encode("utf-8")
        if isinstance(self.body, bytes):
            return self.body
        return str(self.body).encode("utf-8")


def json_response(body: Any, status: int = 200) -> Response:
    return Response(status=status, body=body, content_type=JSON_CONTENT_TYPE)


def html_response(text: str, status: int = 200) -> Response:
    return Response(status=status, body=text, content_type=HTML_CONTENT_TYPE)


def error_response(message: str, status: int = 400) -> Response:
    return json_response({"error": message, "status": status}, status)
