"""Classify network and local failures through the real capture pipeline."""

import asyncio
import errno
import ipaddress
import socket
import struct
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.status import STATUS_AVAILABILITY_ISSUE, STATUS_FAILED, STATUS_OK
from app.db.session import Base
from app.models import Snapshot, Target
from app.services.checks import TargetCheckResult, run_target_check


async def _check_target(
    tmp_path: Path, port: int, dial_error: OSError | None = None
) -> tuple[TargetCheckResult, int]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    original_open_connection = asyncio.open_connection

    async def dial(host: str, requested_port: int, *args: object, **kwargs: object):
        if dial_error is not None and host == "127.0.0.1" and requested_port == port:
            raise dial_error
        return await original_open_connection(host, requested_port, *args, **kwargs)

    with Session(engine) as db:
        target = Target(name="Capture failure", url=f"http://allowed.test:{port}/")
        db.add(target)
        db.commit()
        db.refresh(target)
        with (
            patch("app.services.capture.capture.validate_url"),
            patch(
                "app.services.capture.ssrf_proxy.resolve_host_ips",
                return_value=[ipaddress.ip_address("127.0.0.1")],
            ),
            patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False),
            patch("app.services.capture.ssrf_proxy.asyncio.open_connection", side_effect=dial),
        ):
            result = await asyncio.wait_for(
                run_target_check(
                    db,
                    target,
                    Settings(
                        DATA_DIR=str(tmp_path),
                        PAGE_TIMEOUT_SECONDS=2,
                        PAGE_STABILIZE_ENABLED=False,
                    ),
                ),
                timeout=15,
            )
        snapshots = db.scalars(select(Snapshot).where(Snapshot.target_id == target.id))
        snapshot_count = len(list(snapshots))
    engine.dispose()
    return result, snapshot_count


async def test_capture_connection_refused_is_availability_issue(tmp_path: Path) -> None:
    result, snapshots = await _check_target(
        tmp_path, 8765, ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
    )
    assert result.status == STATUS_AVAILABILITY_ISSUE
    assert "refused" in (result.error or "").lower()
    assert snapshots == 0


async def test_capture_upstream_timeout_is_availability_issue(tmp_path: Path) -> None:
    release = asyncio.Event()
    request_received = asyncio.Event()

    async def silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        request_received.set()
        await release.wait()
        writer.close()

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result, snapshots = await _check_target(tmp_path, port)
    finally:
        release.set()
        server.close()
        await server.wait_closed()

    assert request_received.is_set()
    assert result.status == STATUS_AVAILABILITY_ISSUE
    assert snapshots == 0


async def test_capture_upstream_reset_is_availability_issue(tmp_path: Path) -> None:
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    request_received = threading.Event()

    def reset_before_response() -> None:
        connection, _ = listener.accept()
        try:
            connection.recv(4096)
            request_received.set()
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        finally:
            connection.close()

    thread = threading.Thread(target=reset_before_response, daemon=True)
    thread.start()
    try:
        result, snapshots = await _check_target(tmp_path, port)
    finally:
        listener.close()
        thread.join(timeout=5)

    assert request_received.is_set()
    assert result.status == STATUS_AVAILABILITY_ISSUE
    assert snapshots == 0


@pytest.mark.parametrize(
    "dial_error",
    [PermissionError(errno.EACCES, "Permission denied"), OSError(errno.EMFILE, "Too many files")],
    ids=["permission", "resource"],
)
async def test_capture_local_socket_error_is_failed(
    tmp_path: Path, dial_error: OSError
) -> None:
    result, snapshots = await _check_target(tmp_path, 8765, dial_error)
    assert result.status == STATUS_FAILED
    assert snapshots == 0


@pytest.mark.parametrize("framing", ["content-length", "chunked", "close-delimited"])
async def test_capture_complete_response_is_ok(tmp_path: Path, framing: str) -> None:
    release = asyncio.Event()
    response_sent = asyncio.Event()

    async def keep_alive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        body = b"<html><body>complete page</body></html>"
        if framing == "content-length":
            headers = f"Content-Length: {len(body)}\r\n".encode()
        elif framing == "chunked":
            headers = b"Transfer-Encoding: chunked\r\n"
            body = f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\nX-Test: done\r\n\r\n"
        else:
            headers = b"Connection: close\r\n"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
            + headers + b"\r\n"
            + body
        )
        await writer.drain()
        response_sent.set()
        if framing != "close-delimited":
            await release.wait()
        writer.close()

    server = await asyncio.start_server(keep_alive, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result, snapshots = await _check_target(tmp_path, port)
    finally:
        release.set()
        server.close()
        await server.wait_closed()

    assert response_sent.is_set()
    assert result.status == STATUS_OK
    assert result.snapshot is not None and result.snapshot.is_baseline
    assert snapshots == 1
