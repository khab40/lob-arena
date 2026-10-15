"""Single bounded Google certificate read for the official verifier child."""

import json
import sys
from types import SimpleNamespace
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from google.oauth2.id_token import verify_oauth2_token

CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class CertificateRequest:
    def __init__(self):
        self.used = False

    def __call__(self, url, method="GET", **_kwargs):
        if self.used or url != CERTS_URL or method != "GET":
            raise ValueError("Unexpected certificate request")
        self.used = True
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(Request(url, method="GET"), timeout=10) as response:
            data = response.read(1024 * 1024 + 1)
            if response.status != 200 or len(data) > 1024 * 1024:
                raise ValueError("Invalid certificate response")
        certs = json.loads(data)
        # The library's JWK branch performs an additional unbounded fetch.
        if (not isinstance(certs, dict) or not certs or "keys" in certs
                or not all(isinstance(k, str) and isinstance(v, str)
                           and v.startswith("-----BEGIN CERTIFICATE-----") for k, v in certs.items())):
            raise ValueError("Invalid certificate response")
        return SimpleNamespace(status=200, data=data)


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read(16385))
        credential, client_id = payload["credential"], payload["client_id"]
        if not isinstance(credential, str) or not 1 <= len(credential) <= 8192:
            return 1
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 512:
            return 1
        claims = verify_oauth2_token(credential, CertificateRequest(), audience=client_id)
        fields = ("sub", "email", "name", "iss", "aud", "exp", "email_verified", "nonce")
        result = {key: claims.get(key) for key in fields}
        output = json.dumps(result, separators=(",", ":"))
        if len(output.encode()) > 8192:
            return 1
        sys.stdout.write(output)
        return 0
    except Exception:
        # No credential, response body, private paths or exception descriptions.
        return 1


if __name__ == "__main__":
    sys.exit(main())
