#!/usr/bin/env python3
"""
V2Ray Tunnel Configuration Generator.

This script generates V2Ray configurations to establish secure transport tunnels
by bridging a local Inbound listener (configured via --listen) to a remote Outbound
client connection (configured via --remote). It supports WebSocket, gRPC, HTTP/2,
and raw TCP transport protocols with optional TLS encryption on either end.
"""

import argparse
import json
import random
import subprocess
import sys
import time
from typing import Any, Dict, NamedTuple, Optional, Set
from urllib.parse import ParseResult, urlparse

# Standard Network and Protocol Constants
DEFAULT_TLS_PORT: int = 443
DEFAULT_HTTP_PORT: int = 80
MIN_VALID_PORT: int = 1
MAX_VALID_PORT: int = 65535

# Safe Random Port Ranges
MIN_RANDOM_PORT: int = 10000
MAX_RANDOM_PORT: int = 65535

# V2Ray Specific Transport Configurations
DEFAULT_GRPC_SERVICE_NAME: str = "TunnelService"
DEFAULT_PATH: str = "/"

SUPPORTED_TLS_SCHEMES: Set[str] = {"wss", "https", "tls", "grpc", "h2"}
SUPPORTED_WS_SCHEMES: Set[str] = {"ws", "wss"}
SUPPORTED_GRPC_SCHEMES: Set[str] = {"grpc"}
SUPPORTED_H2_SCHEMES: Set[str] = {"h2"}

# Proxy Configuration Constants
DEFAULT_SOCKS_PROXY_PORT: int = 1080
DEFAULT_HTTP_PROXY_PORT: int = 8080

SOCKS_PROTOCOL_NAME: str = "socks"
HTTP_PROTOCOL_NAME: str = "http"

SUPPORTED_SOCKS_SCHEMES: Set[str] = {"socks", "socks4", "socks4a", "socks5", "socks5h"}
SUPPORTED_HTTP_SCHEMES: Set[str] = {"http", "https"}


class EndpointConfiguration(NamedTuple):
    """
    Immutable representation of an inbound or outbound tunnel endpoint.
    """
    transport_protocol: str
    address: Optional[str]
    port: int
    path: str
    tls_enabled: bool


class ProxyConfiguration(NamedTuple):
    """
    Immutable representation of an upstream proxy configuration.
    """
    protocol: str  # Must be SOCKS_PROTOCOL_NAME or HTTP_PROTOCOL_NAME
    address: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None


def generate_random_port() -> int:
    """
    Generates a random port number within a safe, unassigned range (10000 to 65535).

    Returns:
        A reasonably chosen port number.
    """
    return random.randint(MIN_RANDOM_PORT, MAX_RANDOM_PORT)


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


def parse_endpoint(url_string: str, is_inbound: bool) -> EndpointConfiguration:
    """
    Parses a port number or URL string into a strongly-typed EndpointConfiguration.

    Args:
        url_string: The port string (e.g. '1234') or URL (e.g. 'wss://example.com:443/path').
        is_inbound: True if parsing the inbound listener, False for the outbound client.

    Returns:
        An EndpointConfiguration NamedTuple.
    """
    # Handle plain port number
    if url_string.isdigit():
        port = validate_port_number(url_string)
        return EndpointConfiguration(
            transport_protocol="tcp",
            address=None,
            port=port,
            path="",
            tls_enabled=False,
        )

    # Handle URL
    normalized_string = url_string
    if "://" not in normalized_string:
        normalized_string = f"tcp://{normalized_string}"

    parsed_url = urlparse(normalized_string)

    scheme = parsed_url.scheme.lower()
    if scheme in SUPPORTED_WS_SCHEMES:
        transport_protocol = "ws"
    elif scheme in SUPPORTED_GRPC_SCHEMES:
        transport_protocol = "grpc"
    elif scheme in SUPPORTED_H2_SCHEMES:
        transport_protocol = "h2"
    else:
        transport_protocol = "tcp"

    tls_enabled = scheme in SUPPORTED_TLS_SCHEMES

    # Resolve address (None if not specified)
    address = parsed_url.hostname if parsed_url.hostname else None

    # Validate that outbound (remote) destination has a host
    if not is_inbound and not address:
        raise ValueError(
            f"Remote destination must specify a target address or hostname. Got: '{url_string}'"
        )

    # Resolve port
    if parsed_url.port is not None:
        port = validate_port_number(parsed_url.port)
    else:
        port = DEFAULT_TLS_PORT if tls_enabled else DEFAULT_HTTP_PORT

    # Resolve path
    path = parsed_url.path if parsed_url.path else ""

    return EndpointConfiguration(
        transport_protocol=transport_protocol,
        address=address,
        port=port,
        path=path,
        tls_enabled=tls_enabled,
    )


