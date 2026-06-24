import json
import unittest
import unittest.mock
from typing import Any

from scripts.v2ray_tunnel import (
    EndpointConfiguration,
    ProxyConfiguration,
    assemble_complete_configuration,
    generate_endpoint_stream_settings,
    generate_inbound_configuration,
    generate_outbound_configuration,
    generate_proxy_outbound_configuration,
    generate_random_port,
    is_ip_address,
    parse_endpoint,
    parse_proxy_endpoint_url,
    validate_port_number,
)


class TestV2RayTunnelGenerator(unittest.TestCase):
    """
    Unit and integration test suite for the V2Ray Tunnel Configuration Generator.
    """

    def test_validate_port_number_success(self) -> None:
        """Verifies that validate_port_number accepts valid port values."""
        self.assertEqual(validate_port_number(80), 80)
        self.assertEqual(validate_port_number("443"), 443)
        self.assertEqual(validate_port_number("65535"), 65535)

    def test_validate_port_number_failures(self) -> None:
        """Verifies that validate_port_number rejects invalid port values."""
        with self.assertRaises(ValueError):
            validate_port_number("invalid")
        with self.assertRaises(ValueError):
            validate_port_number(0)
        with self.assertRaises(ValueError):
            validate_port_number(65536)

    def test_is_ip_address(self) -> None:
        """Verifies that is_ip_address correctly identifies IPv4 and IPv6 addresses."""
        # IPv4
        self.assertTrue(is_ip_address("127.0.0.1"))
        self.assertTrue(is_ip_address("8.8.8.8"))
        self.assertTrue(is_ip_address("0.0.0.0"))
        # IPv6
        self.assertTrue(is_ip_address("::1"))
        self.assertTrue(is_ip_address("2001:db8::1"))
        # Hostnames (not IPs)
        self.assertFalse(is_ip_address("localhost"))
        self.assertFalse(is_ip_address("example.com"))
        self.assertFalse(is_ip_address("c5-ts.maomihz.com"))

    def test_parse_endpoint_plain_port(self) -> None:
        """Verifies that a simple port number resolves to plain TCP with no address."""
        endpoint = parse_endpoint("1234", is_inbound=True)
        self.assertEqual(
            endpoint,
            EndpointConfiguration(
                transport_protocol="tcp",
                address=None,
                port=1234,
                path="",
                tls_enabled=False,
            ),
        )

    def test_parse_endpoint_url_ws_insecure(self) -> None:
        """Verifies parsing of an insecure WebSocket URL."""
        endpoint = parse_endpoint("ws://example.com:8080/ws-path", is_inbound=False)
        self.assertEqual(
            endpoint,
            EndpointConfiguration(
                transport_protocol="ws",
                address="example.com",
                port=8080,
                path="/ws-path",
                tls_enabled=False,
            ),
        )

    def test_parse_endpoint_url_wss_secure(self) -> None:
        """Verifies parsing of a secure WebSocket URL."""
        endpoint = parse_endpoint("wss://example.com/ws-path", is_inbound=False)
        self.assertEqual(
            endpoint,
            EndpointConfiguration(
                transport_protocol="ws",
                address="example.com",
                port=443,  # Defaults to 443 for secure
                path="/ws-path",
                tls_enabled=True,
            ),
        )

    def test_parse_endpoint_url_grpc_secure(self) -> None:
        """Verifies parsing of a secure gRPC URL."""
        endpoint = parse_endpoint("grpc://127.0.0.1", is_inbound=True)
        self.assertEqual(
            endpoint,
            EndpointConfiguration(
                transport_protocol="grpc",
                address="127.0.0.1",
                port=443,  # Defaults to 443 for secure
                path="",
                tls_enabled=True,
            ),
        )

    def test_parse_proxy_endpoint_url_socks(self) -> None:
        """Verifies parsing of a standard SOCKS5 proxy URL."""
        config = parse_proxy_endpoint_url("socks5://localhost:1080")
        self.assertEqual(
            config,
            ProxyConfiguration(
                protocol="socks",
                address="localhost",
                port=1080,
                username=None,
                password=None,
            ),
        )

    def test_parse_proxy_endpoint_url_http_auth(self) -> None:
        """Verifies parsing of an HTTP proxy URL with username/password authentication."""
        config = parse_proxy_endpoint_url("http://user:pass@proxy.com:8080")
        self.assertEqual(
            config,
            ProxyConfiguration(
                protocol="http",
                address="proxy.com",
                port=8080,
                username="user",
                password="pass",
            ),
        )

    def test_parse_proxy_endpoint_url_failures(self) -> None:
        """Verifies proxy URL validation failures."""
        with self.assertRaises(ValueError):
            parse_proxy_endpoint_url("invalid-url")
        with self.assertRaises(ValueError):
            parse_proxy_endpoint_url("ftp://localhost")

    def test_generate_endpoint_stream_settings_plain(self) -> None:
        """Verifies that plain TCP endpoint yields no streamSettings."""
        endpoint = parse_endpoint("1234", is_inbound=True)
        settings = generate_endpoint_stream_settings(
            endpoint=endpoint,
            is_inbound=True,
            sni_override="",
            certificate_file="",
            key_file="",
        )
        self.assertIsNone(settings)

    def test_generate_endpoint_stream_settings_ws_inbound_secure(self) -> None:
        """Verifies secure WebSocket streamSettings for an inbound listener."""
        endpoint = parse_endpoint("wss://:443/tunnel", is_inbound=True)
        settings = generate_endpoint_stream_settings(
            endpoint=endpoint,
            is_inbound=True,
            sni_override="",
            certificate_file="/cert.pem",
            key_file="/key.pem",
        )
        self.assertIsNotNone(settings)
        self.assertEqual(settings["network"], "ws")
        self.assertEqual(settings["security"], "tls")
        self.assertEqual(settings["wsSettings"]["path"], "/tunnel")
        self.assertEqual(
            settings["tlsSettings"]["certificates"][0]["certificateFile"],
            "/cert.pem",
        )

    def test_generate_endpoint_stream_settings_ws_outbound_secure(self) -> None:
        """Verifies secure WebSocket streamSettings for an outbound client."""
        endpoint = parse_endpoint("wss://example.com/tunnel", is_inbound=False)
        settings = generate_endpoint_stream_settings(
            endpoint=endpoint,
            is_inbound=False,
            sni_override="custom.com",
            certificate_file="",
            key_file="",
        )
        self.assertIsNotNone(settings)
        self.assertEqual(settings["network"], "ws")
        self.assertEqual(settings["security"], "tls")
        self.assertEqual(settings["tlsSettings"]["serverName"], "custom.com")

    def test_generate_endpoint_stream_settings_ws_outbound_secure_no_sni_if_empty(self) -> None:
        """Verifies that if sni_override is empty, serverName is omitted from tlsSettings."""
        endpoint = parse_endpoint("wss://1.2.3.4/tunnel", is_inbound=False)
        settings = generate_endpoint_stream_settings(
            endpoint=endpoint,
            is_inbound=False,
            sni_override="",
            certificate_file="",
            key_file="",
        )
        self.assertIsNotNone(settings)
        self.assertEqual(settings["network"], "ws")
        self.assertEqual(settings["security"], "tls")
        self.assertNotIn("serverName", settings["tlsSettings"])

    def test_generate_inbound_configuration(self) -> None:
        """Verifies V2Ray inbound block schema construction."""
        inbound = generate_inbound_configuration(
            listen_port=1234,
            listen_address="127.0.0.1",
            address="example.com",
            target_port=22,
            stream_settings={"network": "ws"},
            tag="mytag",
        )
        self.assertEqual(inbound["port"], 1234)
        self.assertEqual(inbound["listen"], "127.0.0.1")
        self.assertEqual(inbound["protocol"], "dokodemo-door")
        self.assertEqual(inbound["settings"]["address"], "example.com")
        self.assertEqual(inbound["settings"]["port"], 22)
        self.assertEqual(inbound["streamSettings"]["network"], "ws")
        self.assertEqual(inbound["tag"], "mytag-in")

    def test_generate_outbound_configuration(self) -> None:
        """Verifies V2Ray outbound block schema construction."""
        outbound = generate_outbound_configuration(
            stream_settings={"network": "grpc"},
            tag="mytag",
            proxy_tag="myproxy",
        )
        self.assertEqual(outbound["protocol"], "freedom")
        self.assertEqual(outbound["streamSettings"]["network"], "grpc")
        self.assertEqual(outbound["tag"], "mytag-out")
        self.assertEqual(outbound["proxySettings"]["tag"], "myproxy")
        self.assertNotIn("settings", outbound)

    def test_generate_outbound_configuration_with_domain_strategy(self) -> None:
        """Verifies V2Ray outbound block with explicit domainStrategy."""
        outbound = generate_outbound_configuration(
            stream_settings={"network": "grpc"},
            tag="mytag",
            domain_strategy="UseIP",
        )
        self.assertEqual(outbound["protocol"], "freedom")
        self.assertEqual(outbound["settings"]["domainStrategy"], "UseIP")

    def test_generate_proxy_outbound_configuration_socks(self) -> None:
        """Verifies upstream SOCKS proxy outbound block generation."""
        proxy_config = parse_proxy_endpoint_url("socks5://user:pass@localhost:1080")
        outbound = generate_proxy_outbound_configuration(proxy_config, "proxy-tag")
        self.assertEqual(outbound["protocol"], "socks")
        self.assertEqual(outbound["tag"], "proxy-tag")
        server = outbound["settings"]["servers"][0]
        self.assertEqual(server["address"], "localhost")
        self.assertEqual(server["port"], 1080)
        self.assertEqual(server["users"][0]["user"], "user")
        self.assertEqual(server["users"][0]["pass"], "pass")

    def test_generate_proxy_outbound_configuration_http(self) -> None:
        """Verifies upstream HTTP proxy outbound block generation uses the correct 'users' key."""
        proxy_config = parse_proxy_endpoint_url("http://user:pass@localhost:8080")
        outbound = generate_proxy_outbound_configuration(proxy_config, "proxy-tag")
        self.assertEqual(outbound["protocol"], "http")
        self.assertEqual(outbound["tag"], "proxy-tag")
        server = outbound["settings"]["servers"][0]
        self.assertEqual(server["address"], "localhost")
        self.assertEqual(server["port"], 8080)
        self.assertEqual(server["users"][0]["user"], "user")
        self.assertEqual(server["users"][0]["pass"], "pass")

    def test_assemble_complete_configuration(self) -> None:
        """Verifies merging of components into the master config schema."""
        inbound = {"tag": "in-tag"}
        outbound = {"tag": "out-tag"}
        complete = assemble_complete_configuration(
            inbound=inbound,
            outbound=outbound,
            tag="mytag",
            proxy_outbound={"tag": "proxy-tag"},
        )
        self.assertEqual(complete["inbounds"], [inbound])
        self.assertEqual(complete["outbounds"], [outbound, {"tag": "proxy-tag"}])
        self.assertEqual(complete["routing"]["rules"][0]["outboundTag"], "out-tag")
        self.assertNotIn("dns", complete)

    def test_assemble_complete_configuration_with_dns(self) -> None:
        """Verifies merging of custom DNS block into the master config schema."""
        inbound = {"tag": "in-tag"}
        outbound = {"tag": "out-tag"}
        complete = assemble_complete_configuration(
            inbound=inbound,
            outbound=outbound,
            tag="mytag",
            dns_servers=["1.1.1.1", "8.8.8.8"],
        )
        self.assertEqual(complete["dns"]["servers"], ["1.1.1.1", "8.8.8.8"])

    def test_generate_random_port(self) -> None:
        """Verifies that generate_random_port returns a valid port in the safe range."""
        port = generate_random_port()
        self.assertTrue(10000 <= port <= 65535)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--listen", "1234", "--remote", "wss://example.com/ws", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_client_flow(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies integrated execution for a secure client forwarding tunnel."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        config = json.loads(kwargs["input"].decode("utf-8"))
        
        # Inbound must be plain TCP and have no listen key (defaults to all interfaces)
        self.assertNotIn("streamSettings", config["inbounds"][0])
        self.assertNotIn("listen", config["inbounds"][0])
        self.assertEqual(config["inbounds"][0]["port"], 1234)
        
        # Outbound must be secure WebSocket
        self.assertEqual(config["outbounds"][0]["streamSettings"]["network"], "ws")
        self.assertEqual(config["outbounds"][0]["streamSettings"]["security"], "tls")

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--listen", "wss://:443/tunnel", "--remote", "tcp://127.0.0.1:22", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_server_flow(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies integrated execution for a secure server decryption tunnel."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        config = json.loads(kwargs["input"].decode("utf-8"))

        # Inbound must be secure WebSocket and have no listen key (defaults to all interfaces)
        self.assertEqual(config["inbounds"][0]["streamSettings"]["network"], "ws")
        self.assertEqual(config["inbounds"][0]["streamSettings"]["security"], "tls")
        self.assertNotIn("listen", config["inbounds"][0])
        
        # Outbound must be plain TCP
        self.assertNotIn("streamSettings", config["outbounds"][0])

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--listen", "127.0.0.1:1234", "--remote", "wss://example.com/ws", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_explicit_listen_address(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that an explicit listen IP is preserved in the V2Ray config."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        config = json.loads(kwargs["input"].decode("utf-8"))
        self.assertEqual(config["inbounds"][0]["listen"], "127.0.0.1")

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "tcp://example.com:22", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_dynamic_port_allocation(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that dynamic port allocation generates a valid random port and binds securely to localhost."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        config = json.loads(kwargs["input"].decode("utf-8"))
        inbound_port = config["inbounds"][0]["port"]
        self.assertTrue(10000 <= inbound_port <= 65535)
        self.assertEqual(config["inbounds"][0]["listen"], "127.0.0.1")

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("subprocess.Popen")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "tcp://example.com:22", "--ssh"])
    @unittest.mock.patch("builtins.print")
    def test_main_ssh_success(self, mock_print: Any, mock_popen: Any, mock_run: Any) -> None:
        """Verifies that --ssh launches V2Ray in background and SSH in foreground."""
        from scripts.v2ray_tunnel import main
        mock_process = unittest.mock.MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        main()

        mock_popen.assert_called_once()
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0][0], "ssh")

    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--listen", "wss://:443", "--remote", "tcp://127.0.0.1:22", "--ssh"])
    @unittest.mock.patch("builtins.print")
    def test_main_ssh_failure_on_secure_listener(self, mock_print: Any) -> None:
        """Verifies that --ssh is rejected when the inbound listener is secure."""
        from scripts.v2ray_tunnel import main
        with self.assertRaises(SystemExit) as context:
            main()
        self.assertEqual(context.exception.code, 1)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "ws://example.com", "--run", "--inbound"])
    @unittest.mock.patch("builtins.print")
    def test_main_config_filter_with_run(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that --run with --inbound filter prints only inbound but runs full config."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        
        # Verify run gets full config
        args, kwargs = mock_run.call_args
        config = json.loads(kwargs["input"].decode("utf-8"))
        self.assertIn("inbounds", config)
        self.assertIn("outbounds", config)

        # Verify print was called only for inbound
        printed_args = [call[0][0] for call in mock_print.call_args_list]
        inbound_printed = False
        for arg in printed_args:
            try:
                data = json.loads(arg)
                if "port" in data and "protocol" in data:
                    inbound_printed = True
                    self.assertNotIn("outbounds", data)
            except (json.JSONDecodeError, TypeError):
                continue
        self.assertTrue(inbound_printed)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("sys.argv", ["v2ray_tunnel.py", "--remote", "tcp://example.com:22", "--dns", "1.1.1.1,8.8.8.8", "--run"])
    @unittest.mock.patch("builtins.print")
    def test_main_with_dns_configuration(self, mock_print: Any, mock_run: Any) -> None:
        """Verifies that passing --dns generates the root-level dns block and defaults domainStrategy to UseIP."""
        from scripts.v2ray_tunnel import main
        main()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        config = json.loads(kwargs["input"].decode("utf-8"))
        
        # DNS block must be present
        self.assertEqual(config["dns"]["servers"], ["1.1.1.1", "8.8.8.8"])
        
        # Outbound must have domainStrategy UseIP
        self.assertEqual(config["outbounds"][0]["settings"]["domainStrategy"], "UseIP")
