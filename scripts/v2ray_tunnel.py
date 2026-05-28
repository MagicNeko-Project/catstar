#!/usr/bin/env python3
"""
V2Ray Tunnel Configuration Generator.

This script generates client and server V2Ray configurations to establish
secure transport tunnels (supporting Websocket, gRPC, HTTP/2, and raw TCP
with or without TLS) for point-to-point port forwarding.
"""

import argparse
import json
import sys
from typing import Any, Dict, Optional, Set
from urllib.parse import ParseResult, urlparse

# Standard Network and Protocol Constants
DEFAULT_TLS_PORT: int = 443
DEFAULT_HTTP_PORT: int = 80
MIN_VALID_PORT: int = 1
MAX_VALID_PORT: int = 65535

# V2Ray Specific Transport Configurations
DEFAULT_GRPC_SERVICE_NAME: str = "TunnelService"
DEFAULT_PATH: str = "/"

SUPPORTED_TLS_SCHEMES: Set[str] = {"wss", "https", "tls", "grpc", "h2"}
SUPPORTED_WS_SCHEMES: Set[str] = {"ws", "wss"}
SUPPORTED_GRPC_SCHEMES: Set[str] = {"grpc"}
SUPPORTED_H2_SCHEMES: Set[str] = {"h2", "http"}


