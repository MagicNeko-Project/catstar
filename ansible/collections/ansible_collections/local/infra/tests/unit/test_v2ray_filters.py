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


def test_build_dokodemo_inbound() -> None:
    """Verify dokodemo-door inbound port forwarding configuration."""
    block = v2ray.build_dokodemo_inbound(80, "192.168.1.1:8080")
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
