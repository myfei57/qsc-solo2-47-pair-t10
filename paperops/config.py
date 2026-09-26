"""Start up settings for the control service."""

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Runtime settings resolved once at start up."""

    host: str = "127.0.0.1"
    port: int = 8123
    data_dir: str = "data"
    web_dir: str = "web"

    def listen(self) -> tuple[str, int]:
        return (self.host, self.port)


def parse_args(argv: list[str] | None = None) -> Config:
    """Build a :class:`Config` from command line arguments."""
    parser = argparse.ArgumentParser(prog="python -m paperops")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--data", dest="data_dir", default="data")
    parser.add_argument("--web", dest="web_dir", default="web")
    namespace = parser.parse_args(argv)
    return Config(
        host=namespace.host,
        port=namespace.port,
        data_dir=namespace.data_dir,
        web_dir=namespace.web_dir,
    )