def validate_port_number(port_value: Any) -> int:
    """
    Validates that the given value represents a valid port number.

    Args:
        port_value: The port string or integer to validate.

    Returns:
        A validated integer representing the port number.

    Raises:
        ValueError: If the port is out of the valid range or invalid.
    """
    try:
        port = int(port_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Port must be a valid integer: '{port_value}'") from error

    if not (MIN_VALID_PORT <= port <= MAX_VALID_PORT):
        raise ValueError(
            f"Port number must be between {MIN_VALID_PORT} and {MAX_VALID_PORT}. Got: {port}"
        )
    return port


def parse_remote_endpoint(remote_url_string: str) -> ParseResult:
    """
    Parses the remote URL endpoint, providing defaults if a scheme is missing.

    Args:
        remote_url_string: The raw remote endpoint input.

    Returns:
        A ParseResult object representing the parsed URL components.
    """
    # Fallback to WebSocket if no protocol scheme is specified
    normalized_url_string = remote_url_string
    if "://" not in normalized_url_string:
        normalized_url_string = f"ws://{normalized_url_string}"

    parsed_url = urlparse(normalized_url_string)

    if not parsed_url.hostname:
        raise ValueError(
            f"Unable to parse hostname from the remote endpoint: '{remote_url_string}'"
        )

    return parsed_url


def determine_tunnel_mode(forced_mode: Optional[str], scheme: str) -> str:
    """
    Determines the tunnel operation mode (client or server).

    Args:
        forced_mode: User-defined override mode ('client' or 'server').
        scheme: The parsed protocol scheme.

    Returns:
        A string representing the active mode: 'client' or 'server'.
    """
    if forced_mode:
        if forced_mode not in {"client", "server"}:
            raise ValueError(f"Invalid tunnel mode: '{forced_mode}'. Must be 'client' or 'server'.")
        return forced_mode

    # Default heuristics: TCP endpoints represent the listening backend (Server mode)
    if scheme == "tcp":
        return "server"

    return "client"


def determine_transport_protocol(scheme: str) -> str:
    """
    Determines the V2Ray transport protocol based on the scheme.

    Args:
        scheme: The parsed protocol scheme.

    Returns:
        The V2Ray transport protocol string name.
    """
    if scheme in SUPPORTED_WS_SCHEMES:
        return "ws"
    if scheme in SUPPORTED_GRPC_SCHEMES:
        return "grpc"
    if scheme in SUPPORTED_H2_SCHEMES:
        return "h2"
    return "tcp"


def generate_stream_settings(
    transport_protocol: str,
    hostname: str,
    path: str,
    tls_enabled: bool,
    tunnel_mode: str,
    sni_override: str,
    certificate_file: str,
    key_file: str,
) -> Dict[str, Any]:
    """
    Generates the V2Ray streamSettings block for the tunnel.

    Args:
        transport_protocol: The transport type ('ws', 'grpc', 'h2', 'tcp').
        hostname: The target host address or name.
        path: The request path/service name if applicable.
        tls_enabled: Whether TLS is enabled for transport encryption.
        tunnel_mode: The active tunnel mode ('client' or 'server').
        sni_override: Server Name Indication for TLS handshakes.
        certificate_file: Path to the TLS certificate file (server mode).
        key_file: Path to the TLS private key file (server mode).

    Returns:
        A dictionary matching V2Ray streamSettings schema.
    """
    stream_settings: Dict[str, Any] = {"network": transport_protocol}

    if transport_protocol == "ws":
        ws_path = path if path else DEFAULT_PATH
        stream_settings["wsSettings"] = {"path": ws_path}

    elif transport_protocol == "grpc":
        service_name = path.strip("/") if path else DEFAULT_GRPC_SERVICE_NAME
        stream_settings["grpcSettings"] = {
            "serviceName": service_name,
            "host": hostname,
        }

    elif transport_protocol == "h2":
        h2_path = path if path else DEFAULT_PATH
        stream_settings["httpSettings"] = {
            "path": h2_path,
            "host": [hostname],
        }

    if tls_enabled:
        stream_settings["security"] = "tls"
        if tunnel_mode == "client":
            stream_settings["tlsSettings"] = {
                "serverName": sni_override,
                "allowInsecure": False,
            }
        else:
            stream_settings["tlsSettings"] = {
                "certificates": [
                    {
                        "certificateFile": certificate_file,
                        "keyFile": key_file,
                    }
                ]
            }

    return stream_settings


def generate_inbound_configuration(
    listen_port: int,
    address: str,
    target_port: int,
    tunnel_mode: str,
    stream_settings: Dict[str, Any],
    tag: Optional[str],
) -> Dict[str, Any]:
    """
    Generates the V2Ray inbound configuration object.

    Args:
        listen_port: Local or public port to receive traffic.
        address: Target host address to route connections to.
        target_port: Target port of the remote service.
        tunnel_mode: Operation mode ('client' or 'server').
        stream_settings: Configured streamSettings block.
        tag: Optional label for routing rules.

    Returns:
        A dictionary representing the inbound configuration.
    """
    inbound: Dict[str, Any] = {
        "port": listen_port,
        "protocol": "dokodemo-door",
        "settings": {
            "address": address,
            "port": target_port,
            "networks": "tcp",
        },
    }

    # Server mode binds the secure transport settings to the incoming connection
    if tunnel_mode == "server":
        inbound["streamSettings"] = stream_settings

    if tag:
        inbound["tag"] = f"{tag}-in"

    return inbound


def generate_outbound_configuration(
    tunnel_mode: str,
    stream_settings: Dict[str, Any],
    tag: Optional[str],
) -> Dict[str, Any]:
    """
    Generates the V2Ray outbound configuration object.

    Args:
        tunnel_mode: Operation mode ('client' or 'server').
        stream_settings: Configured streamSettings block.
        tag: Optional label for routing rules.

    Returns:
        A dictionary representing the outbound configuration.
    """
    outbound: Dict[str, Any] = {
        "protocol": "freedom",
    }

    # Client mode binds the secure transport settings to the outgoing connection
    if tunnel_mode == "client":
        outbound["streamSettings"] = stream_settings

    if tag:
        outbound["tag"] = f"{tag}-out"

    return outbound


def assemble_complete_configuration(
    inbound: Dict[str, Any],
    outbound: Dict[str, Any],
    tag: Optional[str],
) -> Dict[str, Any]:
    """
    Assembles the complete V2Ray configuration object including basic logging
    and routing isolation rules.

    Args:
        inbound: The configured inbound block.
        outbound: The configured outbound block.
        tag: Optional label for isolating traffic.

    Returns:
        A dictionary representing the complete V2Ray configuration.
    """
    config: Dict[str, Any] = {
        "log": {"loglevel": "info"},
        "inbounds": [inbound],
        "outbounds": [outbound],
    }

    if tag:
        config["routing"] = {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": [inbound["tag"]],
                    "outboundTag": outbound["tag"],
                }
            ],
        }

    return config


