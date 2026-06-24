#!/usr/bin/env python3
"""
Unit tests for the V2Ray Tunnel Configuration Generator.

This test suite verifies url parsing, transport logic, mode resolution,
streamSettings creation, and inbound/outbound JSON generation under various
flag and option combinations.
"""

import json
import unittest
import unittest.mock
from typing import Any, Dict
from urllib.parse import ParseResult

# Import functions to test directly from scripts.v2ray_tunnel
from scripts.v2ray_tunnel import (
    ProxyConfiguration,
    assemble_complete_configuration,
    determine_transport_protocol,
    determine_tunnel_mode,
    generate_inbound_configuration,
    generate_outbound_configuration,
    generate_proxy_outbound_configuration,
    generate_stream_settings,
    parse_proxy_endpoint_url,
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

    def test_parse_proxy_endpoint_url_socks_no_auth(self) -> None:
        """Verifies parsing of SOCKS proxy URL without credentials."""
        proxy_config = parse_proxy_endpoint_url("socks5://127.0.0.1:1080")
        self.assertEqual(proxy_config.protocol, "socks")
        self.assertEqual(proxy_config.address, "127.0.0.1")
        self.assertEqual(proxy_config.port, 1080)
        self.assertIsNone(proxy_config.username)
        self.assertIsNone(proxy_config.password)

    def test_parse_proxy_endpoint_url_socks_with_auth(self) -> None:
        """Verifies parsing of SOCKS proxy URL with credentials."""
        proxy_config = parse_proxy_endpoint_url("socks5://myuser:mypass@proxy.domain.com:1081")
        self.assertEqual(proxy_config.protocol, "socks")
        self.assertEqual(proxy_config.address, "proxy.domain.com")
        self.assertEqual(proxy_config.port, 1081)
        self.assertEqual(proxy_config.username, "myuser")
        self.assertEqual(proxy_config.password, "mypass")

    def test_parse_proxy_endpoint_url_http_default_port(self) -> None:
        """Verifies parsing of HTTP proxy URL with default port resolution."""
        proxy_config = parse_proxy_endpoint_url("http://127.0.0.1")
        self.assertEqual(proxy_config.protocol, "http")
        self.assertEqual(proxy_config.address, "127.0.0.1")
        self.assertEqual(proxy_config.port, 8080)

    def test_parse_proxy_endpoint_url_invalid_schemes(self) -> None:
        """Verifies that unsupported or missing schemes raise ValueError."""
        with self.assertRaises(ValueError):
            parse_proxy_endpoint_url("127.0.0.1:1080")
        with self.assertRaises(ValueError):
            parse_proxy_endpoint_url("ftp://127.0.0.1:1080")

    def test_generate_proxy_outbound_configuration_socks_auth(self) -> None:
        """Verifies generation of SOCKS proxy outbound block with user authentication."""
        proxy_config = ProxyConfiguration(
            protocol="socks",
            address="127.0.0.1",
            port=1080,
            username="testuser",
            password="testpassword",
        )
        outbound = generate_proxy_outbound_configuration(proxy_config, "socks-proxy-out")
        self.assertEqual(outbound["protocol"], "socks")
        self.assertEqual(outbound["tag"], "socks-proxy-out")
        server = outbound["settings"]["servers"][0]
        self.assertEqual(server["address"], "127.0.0.1")
        self.assertEqual(server["port"], 1080)
        self.assertEqual(server["users"][0]["user"], "testuser")
        self.assertEqual(server["users"][0]["pass"], "testpassword")

    def test_generate_proxy_outbound_configuration_http_no_auth(self) -> None:
        """Verifies generation of HTTP proxy outbound block without authentication."""
        proxy_config = ProxyConfiguration(
            protocol="http",
            address="proxy.example.com",
            port=8080,
        )
        outbound = generate_proxy_outbound_configuration(proxy_config, "http-proxy-out")
        self.assertEqual(outbound["protocol"], "http")
        self.assertEqual(outbound["tag"], "http-proxy-out")
        server = outbound["settings"]["servers"][0]
        self.assertEqual(server["address"], "proxy.example.com")
        self.assertEqual(server["port"], 8080)
        self.assertEqual(server["user"], [])

    def test_generate_outbound_configuration_with_proxy_tag(self) -> None:
        """Verifies that proxySettings is correctly attached to the main outbound."""
        stream_settings = {"network": "ws"}
        outbound = generate_outbound_configuration(
            tunnel_mode="client",
            stream_settings=stream_settings,
            tag="my-tunnel",
            proxy_tag="my-proxy-out",
        )
        self.assertEqual(outbound["protocol"], "freedom")
        self.assertEqual(outbound["tag"], "my-tunnel-out")
        self.assertEqual(outbound["proxySettings"]["tag"], "my-proxy-out")

    def test_assemble_complete_configuration_with_proxy(self) -> None:
        """Verifies assembly of complete configuration with an upstream proxy outbound."""
        inbound = {"port": 1234, "tag": "inbound-tag"}
        outbound = {"protocol": "freedom", "tag": "outbound-tag"}
        proxy_outbound = {"protocol": "socks", "tag": "proxy-outbound-tag"}

        config = assemble_complete_configuration(
            inbound=inbound,
            outbound=outbound,
            tag=None,
            proxy_outbound=proxy_outbound,
        )
        self.assertEqual(config["inbounds"], [inbound])
        self.assertEqual(config["outbounds"], [outbound, proxy_outbound])

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--listen", "1234", "--remote", "ws://example.com", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_run_flag(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that the main function calls subprocess.run when --run is specified."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], ["v2ray", "run", "-format", "json"])
        self.assertIn(b"example.com", kwargs["input"])

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--listen", "1234", "--remote", "ws://example.com", "--run", "--inbound"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_run_and_inbound_flag(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that main works with --run and --inbound, printing only inbound to stdout and executing with complete config."""
        from scripts.v2ray_tunnel import main
        main()
        
        # Verify subprocess.run was called with complete config
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        config_data = json.loads(kwargs["input"].decode("utf-8"))
        self.assertIn("inbounds", config_data)
        self.assertIn("outbounds", config_data)

        # Verify print was called to output only the inbound configuration
        printed_args = [call[0][0] for call in mock_print.call_args_list]
        inbound_printed = False
        for arg in printed_args:
            try:
                data = json.loads(arg)
                if "port" in data and "protocol" in data and "settings" in data:
                    inbound_printed = True
                    self.assertNotIn("outbounds", data)
            except (json.JSONDecodeError, TypeError):
                continue
        self.assertTrue(inbound_printed)

    def test_generate_random_port(self) -> None:
        """Verifies that generate_random_port returns a valid port within the safe range."""
        from scripts.v2ray_tunnel import generate_random_port
        port = generate_random_port()
        self.assertTrue(10000 <= port <= 65535)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "ws://example.com", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_dynamic_port_allocation(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that main works without --listen and allocates a dynamic port."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        # Verify that the generated config has a valid listening port
        args, kwargs = mock_run.call_args
        config_data = json.loads(kwargs["input"].decode("utf-8"))
        inbound_port = config_data["inbounds"][0]["port"]
        self.assertTrue(1024 <= inbound_port <= 65535)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("subprocess.Popen")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "ws://example.com", "--ssh", "myuser"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_ssh_flag_success(self, mock_print: Any, mock_popen: Any, mock_run: Any) -> None:
        """Verifies that --ssh starts v2ray in background and ssh in foreground."""
        from scripts.v2ray_tunnel import main
        # Mock Popen return value to mock v2ray process
        mock_process = unittest.mock.MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process

        main()

        # Check Popen was called for V2Ray
        mock_popen.assert_called_once()
        popen_args = mock_popen.call_args[0][0]
        self.assertEqual(popen_args, ["v2ray", "run", "-format", "json"])

        # Check subprocess.run was called for SSH
        mock_run.assert_called_once()
        ssh_args = mock_run.call_args[0][0]
        self.assertEqual(ssh_args[0], "ssh")
        self.assertIn("myuser@127.0.0.1", ssh_args)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("subprocess.Popen")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "tcp://example.com", "--mode", "server", "--ssh"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_ssh_flag_server_mode_success(self, mock_print: Any, mock_popen: Any, mock_run: Any) -> None:
        """Verifies that --ssh in server mode works successfully."""
        from scripts.v2ray_tunnel import main
        # Mock Popen return value to mock v2ray process
        mock_process = unittest.mock.MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process

        main()

        # Verify that both background V2Ray and foreground SSH were launched successfully
        mock_popen.assert_called_once()
        mock_run.assert_called_once()
        ssh_args = mock_run.call_args[0][0]
        self.assertEqual(ssh_args[0], "ssh")

