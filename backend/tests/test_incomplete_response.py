"""A partial HTTP 200 must never become a trusted first baseline."""

import asyncio
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
from app.core.status import STATUS_AVAILABILITY_ISSUE
from app.db.session import Base
from app.models import Snapshot, Target
from app.services.checks import run_target_check

_BODY = b"<html><body>partial response"


@pytest.mark.parametrize(
    ("failure", "framing"),
    [
        ("stall", "content-length"),
        ("reset", "content-length"),
        ("stall", "close-delimited"),
        ("reset", "close-delimited"),
        ("stall", "chunked"),
        ("reset", "chunked"),
    ],
)
@pytest.mark.parametrize("existing_baseline", [False, True])
async def test_partial_http_200_is_not_saved_as_baseline(
    tmp_path: Path, failure: str, framing: str, existing_baseline: bool
) -> None:
    length_header = b"Content-Length: 4096\r\n" if framing == "content-length" else b""
    body = _BODY
    if framing == "chunked":
        length_header = b"Transfer-Encoding: chunked\r\n"
        body = f"{len(_BODY):x}\r\n".encode() + _BODY + b"\r\n"
    partial_response = (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
        + length_header
        + b"Connection: close\r\n\r\n"
        + body
    )
    release = asyncio.Event()
    server: asyncio.Server | None = None
    listener: socket.socket | None = None
    server_thread: threading.Thread | None = None
    partial_sent = threading.Event()

    if failure == "stall":
        async def stall_after_partial(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(partial_response)
            await writer.drain()
            partial_sent.set()
            await release.wait()
            writer.close()

        server = await asyncio.start_server(stall_after_partial, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
    else:
        listener = socket.create_server(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        def reset_after_partial() -> None:
            assert listener is not None
            connection, _ = listener.accept()
            try:
                connection.recv(4096)
                connection.sendall(partial_response)
                partial_sent.set()
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            finally:
                connection.close()

        server_thread = threading.Thread(target=reset_after_partial, daemon=True)
        server_thread.start()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        target = Target(name="Partial response", url=f"http://allowed.test:{port}/")
        db.add(target)
        db.commit()
        db.refresh(target)
        baseline = None
        if existing_baseline:
            baseline = Snapshot(
                target_id=target.id, final_url=target.url, http_status=200,
                screenshot_path="old.png", text_path="old.txt", html_path="old.html",
                is_baseline=True,
            )
            db.add(baseline)
            db.commit()

        settings = Settings(
            DATA_DIR=str(tmp_path), PAGE_TIMEOUT_SECONDS=2, PAGE_STABILIZE_ENABLED=False
        )
        try:
            with (
                patch("app.services.capture.capture.validate_url"),
                patch(
                    "app.services.capture.ssrf_proxy.resolve_host_ips",
                    return_value=[ipaddress.ip_address("127.0.0.1")],
                ),
                patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False),
            ):
                result = await asyncio.wait_for(
                    run_target_check(db, target, settings), timeout=15
                )
        finally:
            release.set()
            if server is not None:
                server.close()
                await server.wait_closed()
            if listener is not None:
                listener.close()
            if server_thread is not None:
                server_thread.join(timeout=5)

        assert partial_sent.is_set(), "The fixture must send its partial HTTP 200"
        assert result.status == STATUS_AVAILABILITY_ISSUE
        assert result.snapshot is None
        snapshots = list(db.scalars(select(Snapshot).where(Snapshot.target_id == target.id)))
        assert snapshots == ([baseline] if baseline is not None else [])
        if baseline is not None:
            assert baseline.is_baseline and baseline.html_path == "old.html"
        staging_dir = tmp_path / "staging"
        assert not staging_dir.exists() or not list(staging_dir.iterdir())
