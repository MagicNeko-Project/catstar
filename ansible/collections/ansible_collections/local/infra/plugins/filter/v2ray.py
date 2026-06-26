"""V2Ray configuration generator filter plugin."""

from typing import Any, Dict, List


def force_list(item: Any) -> List[Any]:
    """Ensure the item is returned as a list."""
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def build_vmess_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a VMess inbound configuration block."""
    return {
        "protocol": "vmess",
        "port": inbound_spec["vmess"],
        "listen": inbound_spec.get("listen", "::"),
        "tag": inbound_spec.get("tag"),
        "settings": {"clients": inbound_spec.get("clients", [])},
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_vless_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a VLESS inbound configuration block."""
    return {
        "protocol": "vless",
        "port": inbound_spec["vless"],
        "listen": inbound_spec.get("listen", "127.0.0.1"),
        "tag": inbound_spec.get("tag"),
        "settings": {
            "clients": inbound_spec.get("clients", []),
            "decryption": "none",
        },
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_shadowsocks_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Shadowsocks inbound configuration block."""
    return {
        "protocol": "shadowsocks",
        "port": inbound_spec["ss"],
        "listen": inbound_spec.get("listen", "::"),
        "tag": inbound_spec.get("tag"),
        "settings": {
            "method": inbound_spec.get("method", "aes-256-gcm"),
            "password": inbound_spec.get("password", ""),
        },
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_socks_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a standard SOCKS inbound configuration block."""
    return {
        "protocol": "socks",
        "port": inbound_spec["socks"],
        "listen": inbound_spec.get("listen", "127.0.0.1"),
        "tag": inbound_spec.get("tag"),
        "settings": {"auth": "noauth"},
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_http_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a standard HTTP inbound configuration block."""
    return {
        "protocol": "http",
        "port": inbound_spec["http"],
        "listen": inbound_spec.get("listen", "127.0.0.1"),
        "tag": inbound_spec.get("tag"),
        "settings": {"auth": "noauth"},
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_dokodemo_inbound(port: int, destination: str) -> Dict[str, Any]:
    """Build a dokodemo-door inbound configuration block."""
    parts = destination.rsplit(":", 1)
    address = parts[0]
    dest_port = int(parts[1]) if len(parts) > 1 else 0

    return {
        "protocol": "dokodemo-door",
        "port": port,
        "listen": "::",
        "tag": f"tcp_relay_{port}",
        "settings": {
            "address": address,
            "port": dest_port,
            "network": "tcp",
        },
    }


def build_telegram_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a SOCKS inbound block configured for Telegram routing."""
    accounts = inbound_spec.get("accounts")
    settings: Dict[str, Any] = {}
    if accounts is not None:
        settings["auth"] = "password"
        settings["accounts"] = accounts
        default_listen = "::"
    else:
        settings["auth"] = "noauth"
        default_listen = "127.0.0.1"

    return {
        "protocol": "socks",
        "port": inbound_spec["tg"],
        "listen": inbound_spec.get("listen", default_listen),
        "tag": "inbound-tg",
        "settings": settings,
    }


def process_single_inbound(
    inbound_spec: Dict[str, Any], tcp_relay_tags: List[str]
) -> List[Dict[str, Any]]:
    """Process an inbound specification and return its corresponding block config list."""
    if "vmess" in inbound_spec:
        return [build_vmess_inbound(inbound_spec)]
    if "vless" in inbound_spec:
        return [build_vless_inbound(inbound_spec)]
    if "ss" in inbound_spec:
        return [build_shadowsocks_inbound(inbound_spec)]
    if "socks" in inbound_spec:
        return [build_socks_inbound(inbound_spec)]
    if "http" in inbound_spec:
        return [build_http_inbound(inbound_spec)]
    if "tg" in inbound_spec:
        return [build_telegram_inbound(inbound_spec)]

    if "tcp" in inbound_spec:
        blocks: List[Dict[str, Any]] = []
        tcp_mapping = inbound_spec["tcp"]
        if isinstance(tcp_mapping, dict):
            for port_str, dest_str in tcp_mapping.items():
                port = int(port_str)
                blocks.append(build_dokodemo_inbound(port, dest_str))
                tcp_relay_tags.append(f"tcp_relay_{port}")
        return blocks

    # Fallback for raw configuration blocks
    return [inbound_spec]


def build_routing_rules(
    tcp_relay_tags: List[str],
    rules_default: List[Dict[str, Any]],
    ads_domains: List[str],
    telegram_ips: List[str],
    rules_custom: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Construct the list of V2Ray routing rules."""
    rules: List[Dict[str, Any]] = []

    # 1. TCP Relay routing rule
    if tcp_relay_tags:
        rules.append(
            {
                "type": "field",
                "inboundTag": list(tcp_relay_tags),
                "outboundTag": "direct",
            }
        )

    # 2. Default routing rules
    for rule in rules_default:
        merged_rule = {"type": "field"}
        merged_rule.update(rule)
        rules.append(merged_rule)

    # 3. Ad blocking rules
    if ads_domains:
        ad_rules = [f"domain:{domain}" for domain in ads_domains]
        rules.append(
            {
                "type": "field",
                "domain": ad_rules,
                "outboundTag": "blocked",
            }
        )

    # 4. Telegram IP/Routing rules
    if telegram_ips:
        rules.append(
            {
                "type": "field",
                "ip": list(telegram_ips),
                "inboundTag": ["inbound-tg"],
                "outboundTag": "direct",
            }
        )
        rules.append(
            {
                "type": "field",
                "inboundTag": ["inbound-tg"],
                "outboundTag": "blocked",
            }
        )

    # 5. Custom routing rules
    for rule in rules_custom:
        merged_rule = {"type": "field"}
        merged_rule.update(rule)
        rules.append(merged_rule)

    return rules


class FilterModule:
    """Ansible filter plugin for building V2Ray configurations."""

    def filters(self) -> Dict[str, Any]:
        """Return the dictionary of filters defined by this module."""
        return {"v2ray_config": self.v2ray_config}

    def v2ray_config(
        self,
        inbounds: List[Dict[str, Any]],
        outbounds_default: List[Dict[str, Any]],
        outbounds_custom: List[Dict[str, Any]],
        rules_default: List[Dict[str, Any]],
        ads_domains: List[str],
        telegram_ips: List[str],
        rules_custom: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a complete V2Ray configuration dictionary."""
        tcp_relay_tags: List[str] = []

        # Construct inbounds
        inbound_blocks: List[Dict[str, Any]] = []
        for inbound in force_list(inbounds):
            inbound_blocks.extend(process_single_inbound(inbound, tcp_relay_tags))

        # Construct outbounds
        outbound_blocks: List[Dict[str, Any]] = []
        outbound_blocks.extend(force_list(outbounds_default))
        outbound_blocks.extend(force_list(outbounds_custom))

        # Construct routing rules
        routing_rules = build_routing_rules(
            tcp_relay_tags=tcp_relay_tags,
            rules_default=force_list(rules_default),
            ads_domains=force_list(ads_domains),
            telegram_ips=force_list(telegram_ips),
            rules_custom=force_list(rules_custom),
        )

        return {
            "log": {"loglevel": "info"},
            "inbounds": inbound_blocks,
            "outbounds": outbound_blocks,
            "transport": {
                "tcpSettings": {
                    "header": {"type": "none"},
                }
            },
            "routing": {"rules": routing_rules},
        }
