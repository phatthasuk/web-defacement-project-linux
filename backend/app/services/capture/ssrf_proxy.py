"""Loopback HTTP proxy that binds SSRF validation to the socket it opens.

Both Chromium and Playwright's BrowserContext request client use this proxy.  DNS
is resolved here once, the resulting addresses are checked, and the upstream
socket is opened to one of those exact addresses.  This closes the validation to
connection gap left by resolving in a route handler and connecting by hostname.
"""

import asyncio
import errno
import logging
import socket
import struct
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import suppress
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlsplit

import h11
from playwright.async_api import ProxySettings

from app.core.config import Settings
from app.core.errors import (
    CaptureError,
    DnsResolutionError,
    SsrfBlockedError,
    UpstreamConnectionError,
)
from app.core.ssrf_guard import is_blocked_address, resolve_host_ips, validate_scheme

logger = logging.getLogger(__name__)

_MAX_HEADER_BYTES = 64 * 1024
_STREAM_CHUNK_BYTES = 64 * 1024
# errno values that mean the network path to the site failed, as opposed to a
# fault on this host (permissions, exhausted file descriptors, bad config).
_NETWORK_ERRNOS = frozenset(
    code
    for name in ("ENETUNREACH", "EHOSTUNREACH", "ENETDOWN", "EHOSTDOWN", "ETIMEDOUT")
    if (code := getattr(errno, name, None)) is not None
)


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
        request_sent = False
        exchange: _HttpExchange | None = None
        idle_timeout = float(self._settings.PAGE_TIMEOUT_SECONDS)
        try:
            header_block = await asyncio.wait_for(_read_headers(reader), timeout=idle_timeout)
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
                if not writer.is_closing():
                    try:
                        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                        await writer.drain()
                    except (RuntimeError, ConnectionError, OSError):
                        logger.debug(
                            "Capture proxy client disconnected before CONNECT completed: %s:%d",
                            host,
                            port,
                        )
                        return
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
                exchange = _HttpExchange()
                exchange.request_data(forwarded)
                upstream_writer.write(forwarded)
                await upstream_writer.drain()
                request_sent = True

            rejected = destination

            def record_upstream_failure(reason: str) -> None:
                exc = UpstreamConnectionError(f"Upstream {rejected[0]}:{rejected[1]} {reason}")
                logger.warning("Capture proxy upstream failed: %s", exc)
                self._rejections[rejected].append(exc)

            await _tunnel(
                reader,
                writer,
                upstream_reader,
                upstream_writer,
                idle_timeout,
                request_sent=request_sent,
                on_upstream_failure=record_upstream_failure,
                exchange=exchange,
            )
        except (DnsResolutionError, SsrfBlockedError) as exc:
            logger.warning("Capture proxy blocked request: %s", exc)
            if destination is not None:
                self._rejections[destination].append(exc)
            if not writer.is_closing():
                status = 502 if isinstance(exc, DnsResolutionError) else 403
                await _write_error(writer, status, "Destination rejected")
        except CaptureError as exc:
            # Recorded so the capture reports why the connection failed instead
            # of treating the proxy's own 502 as the target's response. Only
            # UpstreamConnectionError counts as the site being unavailable.
            logger.warning("Capture proxy connection failed: %s", exc)
            if destination is not None:
                self._rejections[destination].append(exc)
            if not writer.is_closing():
                await _write_error(writer, 502, "Upstream connection failed")
        except (
            RuntimeError,
            OSError,
            ValueError,
            asyncio.IncompleteReadError,
            h11.ProtocolError,
        ) as exc:
            logger.debug("Capture proxy client disconnected or connection failed: %s", exc)
            if not writer.is_closing():
                await _write_error(writer, 502, "Upstream connection failed")
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                with suppress(RuntimeError, ConnectionError, OSError):
                    await upstream_writer.wait_closed()
            writer.close()
            with suppress(RuntimeError, ConnectionError, OSError):
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
        if last_error is None:
            raise UpstreamConnectionError(
                f"Upstream {hostname}:{port} has no address to connect to"
            )
        reason = _network_failure_reason(last_error)
        if reason is None:
            raise CaptureError(
                f"Capture proxy could not open a socket to {hostname}:{port}: {last_error}"
            ) from last_error
        raise UpstreamConnectionError(
            f"Upstream connection to {hostname}:{port} failed: {reason}"
        ) from last_error


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


def _network_failure_reason(exc: OSError) -> str | None:
    """Describe a failure of the network path to the site, or None for local faults.

    Phrases match the availability indicators used to classify check failures.
    """
    if isinstance(exc, TimeoutError) or exc.errno == errno.ETIMEDOUT:
        return "connection timed out"
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused"
    if isinstance(exc, ConnectionResetError | ConnectionAbortedError):
        return "connection reset"
    if exc.errno in _NETWORK_ERRNOS:
        return "host unreachable"
    return None


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


