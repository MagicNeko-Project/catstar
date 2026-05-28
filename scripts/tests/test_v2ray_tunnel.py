#!/usr/bin/env python3
"""
Unit tests for the V2Ray Tunnel Configuration Generator.

This test suite verifies url parsing, transport logic, mode resolution,
streamSettings creation, and inbound/outbound JSON generation under various
flag and option combinations.
"""

import unittest
from typing import Any, Dict
from urllib.parse import ParseResult

# Import functions to test directly from scripts.v2ray_tunnel
from scripts.v2ray_tunnel import (
    assemble_complete_configuration,
    determine_transport_protocol,
    determine_tunnel_mode,
    generate_inbound_configuration,
    generate_outbound_configuration,
    generate_stream_settings,
    parse_remote_endpoint,
    validate_port_number,
)


class TestV2RayTunnelGenerator(unittest.TestCase):
    """
    Exhaustive test suite validating all execution logic pathways and argument
    combinations in the V2Ray Tunnel Configuration Generator.
    """

    def test_validate_port_number_success(self) -> None:
        """Verifies valid port conversion and range checking."""
        self.assertEqual(validate_port_number("80"), 80)
        self.assertEqual(validate_port_number(443), 443)
        self.assertEqual(validate_port_number("1"), 1)
        self.assertEqual(validate_port_number("65535"), 65535)

    def test_validate_port_number_failure(self) -> None:
        """Verifies invalid ports raise ValueErrors."""
        with self.assertRaises(ValueError):
            validate_port_number("invalid")
        with self.assertRaises(ValueError):
            validate_port_number("0")
        with self.assertRaises(ValueError):
            validate_port_number("65536")
        with self.assertRaises(ValueError):
            validate_port_number("-80")

    def test_parse_remote_endpoint_success(self) -> None:
        """Verifies valid remote endpoint url parsing and fallbacks."""
        # Websocket fallback
        parsed: ParseResult = parse_remote_endpoint("example.com")
        self.assertEqual(parsed.scheme, "ws")
        self.assertEqual(parsed.hostname, "example.com")

        # Precise URL input
        parsed = parse_remote_endpoint("wss://tunnel.domain.com:8443/path")
        self.assertEqual(parsed.scheme, "wss")
        self.assertEqual(parsed.hostname, "tunnel.domain.com")
        self.assertEqual(parsed.port, 8443)
        self.assertEqual(parsed.path, "/path")

        # gRPC scheme
        parsed = parse_remote_endpoint("grpc://127.0.0.1/MyService")
        self.assertEqual(parsed.scheme, "grpc")
        self.assertEqual(parsed.hostname, "127.0.0.1")
        self.assertEqual(parsed.path, "/MyService")

    def test_parse_remote_endpoint_failure(self) -> None:
        """Verifies that endpoints without resolveable hostnames raise ValueError."""
        with self.assertRaises(ValueError):
            parse_remote_endpoint("://")

    def test_determine_tunnel_mode_autodetect(self) -> None:
        """Verifies automatic tunnel mode heuristics based on url scheme."""
        self.assertEqual(determine_tunnel_mode(None, "tcp"), "server")
        self.assertEqual(determine_tunnel_mode(None, "ws"), "client")
        self.assertEqual(determine_tunnel_mode(None, "wss"), "client")
        self.assertEqual(determine_tunnel_mode(None, "grpc"), "client")

    def test_determine_tunnel_mode_override(self) -> None:
        """Verifies manual override modes."""
        self.assertEqual(determine_tunnel_mode("client", "tcp"), "client")
        self.assertEqual(determine_tunnel_mode("server", "ws"), "server")

        with self.assertRaises(ValueError):
            determine_tunnel_mode("invalid_mode", "ws")

    def test_determine_transport_protocol(self) -> None:
        """Verifies scheme-to-transport mapping matching V2Ray's naming guidelines."""
        self.assertEqual(determine_transport_protocol("ws"), "ws")
        self.assertEqual(determine_transport_protocol("wss"), "ws")
        self.assertEqual(determine_transport_protocol("grpc"), "grpc")
        self.assertEqual(determine_transport_protocol("h2"), "h2")
        self.assertEqual(determine_transport_protocol("http"), "h2")
        self.assertEqual(determine_transport_protocol("tcp"), "tcp")
        self.assertEqual(determine_transport_protocol("tls"), "tcp")

    def test_generate_stream_settings_websocket(self) -> None:
        """Verifies streamSettings generation for WebSocket without TLS."""
        settings: Dict[str, Any] = generate_stream_settings(
            transport_protocol="ws",
            hostname="example.com",
            path="/tunnel",
            tls_enabled=False,
            tunnel_mode="client",
            sni_override="example.com",
            certificate_file="",
            key_file="",
        )
        self.assertEqual(settings["network"], "ws")
        self.assertEqual(settings["wsSettings"]["path"], "/tunnel")
        self.assertNotIn("security", settings)

    def test_generate_stream_settings_grpc_tls_client(self) -> None:
        """Verifies streamSettings generation for gRPC client with TLS enabled."""
        settings: Dict[str, Any] = generate_stream_settings(
            transport_protocol="grpc",
            hostname="example.com",
            path="/CustomService",
            tls_enabled=True,
            tunnel_mode="client",
            sni_override="sni.custom.com",
            certificate_file="",
            key_file="",
        )
        self.assertEqual(settings["network"], "grpc")
        self.assertEqual(settings["grpcSettings"]["serviceName"], "CustomService")
        self.assertEqual(settings["grpcSettings"]["host"], "example.com")
        self.assertEqual(settings["security"], "tls")
        self.assertEqual(settings["tlsSettings"]["serverName"], "sni.custom.com")
        self.assertEqual(settings["tlsSettings"]["allowInsecure"], False)

    def test_generate_stream_settings_h2_tls_server(self) -> None:
        """Verifies streamSettings generation for HTTP/2 server with TLS enabled."""
        settings: Dict[str, Any] = generate_stream_settings(
            transport_protocol="h2",
            hostname="example.com",
            path="/h2-path",
            tls_enabled=True,
            tunnel_mode="server",
            sni_override="example.com",
            certificate_file="/etc/ssl/cert.pem",
            key_file="/etc/ssl/key.pem",
        )
        self.assertEqual(settings["network"], "h2")
        self.assertEqual(settings["httpSettings"]["path"], "/h2-path")
        self.assertEqual(settings["httpSettings"]["host"], ["example.com"])
        self.assertEqual(settings["security"], "tls")
        self.assertEqual(
            settings["tlsSettings"]["certificates"][0]["certificateFile"],
            "/etc/ssl/cert.pem",
        )
        self.assertEqual(
            settings["tlsSettings"]["certificates"][0]["keyFile"],
            "/etc/ssl/key.pem",
        )

    def test_generate_inbound_configuration_client(self) -> None:
        """Verifies inbound configuration details in client mode."""
        stream_settings: Dict[str, Any] = {"network": "ws"}
        inbound: Dict[str, Any] = generate_inbound_configuration(
            listen_port=1234,
            address="example.com",
            target_port=443,
            tunnel_mode="client",
            stream_settings=stream_settings,
            tag="my-tag",
        )
        self.assertEqual(inbound["port"], 1234)
        self.assertEqual(inbound["protocol"], "dokodemo-door")
        self.assertEqual(inbound["settings"]["address"], "example.com")
        self.assertEqual(inbound["settings"]["port"], 443)
        self.assertEqual(inbound["tag"], "my-tag-in")
        # Client mode has streamSettings on outbound, not inbound
        self.assertNotIn("streamSettings", inbound)

    def test_generate_inbound_configuration_server(self) -> None:
        """Verifies inbound configuration details in server mode."""
        stream_settings: Dict[str, Any] = {"network": "tcp", "security": "tls"}
        inbound: Dict[str, Any] = generate_inbound_configuration(
            listen_port=443,
            address="127.0.0.1",
            target_port=22,
            tunnel_mode="server",
            stream_settings=stream_settings,
            tag=None,
        )
        self.assertEqual(inbound["port"], 443)
        self.assertEqual(inbound["protocol"], "dokodemo-door")
        self.assertEqual(inbound["settings"]["address"], "127.0.0.1")
        self.assertEqual(inbound["settings"]["port"], 22)
        self.assertNotIn("tag", inbound)
        # Server mode binds transport streamSettings to the inbound connection
        self.assertEqual(inbound["streamSettings"], stream_settings)

    def test_generate_outbound_configuration_client(self) -> None:
        """Verifies outbound configuration details in client mode."""
        stream_settings: Dict[str, Any] = {"network": "ws", "security": "tls"}
        outbound: Dict[str, Any] = generate_outbound_configuration(
            tunnel_mode="client",
            stream_settings=stream_settings,
            tag="test-tag",
        )
        self.assertEqual(outbound["protocol"], "freedom")
        self.assertEqual(outbound["tag"], "test-tag-out")
        # Client mode binds transport streamSettings to the outbound connection
        self.assertEqual(outbound["streamSettings"], stream_settings)

    def test_generate_outbound_configuration_server(self) -> None:
        """Verifies outbound configuration details in server mode."""
        stream_settings: Dict[str, Any] = {"network": "tcp"}
        outbound: Dict[str, Any] = generate_outbound_configuration(
            tunnel_mode="server",
            stream_settings=stream_settings,
            tag=None,
        )
        self.assertEqual(outbound["protocol"], "freedom")
        self.assertNotIn("tag", outbound)
        # Server mode has streamSettings on inbound, not outbound
        self.assertNotIn("streamSettings", outbound)

    def test_assemble_complete_configuration_tagged(self) -> None:
        """Verifies complete V2Ray config assembly and routing isolation blocks."""
        inbound: Dict[str, Any] = {"port": 1234, "tag": "tag-in"}
        outbound: Dict[str, Any] = {"protocol": "freedom", "tag": "tag-out"}

        config: Dict[str, Any] = assemble_complete_configuration(
            inbound=inbound,
            outbound=outbound,
            tag="tag",
        )

        self.assertEqual(config["log"]["loglevel"], "info")
        self.assertEqual(config["inbounds"], [inbound])
        self.assertEqual(config["outbounds"], [outbound])

        # Check routing rule generation
        routing_rule = config["routing"]["rules"][0]
        self.assertEqual(routing_rule["type"], "field")
        self.assertEqual(routing_rule["inboundTag"], ["tag-in"])
        self.assertEqual(routing_rule["outboundTag"], "tag-out")

