import asyncio
import ipaddress
import socket
import struct
import threading
from unittest.mock import patch

from app.core.config import Settings
from app.core.errors import CaptureError, UpstreamConnectionError
from app.services.capture.ssrf_proxy import SsrfProxy
from app.services.checks import is_availability_error


def _connect_request(proxy: SsrfProxy, host: str, port: int) -> bytes:
    return (
        f"CONNECT {host}:{port} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n\r\n"
    ).encode()


async def test_proxy_blocks_private_ip_before_opening_upstream_socket() -> None:
    connection_count = 0

    async def destination(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal connection_count
        connection_count += 1
        writer.close()

    destination_server = await asyncio.start_server(destination, "127.0.0.1", 0)
    destination_port = destination_server.sockets[0].getsockname()[1]
    try:
        async with SsrfProxy(Settings()) as proxy:
            proxy_port = int(proxy.server_url.rsplit(":", 1)[1])
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
            with patch(
                "app.services.capture.ssrf_proxy.resolve_host_ips",
                return_value=[ipaddress.ip_address("127.0.0.1")],
            ):
                writer.write(_connect_request(proxy, "blocked.test", destination_port))
                await writer.drain()
                response = await reader.read()
            writer.close()
            await writer.wait_closed()
    finally:
        destination_server.close()
        await destination_server.wait_closed()

    assert response.startswith(b"HTTP/1.1 403")
    assert connection_count == 0
    rejection = proxy.pop_rejection(f"https://blocked.test:{destination_port}/")
    assert rejection is not None
    assert "blocked address" in str(rejection)


async def _open_proxy_client(proxy: SsrfProxy) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    proxy_port = int(proxy.server_url.rsplit(":", 1)[1])
    return await asyncio.open_connection("127.0.0.1", proxy_port)


def _allow_loopback():
    """Resolve every host to loopback and let it past the guard for local servers."""
    return (
        patch(
            "app.services.capture.ssrf_proxy.resolve_host_ips",
            return_value=[ipaddress.ip_address("127.0.0.1")],
        ),
        patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False),
    )


async def test_proxy_delivers_full_response_after_client_half_close() -> None:
    body = b"x" * (512 * 1024)

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # Respond only once the client has finished sending (EOF), after a delay,
        # so the old tunnel would already have torn the connection down.
        await reader.read()
        await asyncio.sleep(0.2)
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    destination_server = await asyncio.start_server(destination, "127.0.0.1", 0)
    destination_port = destination_server.sockets[0].getsockname()[1]
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings()) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                writer.write(
                    f"GET http://site.test:{destination_port}/ HTTP/1.1\r\n"
                    f"Host: site.test:{destination_port}\r\n\r\n".encode()
                )
                await writer.drain()
                writer.write_eof()
                response = await asyncio.wait_for(reader.read(), timeout=10)
                writer.close()
                await writer.wait_closed()
    finally:
        destination_server.close()
        await destination_server.wait_closed()

    assert response.startswith(b"HTTP/1.1 200 OK")
    assert response.endswith(body)


async def test_proxy_closes_tunnel_when_upstream_stalls() -> None:
    release = asyncio.Event()

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await release.wait()
        writer.close()

    destination_server = await asyncio.start_server(destination, "127.0.0.1", 0)
    destination_port = destination_server.sockets[0].getsockname()[1]
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings(PAGE_TIMEOUT_SECONDS=1)) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                writer.write(
                    f"GET http://site.test:{destination_port}/ HTTP/1.1\r\n"
                    f"Host: site.test:{destination_port}\r\n\r\n".encode()
                )
                await writer.drain()
                response = await asyncio.wait_for(reader.read(), timeout=5)
                writer.close()
                await writer.wait_closed()
    finally:
        release.set()
        destination_server.close()
        await destination_server.wait_closed()

    assert response == b""
    rejection = proxy.pop_rejection(f"http://site.test:{destination_port}/")
    assert isinstance(rejection, UpstreamConnectionError)
    assert "timed out" in str(rejection)
    assert is_availability_error(rejection)


