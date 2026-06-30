"""Unit tests for the V2Ray Ansible filter plugins."""

from typing import Any, Dict, List

from ansible_collections.local.infra.plugins.filter import v2ray


def test_build_vmess_inbound() -> None:
    """Verify that build_vmess_inbound constructs a correct VMess inbound block."""
    inbound_spec: Dict[str, Any] = {
        "vmess": 10086,
        "clients": [{"id": "uuid-placeholder", "alterId": 0}],
        "tag": "vmess-in",
    }
    block = v2ray.build_vmess_inbound(inbound_spec)
    assert block["protocol"] == "vmess"
    assert block["port"] == 10086
    assert block["listen"] == "::"
    assert block["tag"] == "vmess-in"
    assert block["settings"]["clients"] == [{"id": "uuid-placeholder", "alterId": 0}]


def test_build_vless_inbound() -> None:
    """Verify that build_vless_inbound constructs a correct VLESS inbound block."""
    inbound_spec: Dict[str, Any] = {
        "vless": 10087,
        "clients": [{"id": "uuid-placeholder"}],
        "tag": "vless-in",
    }
    block = v2ray.build_vless_inbound(inbound_spec)
    assert block["protocol"] == "vless"
    assert block["port"] == 10087
    assert block["listen"] == "127.0.0.1"
    assert block["tag"] == "vless-in"
    assert block["settings"]["clients"] == [{"id": "uuid-placeholder"}]
    assert block["settings"]["decryption"] == "none"


def test_build_shadowsocks_inbound() -> None:
    """Verify Shadowsocks inbound creation."""
    inbound_spec: Dict[str, Any] = {
        "ss": 10088,
        "password": "shadowsocks-password",
        "method": "chacha20-ietf-poly1305",
        "tag": "ss-in",
    }
    block = v2ray.build_shadowsocks_inbound(inbound_spec)
    assert block["protocol"] == "shadowsocks"
    assert block["port"] == 10088
    assert block["listen"] == "::"
    assert block["tag"] == "ss-in"
    assert block["settings"]["method"] == "chacha20-ietf-poly1305"
    assert block["settings"]["password"] == "shadowsocks-password"


def test_build_socks_inbound() -> None:
    """Verify standard Socks inbound block configuration."""
    inbound_spec: Dict[str, Any] = {"socks": 1080, "tag": "socks-in"}
    block = v2ray.build_socks_inbound(inbound_spec)
    assert block["protocol"] == "socks"
    assert block["port"] == 1080
    assert block["listen"] == "127.0.0.1"
    assert block["tag"] == "socks-in"
    assert block["settings"]["auth"] == "noauth"


def test_build_http_inbound() -> None:
    """Verify HTTP inbound block configuration."""
    inbound_spec: Dict[str, Any] = {"http": 8080, "tag": "http-in"}
    block = v2ray.build_http_inbound(inbound_spec)
    assert block["protocol"] == "http"
    assert block["port"] == 8080
    assert block["listen"] == "127.0.0.1"
    assert block["tag"] == "http-in"
    assert block["settings"]["auth"] == "noauth"


def test_build_tcp_relay_inbound() -> None:
    """Verify dokodemo-door inbound port forwarding configuration for TCP relay."""
    block = v2ray.build_tcp_relay_inbound(80, "192.168.1.1:8080")
    assert block["protocol"] == "dokodemo-door"
    assert block["port"] == 80
    assert block["listen"] == "::"
    assert block["tag"] == "tcp_relay_80"
    assert block["settings"]["address"] == "192.168.1.1"
    assert block["settings"]["port"] == 8080
    assert block["settings"]["network"] == "tcp"


def test_build_telegram_inbound() -> None:
    """Verify SOCKS inbound optimized for Telegram routing."""
    # No auth case
    inbound_spec: Dict[str, Any] = {"tg": 1088}
    block = v2ray.build_telegram_inbound(inbound_spec)
    assert block["protocol"] == "socks"
    assert block["port"] == 1088
    assert block["listen"] == "127.0.0.1"
    assert block["tag"] == "inbound-tg"
    assert block["settings"]["auth"] == "noauth"

    # User/Pass auth case
    inbound_spec_auth: Dict[str, Any] = {
        "tg": 1088,
        "accounts": [{"user": "tg-user", "pass": "tg-pass"}],
    }
    block_auth = v2ray.build_telegram_inbound(inbound_spec_auth)
    assert block_auth["settings"]["auth"] == "password"
    assert block_auth["settings"]["accounts"] == [
        {"user": "tg-user", "pass": "tg-pass"}
    ]
    assert block_auth["listen"] == "::"


