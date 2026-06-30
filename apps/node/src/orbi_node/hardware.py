"""Minimal hardware discovery with no privileged access."""

import hashlib
import os
import platform
import socket
from pathlib import Path

from orbi_node.schemas import WorkerCapabilities


def discover_capabilities() -> WorkerCapabilities:
    """Return scheduling capabilities without exposing the raw hostname."""
    hostname_hash = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:16]
    return WorkerCapabilities(
        hostname_hash=hostname_hash,
        architecture=platform.machine() or "unknown",
        operating_system=platform.system().lower() or "unknown",
        cpu_count=os.cpu_count() or 1,
        memory_bytes=_memory_bytes(),
    )


def _memory_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None
