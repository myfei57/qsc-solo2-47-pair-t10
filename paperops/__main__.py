"""Command line entry point: ``python -m paperops``."""

from .app import build_services
from .config import parse_args
from .console.server import serve


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    services = build_services(config)
    print(f"control console listening on http://{config.host}:{config.port}", flush=True)
    print(
        f"committed keys {len(services.journal.keys())} "
        f"at watermark {services.journal.watermark}",
        flush=True,
    )
    serve(config, services.console)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