def test_v2ray_config_filter_integration() -> None:
    """Verify integration of the complete config filter."""
    filter_module = v2ray.FilterModule()

    inbounds: List[Dict[str, Any]] = [
        {"socks": 1080, "tag": "socks-in"},
        {"tcp": {1234: "1.1.1.1:1234", 5678: "2.2.2.2:5678"}},
        {"tg": 1089},
    ]
    outbounds_default: List[Dict[str, Any]] = [
        {"protocol": "freedom", "tag": "direct"},
        {"protocol": "blackhole", "tag": "blocked"},
    ]
    outbounds_custom: List[Dict[str, Any]] = [
        {
            "protocol": "vmess",
            "tag": "proxy",
            "settings": {"vnext": [{"address": "proxy.server", "port": 443}]},
        }
    ]
    rules_default: List[Dict[str, Any]] = [
        {"ip": ["geoip:private"], "outboundTag": "blocked"}
    ]
    ads_domains: List[str] = ["vungle.com", "ironsrc.mob"]
    telegram_ips: List[str] = ["91.108.4.0/22", "149.154.160.0/20"]
    rules_custom: List[Dict[str, Any]] = [
        {"domain": ["geosite:cn"], "outboundTag": "direct"}
    ]

    config = filter_module.v2ray_config(
        inbounds=inbounds,
        outbounds_default=outbounds_default,
        outbounds_custom=outbounds_custom,
        rules_default=rules_default,
        ads_domains=ads_domains,
        telegram_ips=telegram_ips,
        rules_custom=rules_custom,
    )

    # Check basic properties
    assert config["log"]["loglevel"] == "info"
    assert len(config["inbounds"]) == 4  # socks + 2 dokodemo + tg
    assert len(config["outbounds"]) == 3  # 2 default + 1 custom
    assert config["transport"]["tcpSettings"]["header"]["type"] == "none"

    # Verify inbound tags list populated
    inbound_tags = [i["tag"] for i in config["inbounds"]]
    assert "socks-in" in inbound_tags
    assert "tcp_relay_1234" in inbound_tags
    assert "tcp_relay_5678" in inbound_tags
    assert "inbound-tg" in inbound_tags

    # Verify routing rules
    rules = config["routing"]["rules"]
    assert len(rules) == 6

    # 1. TCP Relay Rule
    assert rules[0]["inboundTag"] == ["tcp_relay_1234", "tcp_relay_5678"]
    assert rules[0]["outboundTag"] == "direct"

    # 2. Default Rules
    assert rules[1]["ip"] == ["geoip:private"]
    assert rules[1]["outboundTag"] == "blocked"

    # 3. Ad blocking Rules
    assert rules[2]["domain"] == ["domain:vungle.com", "domain:ironsrc.mob"]
    assert rules[2]["outboundTag"] == "blocked"

    # 4. Telegram Routing Rules
    assert rules[3]["ip"] == ["91.108.4.0/22", "149.154.160.0/20"]
    assert rules[3]["inboundTag"] == ["inbound-tg"]
    assert rules[3]["outboundTag"] == "direct"

    assert rules[4]["inboundTag"] == ["inbound-tg"]
    assert rules[4]["outboundTag"] == "blocked"

    # 5. Custom Rules
    assert rules[5]["domain"] == ["geosite:cn"]
    assert rules[5]["outboundTag"] == "direct"


def test_build_dokodemo_inbound() -> None:
    """Verify that build_dokodemo_inbound constructs a correct dokodemo inbound block."""
    inbound_spec: Dict[str, Any] = {
        "dokodemo": 12345,
        "listen": "127.0.0.1",
        "tag": "transparent-in",
        "network": "tcp,udp",
        "timeout": 30,
        "follow_redirect": True,
    }
    block = v2ray.build_dokodemo_inbound(inbound_spec)
    assert block["protocol"] == "dokodemo-door"
    assert block["port"] == 12345
    assert block["listen"] == "127.0.0.1"
    assert block["tag"] == "transparent-in"
    assert block["settings"]["network"] == "tcp,udp"
    assert block["settings"]["timeout"] == 30
    assert block["settings"]["followRedirect"] is True