async def test_proxy_records_reset_before_response() -> None:
    # A raw socket, because asyncio's transport.abort() does not reliably send RST.
    listener = socket.create_server(("127.0.0.1", 0))
    destination_port = listener.getsockname()[1]

    def reset_after_request() -> None:
        conn, _addr = listener.accept()
        conn.recv(4096)
        # SO_LINGER with a zero timeout makes close() send RST instead of FIN.
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        conn.close()

    server_thread = threading.Thread(target=reset_after_request, daemon=True)
    server_thread.start()
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings()) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                writer.write(
                    f"GET http://site.test:{destination_port}/ HTTP/1.1\r\n"
                    f"Host: site.test:{destination_port}\r\n\r\n".encode()
                )
                await writer.drain()
                await asyncio.wait_for(reader.read(), timeout=10)
                writer.close()
                await writer.wait_closed()
    finally:
        server_thread.join(timeout=5)
        listener.close()

    rejection = proxy.pop_rejection(f"http://site.test:{destination_port}/")
    assert isinstance(rejection, UpstreamConnectionError)
    assert "connection reset" in str(rejection)
    assert is_availability_error(rejection)


async def test_proxy_records_reset_after_opaque_tunnel_bytes() -> None:
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    release = threading.Event()
    payload = b"\x16\x03\x03\x00\x04test"

    def destination() -> None:
        connection, _ = listener.accept()
        try:
            connection.recv(4096)
            connection.sendall(payload)
            release.wait(5)
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        finally:
            connection.close()

    thread = threading.Thread(target=destination, daemon=True)
    thread.start()
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings(PAGE_TIMEOUT_SECONDS=2)) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                try:
                    writer.write(_connect_request(proxy, "site.test", port))
                    await writer.drain()
                    assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
                    writer.write(payload)
                    await writer.drain()
                    assert await asyncio.wait_for(reader.readexactly(len(payload)), 5) == payload
                    release.set()
                    try:
                        await asyncio.wait_for(reader.read(), 5)
                    except ConnectionResetError:
                        pass
                    rejection = proxy.pop_rejection(f"https://site.test:{port}/")
                    assert isinstance(rejection, UpstreamConnectionError)
                    assert "connection reset" in str(rejection)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except ConnectionResetError:
                        pass
    finally:
        release.set()
        listener.close()
        thread.join(timeout=5)


async def test_proxy_does_not_blame_site_for_idle_keep_alive() -> None:
    release = asyncio.Event()

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        await release.wait()
        writer.close()

    destination_server = await asyncio.start_server(destination, "127.0.0.1", 0)
    destination_port = destination_server.sockets[0].getsockname()[1]
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings(PAGE_TIMEOUT_SECONDS=1)) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                writer.write(
                    f"GET http://site.test:{destination_port}/ HTTP/1.1\r\n"
                    f"Host: site.test:{destination_port}\r\n\r\n".encode()
                )
                await writer.drain()
                response = await asyncio.wait_for(reader.read(), timeout=5)
                writer.close()
                await writer.wait_closed()
    finally:
        release.set()
        destination_server.close()
        await destination_server.wait_closed()

    assert response.endswith(b"ok")
    assert proxy.pop_rejection(f"http://site.test:{destination_port}/") is None


