"""Loopback HTTP proxy that binds SSRF validation to the socket it opens.

Both Chromium and Playwright's BrowserContext request client use this proxy.  DNS
is resolved here once, the resulting addresses are checked, and the upstream
socket is opened to one of those exact addresses.  This closes the validation to
connection gap left by resolving in a route handler and connecting by hostname.
"""

import asyncio
import logging
from collections import defaultdict, deque
from contextlib import suppress
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlsplit

from playwright.async_api import ProxySettings

from app.core.config import Settings
from app.core.errors import DnsResolutionError, SsrfBlockedError
from app.core.ssrf_guard import is_blocked_address, resolve_host_ips, validate_scheme

logger = logging.getLogger(__name__)

_MAX_HEADER_BYTES = 64 * 1024
_STREAM_CHUNK_BYTES = 64 * 1024


class SsrfProxy:
    """A per-capture loopback proxy with fail-closed destination checks."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._rejections: dict[tuple[str, int], deque[Exception]] = defaultdict(deque)

    async def __aenter__(self) -> "SsrfProxy":
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in tuple(self._writers):
            writer.close()
        if self._writers:
            await asyncio.gather(
                *(writer.wait_closed() for writer in tuple(self._writers)),
                return_exceptions=True,
            )
        self._writers.clear()

    @property
    def server_url(self) -> str:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("SSRF proxy has not been started")
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    @property
    def playwright_proxy(self) -> ProxySettings:
        return ProxySettings(server=self.server_url)

    def pop_rejection(self, url: str) -> Exception | None:
        parsed = urlsplit(url)
        if not parsed.hostname:
            return None
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        key = (parsed.hostname.lower(), parsed.port or default_port)
        errors = self._rejections.get(key)
        if not errors:
            return None
        error = errors.popleft()
        if not errors:
            self._rejections.pop(key, None)
        return error

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._writers.add(writer)
        upstream_writer: asyncio.StreamWriter | None = None
        destination: tuple[str, int] | None = None
        try:
            header_block = await _read_headers(reader)
            request_line, headers = _parse_request_headers(header_block)
            method, target, version = request_line.split(" ", 2)
            if method.upper() == "CONNECT":
                host, port = _parse_authority(target)
                destination = (host.lower(), port)
                upstream_reader, upstream_writer = await self._connect_allowed(
                    host,
                    port,
                    "https",
                )
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                parsed = urlsplit(target)
                if parsed.scheme.lower() != "http" or not parsed.hostname:
                    raise SsrfBlockedError("Proxy accepts absolute HTTP URLs only")
                port = parsed.port or 80
                destination = (parsed.hostname.lower(), port)
                upstream_reader, upstream_writer = await self._connect_allowed(
                    parsed.hostname,
                    port,
                    "http",
                )
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                forwarded = _build_forward_headers(method, path, version, headers)
                upstream_writer.write(forwarded)
                await upstream_writer.drain()

            await _tunnel(reader, writer, upstream_reader, upstream_writer)
        except (DnsResolutionError, SsrfBlockedError) as exc:
            logger.warning("Capture proxy blocked request: %s", exc)
            if destination is not None:
                self._rejections[destination].append(exc)
            if not writer.is_closing():
                status = 502 if isinstance(exc, DnsResolutionError) else 403
                await _write_error(writer, status, "Destination rejected")
        except (OSError, ValueError, asyncio.IncompleteReadError) as exc:
            logger.warning("Capture proxy connection failed: %s", exc)
            if not writer.is_closing():
                await _write_error(writer, 502, "Upstream connection failed")
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                with suppress(OSError):
                    await upstream_writer.wait_closed()
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            self._writers.discard(writer)

    async def _connect_allowed(
        self,
        hostname: str,
        port: int,
        scheme: str,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        validate_scheme(f"{scheme}://{_format_host(hostname)}:{port}/", self._settings)
        ips = await asyncio.to_thread(resolve_host_ips, hostname)
        allowed: list[IPv4Address | IPv6Address] = []
        for ip in ips:
            if is_blocked_address(ip):
                raise SsrfBlockedError(
                    f"Blocked by SSRF guard: {hostname} resolved to blocked address {ip}"
                )
            allowed.append(ip)

        last_error: OSError | None = None
        for ip in allowed:
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(str(ip), port),
                    timeout=float(self._settings.PAGE_TIMEOUT_SECONDS),
                )
            except OSError as exc:
                last_error = exc
        raise OSError(f"Could not connect to {hostname}:{port}") from last_error


async def _read_headers(reader: asyncio.StreamReader) -> bytes:
    try:
        return await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError as exc:
        raise ValueError("Proxy request headers are too large") from exc


def _parse_request_headers(block: bytes) -> tuple[str, list[tuple[str, str]]]:
    if len(block) > _MAX_HEADER_BYTES:
        raise ValueError("Proxy request headers are too large")
    lines = block.decode("iso-8859-1").split("\r\n")
    if len(lines[0].split(" ", 2)) != 3:
        raise ValueError("Malformed proxy request line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("Malformed proxy request header")
        name, value = line.split(":", 1)
        headers.append((name.strip(), value.strip()))
    return lines[0], headers


def _parse_authority(authority: str) -> tuple[str, int]:
    parsed = urlsplit(f"//{authority}")
    if not parsed.hostname:
        raise ValueError("CONNECT target has no hostname")
    return parsed.hostname, parsed.port or 443


def _format_host(hostname: str) -> str:
    return f"[{hostname}]" if ":" in hostname else hostname


def _build_forward_headers(
    method: str,
    path: str,
    version: str,
    headers: list[tuple[str, str]],
) -> bytes:
    kept = [
        (name, value)
        for name, value in headers
        if name.lower() not in {"proxy-authorization", "proxy-connection"}
    ]
    lines = [f"{method} {path} {version}", *(f"{name}: {value}" for name, value in kept)]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1")


async def _tunnel(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> None:
    async def copy(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
        try:
            while chunk := await source.read(_STREAM_CHUNK_BYTES):
                destination.write(chunk)
                await destination.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            with suppress(OSError):
                destination.write_eof()

    tasks = {
        asyncio.create_task(copy(client_reader, upstream_writer)),
        asyncio.create_task(copy(upstream_reader, client_writer)),
    }
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _write_error(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    body = f"{status} {reason}\n".encode()
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n".encode()
        + body
    )
    with suppress(ConnectionError, OSError):
        await writer.drain()