def test_build_vless_outbound() -> None:
    """Verify that build_vless_outbound constructs a correct VLESS outbound block."""
    outbound_spec: Dict[str, Any] = {
        "vless": "vless.server.com",
        "port": 443,
        "tag": "out1004",
        "id": "vless-uuid-placeholder",
        "encryption": "none",
        "network": "ws",
        "security": "tls",
        "path": "/vlesspath",
    }
    block = v2ray.build_vless_outbound(outbound_spec)
    assert block["protocol"] == "vless"
    assert block["tag"] == "out1004"
    assert block["settings"]["vnext"][0]["address"] == "vless.server.com"
    assert block["settings"]["vnext"][0]["port"] == 443
    assert block["settings"]["vnext"][0]["users"][0]["id"] == "vless-uuid-placeholder"
    assert block["settings"]["vnext"][0]["users"][0]["encryption"] == "none"
    assert block["streamSettings"]["network"] == "ws"
    assert block["streamSettings"]["security"] == "tls"
    assert block["streamSettings"]["wsSettings"]["path"] == "/vlesspath"


def test_build_vmess_outbound() -> None:
    """Verify that build_vmess_outbound constructs a correct VMess outbound block."""
    outbound_spec: Dict[str, Any] = {
        "vmess": "proxy.server.com",
        "port": 443,
        "tag": "vmess-out",
        "uuid": "uuid-placeholder",
        "alter_id": 64,
        "network": "ws",
        "security_stream": "tls",
        "path": "/ray",
    }
    block = v2ray.build_vmess_outbound(outbound_spec)
    assert block["protocol"] == "vmess"
    assert block["tag"] == "vmess-out"
    assert block["settings"]["vnext"][0]["address"] == "proxy.server.com"
    assert block["settings"]["vnext"][0]["port"] == 443
    assert block["settings"]["vnext"][0]["users"][0]["id"] == "uuid-placeholder"
    assert block["settings"]["vnext"][0]["users"][0]["alterId"] == 64
    assert block["streamSettings"]["network"] == "ws"
    assert block["streamSettings"]["security"] == "tls"
    assert block["streamSettings"]["wsSettings"]["path"] == "/ray"


def test_build_shadowsocks_outbound() -> None:
    """Verify that build_shadowsocks_outbound constructs a correct Shadowsocks outbound block."""
    outbound_spec: Dict[str, Any] = {
        "ss": "ss.server.com",
        "port": 8388,
        "tag": "ss-out",
        "method": "chacha20-ietf-poly1305",
        "password": "ss-password",
    }
    block = v2ray.build_shadowsocks_outbound(outbound_spec)
    assert block["protocol"] == "shadowsocks"
    assert block["tag"] == "ss-out"
    assert block["settings"]["servers"][0]["address"] == "ss.server.com"
    assert block["settings"]["servers"][0]["port"] == 8388
    assert block["settings"]["servers"][0]["method"] == "chacha20-ietf-poly1305"
    assert block["settings"]["servers"][0]["password"] == "ss-password"


def test_build_trojan_outbound() -> None:
    """Verify that build_trojan_outbound constructs a correct Trojan outbound block."""
    outbound_spec: Dict[str, Any] = {
        "trojan": "trojan.server.com",
        "port": 443,
        "tag": "trojan-out",
        "password": "trojan-password",
    }
    block = v2ray.build_trojan_outbound(outbound_spec)
    assert block["protocol"] == "trojan"
    assert block["tag"] == "trojan-out"
    assert block["settings"]["servers"][0]["address"] == "trojan.server.com"
    assert block["settings"]["servers"][0]["port"] == 443
    assert block["settings"]["servers"][0]["password"] == "trojan-password"


def test_build_socks_outbound() -> None:
    """Verify that build_socks_outbound constructs a correct SOCKS outbound block."""
    outbound_spec: Dict[str, Any] = {
        "socks": "socks.server.com",
        "port": 1080,
        "tag": "socks-out",
        "username": "user",
        "password": "pwd",
    }
    block = v2ray.build_socks_outbound(outbound_spec)
    assert block["protocol"] == "socks"
    assert block["tag"] == "socks-out"
    assert block["settings"]["servers"][0]["address"] == "socks.server.com"
    assert block["settings"]["servers"][0]["port"] == 1080
    assert block["settings"]["servers"][0]["users"][0]["user"] == "user"
    assert block["settings"]["servers"][0]["users"][0]["pass"] == "pwd"


