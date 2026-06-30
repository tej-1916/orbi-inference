"""ORBI Node process entry point."""

import asyncio
import signal

import structlog
from pydantic import ValidationError

from orbi_node.client import GatewayClient
from orbi_node.config import get_settings
from orbi_node.hardware import discover_capabilities
from orbi_node.logging import configure_logging
from orbi_node.runtimes import create_runtime
from orbi_node.worker import OrbiWorker


async def async_main() -> None:
    """Validate first, then construct all network-aware components."""
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = OrbiWorker(
        settings,
        GatewayClient(settings),
        create_runtime(settings),
        discover_capabilities(),
    )
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_name, lambda: asyncio.create_task(worker.stop()))
    await worker.run()


def main() -> None:
    try:
        asyncio.run(async_main())
    except ValidationError:
        structlog.get_logger(__name__).error("invalid_node_configuration")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
