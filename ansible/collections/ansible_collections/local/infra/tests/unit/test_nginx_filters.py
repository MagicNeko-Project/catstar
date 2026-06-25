"""Unit tests for the Nginx Ansible filter plugins."""

import os
import sys
from typing import Any, Dict, List

# Ensure the parent collection directories are in the Python path
# so that the plugins package can be imported correctly.
COLLECTION_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, COLLECTION_ROOT)

from plugins.filter import nginx  # noqa: E402 # type: ignore


def test_force_list_behavior() -> None:
    """Verify that force_list correctly converts inputs to list format."""
    assert nginx.force_list("test") == ["test"]
    assert nginx.force_list(["test"]) == ["test"]
    assert nginx.force_list(None) == [None]


def test_parse_listen_ports() -> None:
    """Verify that listen port strings are correctly parsed into ListenPort objects."""
    ports: List[nginx.ListenPort] = list(nginx.parse_listen_ports("80 443"))

    assert len(ports) == 4

    # Port 80 IPv4
    assert ports[0].port == 80
    assert not ports[0].ssl
    assert not ports[0].v6

    # Port 80 IPv6
    assert ports[1].port == 80
    assert not ports[1].ssl
    assert ports[1].v6

    # Port 443 IPv4
    assert ports[2].port == 443
    assert ports[2].ssl
    assert not ports[2].v6

    # Port 443 IPv6
    assert ports[3].port == 443
    assert ports[3].ssl
    assert ports[3].v6


def test_nginx_location_block_filter() -> None:
    """Verify that the nginx_location_block filter correctly builds location blocks."""
    filter_module = nginx.FilterModule()
    configs: List[Dict[str, Any]] = [{"location": "/app", "proxy": "http://backend"}]

    result: List[nginx.NginxLocationBlock] = filter_module.nginx_location_block(configs)

    assert len(result) == 1
    location_block = result[0]
    assert location_block.location == "/app"
    assert location_block.proxy == "http://backend"
    assert location_block.options == {}


def test_nginx_server_block_filter() -> None:
    """Verify that the nginx_server_block filter correctly instantiates server blocks."""
    filter_module = nginx.FilterModule()
    configs: List[Dict[str, Any]] = [
        {
            "server_name": "example.com",
            "locations": [{"location": "/", "proxy": "http://frontend"}],
        }
    ]

    result: List[nginx.NginxServerBlock] = filter_module.nginx_server_block(
        configs, "default_name"
    )

    assert len(result) == 1
    server_block = result[0]
    assert server_block.server_name == "example.com"
    assert server_block.ssl_host == "example.com"
    assert len(server_block.listen) == 2
    assert server_block.listen[0].port == 443
    assert server_block.listen[0].ssl
    assert not server_block.listen[0].v6
    assert server_block.listen[1].port == 443
    assert server_block.listen[1].ssl
    assert server_block.listen[1].v6
    assert server_block.locations == [{"location": "/", "proxy": "http://frontend"}]


def test_gather_ssl_hosts_filter() -> None:
    """Verify that gather_ssl_hosts extracts correct domains for SSL certifications."""
    filter_module = nginx.FilterModule()
    sites: Dict[str, Dict[str, Any]] = {
        "default": {},
        "c5.example.com": {},
        "c6.example.com": {"server_name": "c6.example.com"},
    }

    ssl_hosts: List[str] = filter_module.gather_ssl_hosts(sites)

    assert ssl_hosts == ["default", "example.com", "example.com"]


def test_nginx_options_formatting() -> None:
    """Verify that nginx_options returns correctly formatted Nginx directives."""
    filter_module = nginx.FilterModule()

    options: Dict[str, Any] = {
        "gzip": True,
        "client_max_body_size": "50m",
        "if": "($host = example.com)",
    }

    formatted: List[str] = filter_module.nginx_options(options)

    assert "gzip on;" in formatted
    assert "client_max_body_size 50m;" in formatted
    assert "if ($host = example.com)" in formatted