class _HttpExchange:
    """Observe HTTP framing without buffering bodies or changing forwarded bytes.

    Two h11 state machines parse the raw requests/responses. Mirroring their
    events supplies the request method (HEAD, for example) and lets both start
    another keep-alive cycle once that exchange is complete.
    """

    def __init__(self) -> None:
        self.requests = h11.Connection(h11.SERVER, max_incomplete_event_size=_MAX_HEADER_BYTES)
        self.responses = h11.Connection(h11.CLIENT, max_incomplete_event_size=_MAX_HEADER_BYTES)
        self.pending_response = False
        self._closed: set[h11.Connection] = set()

    def request_data(self, data: bytes) -> None:
        self.requests.receive_data(data)
        self._pump()

    def response_data(self, data: bytes) -> None:
        self.responses.receive_data(data)
        self._pump()

    def _pump(self) -> None:
        progress = True
        while progress:
            progress = False
            for source, destination in (
                (self.requests, self.responses),
                (self.responses, self.requests),
            ):
                if source in self._closed:
                    continue
                while True:
                    event = source.next_event()
                    if event is h11.NEED_DATA or event is h11.PAUSED:
                        break
                    if isinstance(event, h11.ConnectionClosed):
                        self._closed.add(source)
                        break
                    if isinstance(event, h11.Request):
                        self.pending_response = True
                    elif source is self.responses and isinstance(event, h11.EndOfMessage):
                        self.pending_response = False
                    # Advance the other parser without joining/copying body data.
                    destination.send_with_data_passthrough(event)
                    progress = True
            if all(
                connection.our_state is h11.DONE and connection.their_state is h11.DONE
                for connection in (self.requests, self.responses)
            ):
                self.requests.start_next_cycle()
                self.responses.start_next_cycle()
                progress = True


async def _tunnel(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
    idle_timeout: float,
    *,
    request_sent: bool,
    on_upstream_failure: Callable[[str], None],
    exchange: _HttpExchange | None = None,
) -> None:
    sent = request_sent
    received = False

    async def to_upstream() -> None:
        nonlocal sent, exchange
        try:
            while chunk := await asyncio.wait_for(
                client_reader.read(_STREAM_CHUNK_BYTES), timeout=idle_timeout
            ):
                # Playwright's request client also uses CONNECT for plain HTTP.
                # TLS starts with a binary record type; an HTTP method starts
                # with an ASCII token. Observe cleartext inside that tunnel too.
                if not sent and exchange is None and 65 <= chunk[0] <= 90:
                    exchange = _HttpExchange()
                if exchange is not None:
                    exchange.request_data(chunk)
                sent = True
                upstream_writer.write(chunk)
                await asyncio.wait_for(upstream_writer.drain(), timeout=idle_timeout)
        except (RuntimeError, ConnectionError, OSError, h11.ProtocolError):
            # OSError covers TimeoutError: an idle client ends this direction.
            pass
        finally:
            with suppress(RuntimeError, ConnectionError, OSError):
                upstream_writer.write_eof()

    async def to_client() -> None:
        nonlocal received
        abnormal_end = False
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        upstream_reader.read(_STREAM_CHUNK_BYTES), timeout=idle_timeout
                    )
                    if exchange is not None:
                        # EOF completes a close-delimited response, but rejects
                        # incomplete Content-Length/chunked messages.
                        exchange.response_data(chunk)
                except (OSError, h11.ProtocolError) as exc:
                    incomplete = (
                        exchange.pending_response
                        if exchange is not None
                        else sent and (not received or not isinstance(exc, TimeoutError))
                    )
                    if incomplete:
                        reason = (
                            _network_failure_reason(exc)
                            if isinstance(exc, OSError)
                            else "invalid or incomplete HTTP response"
                        )
                        if reason is not None:
                            on_upstream_failure(f"response interrupted: {reason}")
                    # An opaque TLS tunnel cannot expose HTTP message boundaries.
                    # Preserve a real reset as a reset instead of manufacturing
                    # a clean EOF; idle keep-alive expiry still closes normally.
                    abnormal_end = incomplete or not isinstance(exc, TimeoutError)
                    break
                if not chunk:
                    if exchange is not None and exchange.pending_response:
                        on_upstream_failure("connection closed before a response")
                        abnormal_end = True
                    break
                received = True
                client_writer.write(chunk)
                await asyncio.wait_for(client_writer.drain(), timeout=idle_timeout)
        except (RuntimeError, ConnectionError, OSError):
            # Backpressure or a closed client is not an upstream site failure.
            abnormal_end = True
        finally:
            if abnormal_end:
                # Best effort RST: some event loops shut down before closing the
                # socket, so the recorded error must also reject successful fetches.
                downstream_socket = client_writer.get_extra_info("socket")
                if downstream_socket is not None:
                    with suppress(RuntimeError, ConnectionError, OSError):
                        downstream_socket.setsockopt(
                            socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                        )
                if client_writer.transport is not None:
                    with suppress(RuntimeError, ConnectionError, OSError):
                        client_writer.transport.abort()
            else:
                with suppress(RuntimeError, ConnectionError, OSError):
                    client_writer.write_eof()

    # A client that half-closes after sending its request still expects the
    # whole response, so the tunnel lives until the upstream side finishes.
    # The request direction is only cancelled once there is nothing left to
    # deliver; idle_timeout keeps a stalled upstream from holding it open.
    upstream_task = asyncio.create_task(to_upstream())
    client_task = asyncio.create_task(to_client())
    try:
        await client_task
    finally:
        upstream_task.cancel()
        await asyncio.gather(upstream_task, client_task, return_exceptions=True)


async def _write_error(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    if writer.is_closing():
        return
    body = f"{status} {reason}\n".encode()
    try:
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
    except (RuntimeError, ConnectionError, OSError):
        pass