def main() -> None:
    """
    Executes the command-line parsing and config generation logic.
    """
    parser = argparse.ArgumentParser(
        description="V2Ray Tunnel Configuration Generator (TCP, WS, gRPC, H2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Client Mode: Local Port 1234 -> Forward to Remote WSS Server
  python3 v2ray_tunnel.py --listen 1234 --remote wss://example.com/tunnel

  # Server Mode: Listen WS 443 with TLS -> Forward to Local SSH (22)
  python3 v2ray_tunnel.py --listen 443 --remote tcp://127.0.0.1:22 --tls

  # Isolated Tunnel with Routing Tags
  python3 v2ray_tunnel.py --listen 1234 --remote wss://example.com/tunnel --tag my-tunnel
""",
    )

    parser.add_argument(
        "-l",
        "--listen",
        required=True,
        help="Port to listen on",
    )
    parser.add_argument(
        "-r",
        "--remote",
        required=True,
        help="Remote URL endpoint (e.g., wss://example.com/path, grpc://host, tcp://127.0.0.1:22)",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["client", "server"],
        help="Force specific tunnel mode (client or server). Autodetected if omitted.",
    )
    parser.add_argument(
        "-t",
        "--tag",
        help="Optional routing tag for isolation inside the V2Ray router",
    )

    # TLS controls
    group_tls = parser.add_mutually_exclusive_group()
    group_tls.add_argument(
        "--tls",
        action="store_true",
        help="Force enable TLS encryption",
    )
    group_tls.add_argument(
        "--no-tls",
        action="store_true",
        help="Force disable TLS encryption",
    )

    parser.add_argument(
        "--sni",
        help="Override TLS Server Name Indication (SNI) handshake",
    )

    parser.add_argument(
        "--cert-file",
        default="/etc/ssl/example.com/full.pem",
        help="Path to the TLS certificate file for server mode",
    )
    parser.add_argument(
        "--key-file",
        default="/etc/ssl/example.com/key.pem",
        help="Path to the TLS private key file for server mode",
    )

    # Output filtration
    group_output = parser.add_mutually_exclusive_group()
    group_output.add_argument(
        "--inbound",
        action="store_true",
        help="Output only the inbound block",
    )
    group_output.add_argument(
        "--outbound",
        action="store_true",
        help="Output only the outbound block",
    )

    args = parser.parse_args()

    try:
        # Input validation
        listen_port = validate_port_number(args.listen)
        parsed_remote = parse_remote_endpoint(args.remote)

        # Mode heuristics and overrides
        tunnel_mode = determine_tunnel_mode(args.mode, parsed_remote.scheme)

        # TLS configuration
        tls_enabled = parsed_remote.scheme in SUPPORTED_TLS_SCHEMES
        if args.tls:
            tls_enabled = True
        elif args.no_tls:
            tls_enabled = False

        # Resolve transport details
        transport_protocol = determine_transport_protocol(parsed_remote.scheme)
        hostname = parsed_remote.hostname
        assert hostname is not None  # Guaranteed by parse_remote_endpoint validation

        # Resolve remote port
        if parsed_remote.port is not None:
            remote_port = validate_port_number(parsed_remote.port)
        else:
            remote_port = DEFAULT_TLS_PORT if tls_enabled else DEFAULT_HTTP_PORT

        # Resolve path or default
        path = parsed_remote.path if parsed_remote.path else ""

        # Resolve TLS SNI
        sni_override = args.sni if args.sni else hostname

        # Construct the settings
        stream_settings = generate_stream_settings(
            transport_protocol=transport_protocol,
            hostname=hostname,
            path=path,
            tls_enabled=tls_enabled,
            tunnel_mode=tunnel_mode,
            sni_override=sni_override,
            certificate_file=args.cert_file,
            key_file=args.key_file,
        )

        # Generate inbound & outbound configurations
        inbound_config = generate_inbound_configuration(
            listen_port=listen_port,
            address=hostname,
            target_port=remote_port,
            tunnel_mode=tunnel_mode,
            stream_settings=stream_settings,
            tag=args.tag,
        )

        outbound_config = generate_outbound_configuration(
            tunnel_mode=tunnel_mode,
            stream_settings=stream_settings,
            tag=args.tag,
        )

        # Output generation based on filters
        if args.inbound:
            print(json.dumps(inbound_config, indent=2))
        elif args.outbound:
            print(json.dumps(outbound_config, indent=2))
        else:
            complete_config = assemble_complete_configuration(
                inbound=inbound_config,
                outbound=outbound_config,
                tag=args.tag,
            )
            print(json.dumps(complete_config, indent=2))

    except ValueError as error:
        print(f"Configuration Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