def parse_proxy_endpoint_url(proxy_url_string: str) -> ProxyConfiguration:
    """
    Parses a proxy URL string into an immutable ProxyConfiguration NamedTuple.

    Supported schemes: socks, socks4, socks4a, socks5, socks5h, http, https.

    Args:
        proxy_url_string: The raw proxy URL string (e.g., socks5://127.0.0.1:1080).

    Returns:
        A ProxyConfiguration NamedTuple containing the parsed details.

    Raises:
        ValueError: If the URL is invalid, lacks a scheme/host, or has an unsupported scheme.
    """
    parsed_url = urlparse(proxy_url_string)
    if not parsed_url.scheme:
        raise ValueError(
            f"Proxy URL must include a scheme (e.g., socks5:// or http://). Got: '{proxy_url_string}'"
        )

    scheme = parsed_url.scheme.lower()
    if scheme in SUPPORTED_SOCKS_SCHEMES:
        protocol = SOCKS_PROTOCOL_NAME
    elif scheme in SUPPORTED_HTTP_SCHEMES:
        protocol = HTTP_PROTOCOL_NAME
    else:
        supported_schemes_list = sorted(list(SUPPORTED_SOCKS_SCHEMES | SUPPORTED_HTTP_SCHEMES))
        raise ValueError(
            f"Unsupported proxy scheme: '{scheme}'. Supported schemes are: {', '.join(supported_schemes_list)}"
        )

    if not parsed_url.hostname:
        raise ValueError(
            f"Unable to parse hostname from the proxy URL: '{proxy_url_string}'"
        )

    if parsed_url.port is not None:
        port = validate_port_number(parsed_url.port)
    else:
        port = DEFAULT_SOCKS_PROXY_PORT if protocol == SOCKS_PROTOCOL_NAME else DEFAULT_HTTP_PROXY_PORT

    return ProxyConfiguration(
        protocol=protocol,
        address=parsed_url.hostname,
        port=port,
        username=parsed_url.username,
        password=parsed_url.password,
    )


def generate_endpoint_stream_settings(
    endpoint: EndpointConfiguration,
    is_inbound: bool,
    sni_override: str,
    certificate_file: str,
    key_file: str,
) -> Optional[Dict[str, Any]]:
    """
    Generates the V2Ray streamSettings block for an inbound or outbound endpoint.

    Args:
        endpoint: The EndpointConfiguration.
        is_inbound: True for inbound listener, False for outbound client.
        sni_override: Server Name Indication for outbound TLS handshakes.
        certificate_file: Path to the TLS certificate file (inbound).
        key_file: Path to the TLS private key file (inbound).

    Returns:
        A dictionary matching V2Ray streamSettings schema, or None if plain TCP.
    """
    if endpoint.transport_protocol == "tcp" and not endpoint.tls_enabled:
        return None

    stream_settings: Dict[str, Any] = {"network": endpoint.transport_protocol}

    if endpoint.transport_protocol == "ws":
        ws_path = endpoint.path if endpoint.path else DEFAULT_PATH
        stream_settings["wsSettings"] = {"path": ws_path}

    elif endpoint.transport_protocol == "grpc":
        service_name = endpoint.path.strip("/") if endpoint.path else DEFAULT_GRPC_SERVICE_NAME
        stream_settings["grpcSettings"] = {
            "serviceName": service_name,
            "host": endpoint.address,
        }

    elif endpoint.transport_protocol == "h2":
        h2_path = endpoint.path if endpoint.path else DEFAULT_PATH
        stream_settings["httpSettings"] = {
            "path": h2_path,
            "host": [endpoint.address],
        }

    if endpoint.tls_enabled:
        stream_settings["security"] = "tls"
        if not is_inbound:
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
    listen_address: Optional[str],
    address: str,
    target_port: int,
    stream_settings: Optional[Dict[str, Any]],
    tag: Optional[str],
) -> Dict[str, Any]:
    """
    Generates the V2Ray inbound configuration object.
    """
    inbound: Dict[str, Any] = {
        "port": listen_port,
        "protocol": "dokodemo-door",
        "settings": {
            "address": address,
            "port": target_port,
            "network": "tcp",
        },
    }

    if listen_address:
        inbound["listen"] = listen_address

    if stream_settings:
        inbound["streamSettings"] = stream_settings

    if tag:
        inbound["tag"] = f"{tag}-in"

    return inbound


