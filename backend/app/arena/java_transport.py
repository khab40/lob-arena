"""One credential-free transport to the configured Java owner, without redirects."""

import http.client
import math
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_REQUEST = 8 * 1024**2  # Existing Java kernel request contract.


@dataclass(frozen=True)
class JavaResponse:
    status: int
    body: bytes
    content_type: str


class JavaStream:
    def __init__(self, connection, response, sock, method, content_type, headers):
        self.connection, self.response, self.sock = connection, response, sock
        self.method, self.content_type, self.status = method, content_type, response.status
        self.closed = False
        self.headers = headers

    def chunks(self):
        count = 0
        try:
            while not self.closed:
                chunk = self.response.read1(65536)
                if not chunk:
                    break
                count += len(chunk)
                yield chunk
            size = self.response.getheader("Content-Length")
            if self.method != "HEAD" and self.status not in (204, 304) and size is not None and count != int(size):
                raise ValueError("Java response truncated")
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise RuntimeError("Java service unavailable") from exc
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Interrupt an owned read when downstream cancellation races its thread.
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.response.close()
        finally:
            self.connection.close()


class JavaTransport:
    def __init__(self, base_url: str, timeout: float):
        origin = urlsplit(base_url)
        if (origin.scheme not in ("http", "https") or not origin.hostname or origin.username
                or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("Invalid Java transport configuration")
        self.origin, self.timeout = origin, timeout

    @property
    def websocket_url(self):
        scheme = "wss" if self.origin.scheme == "https" else "ws"
        return f"{scheme}://{self.origin.netloc}/ws/arena"

    def open(self, method, path, body=None, content_type="application/json", *, timeout=None):
        limit = self.timeout if timeout is None else timeout
        if (not path.startswith("/") or path.startswith("//") or "#" in path
                or len(body or b"") > MAX_REQUEST or len(content_type) > 256
                or "\r" in content_type or "\n" in content_type
                or not math.isfinite(limit) or limit <= 0):
            raise ValueError("Invalid Java request")
        connection_type = http.client.HTTPSConnection if self.origin.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(self.origin.hostname, self.origin.port, timeout=limit)
        response = None
        try:
            connection.request(method, path, body=body,
                               headers={"Accept": "*/*", "Content-Type": content_type})
            sock = connection.sock  # HTTPResponse may own it on Connection: close.
            response = connection.getresponse()
            # Follow no redirects and expose no upstream location/cookie/auth headers.
            if 300 <= response.status < 400:
                raise ValueError("Java redirect refused")
            size = response.getheader("Content-Length")
            if size is not None and int(size) < 0:
                raise ValueError("Invalid Java response length")
            content_type = response.getheader("Content-Type", "application/octet-stream")
            if len(content_type) > 256 or "\r" in content_type or "\n" in content_type:
                raise ValueError("Invalid Java response header")
            proof = {}
            for name in ("X-Kernel-Authority", "X-Kernel-Decision"):
                value = response.getheader(name)
                if value is not None:
                    if value != "java":
                        raise ValueError("Invalid Java authority proof")
                    proof[name] = value
            return JavaStream(connection, response, sock, method, content_type, proof)
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if response is not None:
                response.close()
            connection.close()
            raise RuntimeError("Java service unavailable") from exc

    def request(self, method, path, body=None, content_type="application/json"):
        # Retained typed JSON aggregation and configured socket timeout remain.
        stream = self.open(method, path, body, content_type)
        return JavaResponse(stream.status, b"".join(stream.chunks()), stream.content_type)
