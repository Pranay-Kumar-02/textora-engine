"""
SSRF (Server-Side Request Forgery) protection and URL validation for Textora Engine.
Enforces per-hop IP validation against private CIDRs, loopbacks, and cloud metadata targets.
"""

import ipaddress
import logging
import socket
from typing import List, Optional, Set
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger("textora_engine.security.ssrf")


class SecurityError(Exception):
    """Raised when an operation violates platform security guardrails."""
    pass


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Intercepts and validates every redirect target against SSRF before following."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        URLValidator.validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class URLValidator:
    """Validates external URLs against SSRF and network exfiltration attacks."""

    ALLOWED_SCHEMES: Set[str] = {"http", "https"}

    # Prohibited sensitive/internal ports
    PROHIBITED_PORTS: Set[int] = {
        21, 22, 23, 25, 53, 69, 110, 111, 135, 137, 138, 139, 143, 389, 445,
        636, 1433, 1521, 2049, 2375, 2376, 3306, 3389, 5432, 5900, 6379,
        9200, 11211, 27017,
    }

    # Prohibited IP networks (RFC 1918, loopbacks, link-local, cloud metadata)
    PROHIBITED_NETWORKS = [
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),   # Link-local & cloud metadata (169.254.169.254)
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("224.0.0.0/4"),     # Multicast
        ipaddress.ip_network("240.0.0.0/4"),     # Reserved
        # IPv6
        ipaddress.ip_network("::1/128"),         # IPv6 loopback
        ipaddress.ip_network("fc00::/7"),        # Unique local address
        ipaddress.ip_network("fe80::/10"),       # Link-local unicast
    ]

    @classmethod
    def is_ip_prohibited(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Return True if IP is within any prohibited network."""
        for net in cls.PROHIBITED_NETWORKS:
            if ip in net:
                return True
        return False

    @classmethod
    def validate_url(cls, url: str, allow_file_scheme: bool = False) -> str:
        """
        Validate URL syntax, scheme, credentials, ports, and resolve host IP.
        Raises SecurityError if URL is malicious or targets internal network.
        """
        if not url or not isinstance(url, str):
            raise SecurityError("URL cannot be empty")

        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()

        allowed = cls.ALLOWED_SCHEMES | ({"file"} if allow_file_scheme else set())
        if scheme not in allowed:
            raise SecurityError(f"Prohibited URL scheme '{scheme}'. Allowed: {', '.join(sorted(allowed))}")

        if scheme == "file":
            return url.strip()

        # Check for embedded credentials
        if parsed.username or parsed.password:
            raise SecurityError("URLs with embedded user credentials are prohibited")

        hostname = parsed.hostname
        if not hostname:
            raise SecurityError(f"URL missing valid hostname: '{url}'")

        # Disallow literal localhost or obvious local names
        if hostname.lower() in ("localhost", "localhost.localdomain", "127.0.0.1", "::1"):
            raise SecurityError(f"Targeting localhost is prohibited: '{hostname}'")

        # Port validation
        port = parsed.port
        if port and port in cls.PROHIBITED_PORTS:
            raise SecurityError(f"Targeting port {port} is prohibited for security reasons")

        # Resolve hostname to check target IP addresses
        try:
            target_port = port or (443 if scheme == "https" else 80)
            addr_info = socket.getaddrinfo(hostname, target_port)
        except socket.gaierror as e:
            raise SecurityError(f"Could not resolve host '{hostname}': {e}")

        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if cls.is_ip_prohibited(ip_obj):
                    raise SecurityError(
                        f"SSRF blocked: Host '{hostname}' resolved to prohibited address '{ip_str}'"
                    )
            except ValueError:
                continue

        return url.strip()

    @classmethod
    def build_safe_opener(cls) -> urllib.request.OpenerDirector:
        """Construct a urllib opener that validates all redirect hops against SSRF."""
        return urllib.request.build_opener(SafeRedirectHandler())
