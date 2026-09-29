import asyncio
import ipaddress
from unittest.mock import patch

from app.core.config import Settings
from app.services.capture.ssrf_proxy import SsrfProxy


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