async def test_proxy_tracks_head_then_chunked_on_same_connection() -> None:
    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            assert head.startswith(b"HEAD ")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 999\r\n\r\n")
            await writer.drain()
            get = await reader.readuntil(b"\r\n\r\n")
            assert get.startswith(b"GET ")
            writer.write(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n2\r\nok\r\n0\r\nX-Test: done\r\n\r\n"
            )
            await writer.drain()
        finally:
            writer.close()

    server = await asyncio.start_server(destination, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings(PAGE_TIMEOUT_SECONDS=2)) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                try:
                    for method in ("HEAD", "GET"):
                        writer.write(
                            f"{method} http://site.test:{port}/ HTTP/1.1\r\n"
                            f"Host: site.test:{port}\r\n\r\n".encode()
                        )
                        await writer.drain()
                        headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
                        assert headers.startswith(b"HTTP/1.1 200")
                    body = await asyncio.wait_for(reader.read(), 5)
                    assert body == b"2\r\nok\r\n0\r\nX-Test: done\r\n\r\n"
                    assert proxy.pop_rejection(f"http://site.test:{port}/") is None
                finally:
                    writer.close()
                    await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()


async def test_proxy_does_not_blame_site_for_unused_preconnect() -> None:
    release = asyncio.Event()

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await release.wait()
        writer.close()

    destination_server = await asyncio.start_server(destination, "127.0.0.1", 0)
    destination_port = destination_server.sockets[0].getsockname()[1]
    resolve_patch, guard_patch = _allow_loopback()
    try:
        with resolve_patch, guard_patch:
            async with SsrfProxy(Settings(PAGE_TIMEOUT_SECONDS=1)) as proxy:
                reader, writer = await _open_proxy_client(proxy)
                writer.write(_connect_request(proxy, "site.test", destination_port))
                await writer.drain()
                response = await asyncio.wait_for(reader.read(), timeout=5)
                writer.close()
                await writer.wait_closed()
    finally:
        release.set()
        destination_server.close()
        await destination_server.wait_closed()

    assert response.startswith(b"HTTP/1.1 200 Connection Established")
    assert proxy.pop_rejection(f"https://site.test:{destination_port}/") is None


async def test_proxy_local_socket_error_is_not_an_availability_issue() -> None:
    async def deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    resolve_patch, guard_patch = _allow_loopback()
    with resolve_patch, guard_patch:
        async with SsrfProxy(Settings()) as proxy:
            # Connect first: the patch below must only affect the proxy's upstream dial.
            reader, writer = await _open_proxy_client(proxy)
            with patch("app.services.capture.ssrf_proxy.asyncio.open_connection", deny):
                writer.write(_connect_request(proxy, "site.test", 443))
                await writer.drain()
                response = await asyncio.wait_for(reader.read(), timeout=10)
            writer.close()
            await writer.wait_closed()

    assert response.startswith(b"HTTP/1.1 502")
    rejection = proxy.pop_rejection("https://site.test/")
    assert isinstance(rejection, CaptureError)
    assert not isinstance(rejection, UpstreamConnectionError)
    assert "Permission denied" in str(rejection)
    assert not is_availability_error(rejection)


async def test_proxy_closes_client_that_never_sends_headers() -> None:
    async with SsrfProxy(Settings(PAGE_TIMEOUT_SECONDS=1)) as proxy:
        reader, writer = await _open_proxy_client(proxy)
        response = await asyncio.wait_for(reader.read(), timeout=5)
        writer.close()
        await writer.wait_closed()

    assert response.startswith(b"HTTP/1.1 502")


async def test_proxy_records_connection_refused_as_upstream_error() -> None:
    probe = await asyncio.start_server(lambda _r, _w: None, "127.0.0.1", 0)
    closed_port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()

    resolve_patch, guard_patch = _allow_loopback()
    with resolve_patch, guard_patch:
        async with SsrfProxy(Settings()) as proxy:
            reader, writer = await _open_proxy_client(proxy)
            writer.write(_connect_request(proxy, "down.test", closed_port))
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), timeout=10)
            writer.close()
            await writer.wait_closed()

    assert response.startswith(b"HTTP/1.1 502")
    rejection = proxy.pop_rejection(f"https://down.test:{closed_port}/")
    assert isinstance(rejection, UpstreamConnectionError)
    assert "connection refused" in str(rejection)
    assert is_availability_error(rejection)