def test_build_http_outbound() -> None:
    """Verify that build_http_outbound constructs a correct HTTP outbound block."""
    outbound_spec: Dict[str, Any] = {
        "http": "http.server.com",
        "port": 8080,
        "tag": "http-out",
        "username": "user",
        "password": "pwd",
    }
    block = v2ray.build_http_outbound(outbound_spec)
    assert block["protocol"] == "http"
    assert block["tag"] == "http-out"
    assert block["settings"]["servers"][0]["address"] == "http.server.com"
    assert block["settings"]["servers"][0]["port"] == 8080
    assert block["settings"]["servers"][0]["users"][0]["user"] == "user"
    assert block["settings"]["servers"][0]["users"][0]["pass"] == "pwd"


def test_v2ray_config_filter_integration_extended() -> None:
    """Verify the integration of the complete config filter with new optional parameters."""
    filter_module = v2ray.FilterModule()

    inbounds: List[Dict[str, Any]] = [
        {"socks": 1080, "tag": "socks-in"},
        {"dokodemo": 12345, "tag": "transparent-in", "follow_redirect": True},
    ]
    outbounds_default: List[Dict[str, Any]] = [
        {"protocol": "freedom", "tag": "direct"},
    ]
    outbounds_custom: List[Dict[str, Any]] = [
        {
            "vless": "vless.server.com",
            "port": 443,
            "tag": "out1004",
            "id": "vless-uuid-placeholder",
            "encryption": "none",
            "network": "ws",
            "security": "tls",
            "path": "/vlesspath",
        }
    ]
    rules_default: List[Dict[str, Any]] = []
    ads_domains: List[str] = []
    telegram_ips: List[str] = []
    rules_custom: List[Dict[str, Any]] = [
        {
            "inboundTag": ["socks-in", "transparent-in"],
            "outboundTag": "out1004",
        }
    ]

    config = filter_module.v2ray_config(
        inbounds=inbounds,
        outbounds_default=outbounds_default,
        outbounds_custom=outbounds_custom,
        rules_default=rules_default,
        ads_domains=ads_domains,
        telegram_ips=telegram_ips,
        rules_custom=rules_custom,
        routing_strategy="AsIs",
        dns_servers=["1.1.1.1", "8.8.8.8"],
        policy={
            "levels": {"0": {"uplinkOnly": 0}},
        },
        extra_config={
            "other": "value",
            "routing": {
                "domainMatcher": "mph",
            },
            "log": {
                "loglevel": "debug",
            },
        },
    )

    assert config["log"]["loglevel"] == "debug"
    assert len(config["inbounds"]) == 2
    assert config["inbounds"][1]["protocol"] == "dokodemo-door"
    assert config["inbounds"][1]["settings"]["followRedirect"] is True

    assert len(config["outbounds"]) == 2
    assert config["outbounds"][0]["protocol"] == "freedom"
    assert config["outbounds"][1]["protocol"] == "vless"
    assert (
        config["outbounds"][1]["settings"]["vnext"][0]["address"] == "vless.server.com"
    )

    assert config["routing"]["domainStrategy"] == "AsIs"
    assert config["routing"]["domainMatcher"] == "mph"
    assert len(config["routing"]["rules"]) == 1
    assert config["routing"]["rules"][0]["inboundTag"] == ["socks-in", "transparent-in"]
    assert config["routing"]["rules"][0]["outboundTag"] == "out1004"

    assert config["dns"] == {"servers": ["1.1.1.1", "8.8.8.8"]}
    assert config["policy"] == {"levels": {"0": {"uplinkOnly": 0}}}
    assert config["other"] == "value"


def test_default_tags_generation() -> None:
    """Verify that default unique tags are generated for inbounds/outbounds when tag is missing."""
    # Test VMess Inbound default tag
    inbound_spec_vmess = {"vmess": 10086}
    block_vmess = v2ray.build_vmess_inbound(inbound_spec_vmess)
    assert block_vmess["tag"] == "inbound-vmess-10086"

    # Test VLESS Inbound default tag
    inbound_spec_vless = {"vless": 10087}
    block_vless = v2ray.build_vless_inbound(inbound_spec_vless)
    assert block_vless["tag"] == "inbound-vless-10087"

    # Test VLESS Outbound default tag
    outbound_spec_vless = {"vless": "proxy.example.com", "port": 443}
    block_vless_out = v2ray.build_vless_outbound(outbound_spec_vless)
    assert block_vless_out["tag"] == "outbound-vless-proxy.example.com-443"

    # Test SOCKS Outbound default tag
    outbound_spec_socks = {"socks": "socks.example.com", "port": 1080}
    block_socks_out = v2ray.build_socks_outbound(outbound_spec_socks)
    assert block_socks_out["tag"] == "outbound-socks-socks.example.com-1080"