def generate_outbound_configuration(
    stream_settings: Optional[Dict[str, Any]],
    tag: Optional[str],
    proxy_tag: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates the V2Ray outbound configuration object.
    """
    outbound: Dict[str, Any] = {
        "protocol": "freedom",
    }

    if stream_settings:
        outbound["streamSettings"] = stream_settings

    if tag:
        outbound["tag"] = f"{tag}-out"

    if proxy_tag:
        outbound["proxySettings"] = {
            "tag": proxy_tag,
        }

    return outbound


def generate_proxy_outbound_configuration(
    proxy_config: ProxyConfiguration,
    proxy_tag: str,
) -> Dict[str, Any]:
    """
    Generates the V2Ray outbound configuration object for an upstream proxy server.
    """
    outbound: Dict[str, Any] = {
        "protocol": proxy_config.protocol,
        "tag": proxy_tag,
    }

    server_entry: Dict[str, Any] = {
        "address": proxy_config.address,
        "port": proxy_config.port,
    }

    if proxy_config.protocol == SOCKS_PROTOCOL_NAME:
        users_list = []
        if proxy_config.username and proxy_config.password:
            users_list.append({
                "user": proxy_config.username,
                "pass": proxy_config.password,
                "level": 0,
            })
        server_entry["users"] = users_list
        outbound["settings"] = {
            "servers": [server_entry]
        }

    elif proxy_config.protocol == HTTP_PROTOCOL_NAME:
        user_list = []
        if proxy_config.username and proxy_config.password:
            user_list.append({
                "user": proxy_config.username,
                "pass": proxy_config.password,
            })
        server_entry["users"] = user_list
        outbound["settings"] = {
            "servers": [server_entry]
        }

    return outbound


def assemble_complete_configuration(
    inbound: Dict[str, Any],
    outbound: Dict[str, Any],
    tag: Optional[str],
    proxy_outbound: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assembles the complete V2Ray configuration object including basic logging,
    routing isolation rules, and optional upstream proxy outbound.
    """
    outbounds = [outbound]
    if proxy_outbound:
        outbounds.append(proxy_outbound)

    config: Dict[str, Any] = {
        "log": {"loglevel": "info"},
        "inbounds": [inbound],
        "outbounds": outbounds,
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


def generate_colorized_examples_epilog(colorize: bool) -> str:
    """
    Generates a colorized help epilog containing usage examples.
    """
    ansi_bold = "\033[1m" if colorize else ""
    ansi_cyan = "\033[36m" if colorize else ""
    ansi_yellow = "\033[33m" if colorize else ""
    ansi_reset = "\033[0m" if colorize else ""

    lines = [
        "Examples:",
        f"  {ansi_cyan}# Client Forwarding: Local Port 1234 -> Forward to Remote Secure WebSocket Server{ansi_reset}",
        f"  {ansi_bold}python3 v2ray_tunnel.py{ansi_reset} {ansi_yellow}--listen{ansi_reset} 1234 {ansi_yellow}--remote{ansi_reset} wss://example.com/tunnel",
        "",
        f"  {ansi_cyan}# Client Forwarding through a SOCKS5 Proxy:{ansi_reset}",
        f"  {ansi_bold}python3 v2ray_tunnel.py{ansi_reset} {ansi_yellow}--listen{ansi_reset} 1234 {ansi_yellow}--remote{ansi_reset} wss://example.com/tunnel {ansi_yellow}--proxy{ansi_reset} socks5://127.0.0.1:1080",
        "",
        f"  {ansi_cyan}# Server Decryption: Public Secure WebSocket listener -> Forward decrypt to local SSH (22){ansi_reset}",
        f"  {ansi_bold}python3 v2ray_tunnel.py{ansi_reset} {ansi_yellow}--listen{ansi_reset} wss://:443 {ansi_yellow}--remote{ansi_reset} tcp://127.0.0.1:22",
        "",
        f"  {ansi_cyan}# Plain TCP Proxy with Dynamic Port Allocation and Auto-SSH connection:{ansi_reset}",
        f"  {ansi_bold}python3 v2ray_tunnel.py{ansi_reset} {ansi_yellow}--remote{ansi_reset} tcp://c5-ts.maomihz.com:22 {ansi_yellow}--ssh{ansi_reset} myuser",
    ]
    return "\n".join(lines)


def main() -> None:
    """
    Executes the command-line parsing and config generation logic.
    """
    colorize = sys.stdout.isatty()
    epilog_text = generate_colorized_examples_epilog(colorize)

    parser = argparse.ArgumentParser(
        description="V2Ray Tunnel Configuration Generator (TCP, WS, gRPC, H2 Proxy)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog_text,
    )

    parser.add_argument(
        "-l",
        "--listen",
        help="Listening port or URL (e.g. 1234, ws://:1234, wss://127.0.0.1:1234). If not specified, a random port is allocated.",
    )
    parser.add_argument(
        "-r",
        "--remote",
        required=True,
        help="Remote destination URL (e.g. wss://example.com/path, grpc://host, tcp://127.0.0.1:22)",
    )
    parser.add_argument(
        "-t",
        "--tag",
        help="Optional routing tag for isolation inside the V2Ray router",
    )
    parser.add_argument(
        "-p",
        "--proxy",
        help="Upstream proxy URL (e.g. socks5://127.0.0.1:1080, http://user:pass@proxy.com:8080) to route the outbound connection through",
    )
    parser.add_argument(
        "--sni",
        help="Override TLS Server Name Indication (SNI) handshake for outbound TLS",
    )
    parser.add_argument(
        "--cert-file",
        help="Path to the TLS certificate file for secure inbound listeners",
    )
    parser.add_argument(
        "--key-file",
        help="Path to the TLS private key file for secure inbound listeners",
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

    parser.add_argument(
        "--run",
        action="store_true",
        help="Start the V2Ray binary directly with the generated configuration",
    )
    parser.add_argument(
        "--ssh",
        nargs="?",
        const="",
        help="Start V2Ray and automatically launch an SSH session connecting to the local tunneled port. Optionally specify the SSH username (e.g. --ssh myuser). Only supported if the local listening port is plain TCP.",
    )

    args = parser.parse_args()

    try:
        # Parse remote (outbound) endpoint details
        outbound_endpoint = parse_endpoint(args.remote, is_inbound=False)

        # Parse local (inbound) endpoint details
        if args.listen:
            inbound_endpoint = parse_endpoint(args.listen, is_inbound=True)
        else:
            # Generate a random local port
            random_port = generate_random_port()
            inbound_endpoint = EndpointConfiguration(
                transport_protocol="tcp",
                address=None,
                port=random_port,
                path="",
                tls_enabled=False,
            )
            ansi_cyan = "\033[36m" if colorize else ""
            ansi_reset = "\033[0m" if colorize else ""
            print(
                f"{ansi_cyan}# Dynamically allocated free listening port: {random_port}{ansi_reset}",
                file=sys.stderr,
            )

        # Validate SSH mode constraints (SSH only works with plain TCP listeners)
        if args.ssh is not None:
            if inbound_endpoint.tls_enabled or inbound_endpoint.transport_protocol != "tcp":
                raise ValueError(
                    "The --ssh option cannot be used when the local listening port expects secure decorated traffic (TLS/WS/gRPC/H2)."
                )


        # Resolve proxy if specified
        proxy_tag = None
        proxy_outbound_config = None
        if args.proxy:
            proxy_config = parse_proxy_endpoint_url(args.proxy)
            proxy_tag = f"{args.tag}-proxy-out" if args.tag else "proxy-out"
            proxy_outbound_config = generate_proxy_outbound_configuration(
                proxy_config=proxy_config,
                proxy_tag=proxy_tag,
            )

        # Generate stream settings for both ends
        inbound_stream_settings = generate_endpoint_stream_settings(
            endpoint=inbound_endpoint,
            is_inbound=True,
            sni_override="",
            certificate_file=args.cert_file,
            key_file=args.key_file,
        )

        sni_override = args.sni if args.sni else outbound_endpoint.address
        outbound_stream_settings = generate_endpoint_stream_settings(
            endpoint=outbound_endpoint,
            is_inbound=False,
            sni_override=sni_override,
            certificate_file="",
            key_file="",
        )

        # Generate configurations
        inbound_config = generate_inbound_configuration(
            listen_port=inbound_endpoint.port,
            listen_address=inbound_endpoint.address,
            address=outbound_endpoint.address,
            target_port=outbound_endpoint.port,
            stream_settings=inbound_stream_settings,
            tag=args.tag,
        )

        outbound_config = generate_outbound_configuration(
            stream_settings=outbound_stream_settings,
            tag=args.tag,
            proxy_tag=proxy_tag,
        )

        # Assemble the complete configuration internally
        complete_config = assemble_complete_configuration(
            inbound=inbound_config,
            outbound=outbound_config,
            tag=args.tag,
            proxy_outbound=proxy_outbound_config,
        )
        config_json_string = json.dumps(complete_config, indent=2)

        # Output generation based on filters
        if args.inbound:
            print(json.dumps(inbound_config, indent=2))
        elif args.outbound:
            if proxy_outbound_config:
                print(json.dumps([outbound_config, proxy_outbound_config], indent=2))
            else:
                print(json.dumps([outbound_config], indent=2))
        else:
            print(config_json_string)

        # Execution logic
        if args.ssh is not None:
            try:
                # Launch V2Ray in the background
                v2ray_process = subprocess.Popen(
                    ["v2ray", "run", "-format", "json"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                v2ray_process.stdin.write(config_json_string.encode("utf-8"))
                v2ray_process.stdin.close()

                # Pause to let V2Ray bind to the port
                time.sleep(0.2)

                # Verify that the V2Ray process is still running
                if v2ray_process.poll() is not None:
                    print("Error: V2Ray process failed to start.", file=sys.stderr)
                    sys.exit(1)

                # Build the SSH command
                ssh_command = ["ssh", "-p", str(inbound_endpoint.port)]
                if args.ssh:  # Username is specified
                    ssh_command.append(f"{args.ssh}@127.0.0.1")
                else:
                    ssh_command.append("127.0.0.1")

                ansi_cyan = "\033[36m" if colorize else ""
                ansi_reset = "\033[0m" if colorize else ""
                print(
                    f"{ansi_cyan}# Launching SSH session: {' '.join(ssh_command)}{ansi_reset}",
                    file=sys.stderr,
                )
                
                subprocess.run(ssh_command, check=True)

            except FileNotFoundError:
                print(
                    "Error: 'v2ray' or 'ssh' binary not found in PATH.",
                    file=sys.stderr,
                )
                sys.exit(1)
            except KeyboardInterrupt:
                pass
            finally:
                # Always clean up the background process cleanly
                print("\nStopping V2Ray tunnel...", file=sys.stderr)
                v2ray_process.terminate()
                v2ray_process.wait()

        elif args.run:
            try:
                subprocess.run(
                    ["v2ray", "run", "-format", "json"],
                    input=config_json_string.encode("utf-8"),
                    check=True,
                )
            except FileNotFoundError:
                print(
                    "Error: 'v2ray' binary not found in PATH. Please ensure V2Ray is installed.",
                    file=sys.stderr,
                )
                sys.exit(1)
            except KeyboardInterrupt:
                print("\nStopping V2Ray tunnel...", file=sys.stderr)
                sys.exit(0)

    except ValueError as error:
        print(f"Configuration Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
