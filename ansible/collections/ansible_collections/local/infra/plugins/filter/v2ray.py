"""V2Ray configuration generator filter plugin."""

from typing import Any, Dict, List, Optional


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
        "tag": inbound_spec.get("tag") or f"inbound-vmess-{inbound_spec['vmess']}",
        "settings": {"clients": inbound_spec.get("clients", [])},
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_vless_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a VLESS inbound configuration block."""
    return {
        "protocol": "vless",
        "port": inbound_spec["vless"],
        "listen": inbound_spec.get("listen", "127.0.0.1"),
        "tag": inbound_spec.get("tag") or f"inbound-vless-{inbound_spec['vless']}",
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
        "tag": inbound_spec.get("tag") or f"inbound-ss-{inbound_spec['ss']}",
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
        "tag": inbound_spec.get("tag") or f"inbound-socks-{inbound_spec['socks']}",
        "settings": {"auth": "noauth"},
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_http_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a standard HTTP inbound configuration block."""
    return {
        "protocol": "http",
        "port": inbound_spec["http"],
        "listen": inbound_spec.get("listen", "127.0.0.1"),
        "tag": inbound_spec.get("tag") or f"inbound-http-{inbound_spec['http']}",
        "settings": {"auth": "noauth"},
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_tcp_relay_inbound(port: int, destination: str) -> Dict[str, Any]:
    """Build a dokodemo-door inbound configuration block for TCP relay."""
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
        "tag": inbound_spec.get("tag") or f"inbound-tg-{inbound_spec['tg']}",
        "settings": settings,
    }


def build_dokodemo_inbound(inbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a general dokodemo-door inbound configuration block."""
    settings: Dict[str, Any] = {}
    if "address" in inbound_spec:
        settings["address"] = inbound_spec["address"]
    if "port_dest" in inbound_spec:
        settings["port"] = inbound_spec["port_dest"]
    elif "destination_port" in inbound_spec:
        settings["port"] = inbound_spec["destination_port"]

    for key in ["network", "timeout", "followRedirect", "userLevel"]:
        if key in inbound_spec:
            settings[key] = inbound_spec[key]
        elif key == "followRedirect" and "follow_redirect" in inbound_spec:
            settings["followRedirect"] = inbound_spec["follow_redirect"]

    return {
        "protocol": "dokodemo-door",
        "port": inbound_spec["dokodemo"],
        "listen": inbound_spec.get("listen", "127.0.0.1"),
        "tag": inbound_spec.get("tag")
        or f"inbound-dokodemo-{inbound_spec['dokodemo']}",
        "settings": settings,
        "streamSettings": inbound_spec.get("stream_settings", {}),
    }


def build_vless_outbound(outbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a VLESS outbound configuration block."""
    user: Dict[str, Any] = {
        "id": outbound_spec.get("uuid") or outbound_spec.get("id"),
        "encryption": outbound_spec.get("encryption", "none"),
    }
    if "flow" in outbound_spec:
        user["flow"] = outbound_spec["flow"]

    vnext_item = {
        "address": outbound_spec["vless"],
        "port": outbound_spec.get("port", 443),
        "users": [user],
    }

    settings = {
        "vnext": [vnext_item],
    }

    outbound: Dict[str, Any] = {
        "protocol": "vless",
        "tag": outbound_spec.get("tag")
        or f"outbound-vless-{outbound_spec['vless']}-{outbound_spec.get('port', 443)}",
        "settings": settings,
    }

    # Handle streamSettings
    stream_settings = outbound_spec.get("stream_settings")
    if stream_settings is not None:
        outbound["streamSettings"] = stream_settings
    else:
        # Construct streamSettings dynamically from top-level keys if present
        dynamic_stream_settings: Dict[str, Any] = {}
        network = outbound_spec.get("network")
        if network:
            dynamic_stream_settings["network"] = network
        security = outbound_spec.get("security")
        if security:
            dynamic_stream_settings["security"] = security

        ws_settings: Dict[str, Any] = {}
        if "path" in outbound_spec:
            ws_settings["path"] = outbound_spec["path"]
        if "headers" in outbound_spec:
            ws_settings["headers"] = outbound_spec["headers"]
        if ws_settings:
            dynamic_stream_settings["wsSettings"] = ws_settings

        tls_settings: Dict[str, Any] = {}
        if "sni" in outbound_spec:
            tls_settings["serverName"] = outbound_spec["sni"]
        if "fingerprint" in outbound_spec:
            tls_settings["fingerprint"] = outbound_spec["fingerprint"]
        if tls_settings:
            dynamic_stream_settings["tlsSettings"] = tls_settings

        if dynamic_stream_settings:
            outbound["streamSettings"] = dynamic_stream_settings

    return outbound


def build_vmess_outbound(outbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a VMess outbound configuration block."""
    user: Dict[str, Any] = {
        "id": outbound_spec.get("uuid") or outbound_spec.get("id"),
        "alterId": outbound_spec.get("alter_id", outbound_spec.get("alterId", 0)),
    }
    if "security" in outbound_spec:
        user["security"] = outbound_spec["security"]

    vnext_item = {
        "address": outbound_spec["vmess"],
        "port": outbound_spec.get("port", 443),
        "users": [user],
    }

    settings = {
        "vnext": [vnext_item],
    }

    outbound: Dict[str, Any] = {
        "protocol": "vmess",
        "tag": outbound_spec.get("tag")
        or f"outbound-vmess-{outbound_spec['vmess']}-{outbound_spec.get('port', 443)}",
        "settings": settings,
    }

    # Handle streamSettings
    stream_settings = outbound_spec.get("stream_settings")
    if stream_settings is not None:
        outbound["streamSettings"] = stream_settings
    else:
        # Construct streamSettings dynamically from top-level keys if present
        dynamic_stream_settings: Dict[str, Any] = {}
        network = outbound_spec.get("network")
        if network:
            dynamic_stream_settings["network"] = network
        security = outbound_spec.get("security_stream") or outbound_spec.get(
            "stream_security"
        )
        if security:
            dynamic_stream_settings["security"] = security

        ws_settings: Dict[str, Any] = {}
        if "path" in outbound_spec:
            ws_settings["path"] = outbound_spec["path"]
        if "headers" in outbound_spec:
            ws_settings["headers"] = outbound_spec["headers"]
        if ws_settings:
            dynamic_stream_settings["wsSettings"] = ws_settings

        tls_settings: Dict[str, Any] = {}
        if "sni" in outbound_spec:
            tls_settings["serverName"] = outbound_spec["sni"]
        if tls_settings:
            dynamic_stream_settings["tlsSettings"] = tls_settings

        if dynamic_stream_settings:
            outbound["streamSettings"] = dynamic_stream_settings

    return outbound


def build_shadowsocks_outbound(outbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Shadowsocks outbound configuration block."""
    server = {
        "address": outbound_spec["ss"],
        "port": outbound_spec.get("port"),
        "method": outbound_spec.get("method", "aes-256-gcm"),
        "password": outbound_spec.get("password", ""),
    }
    return {
        "protocol": "shadowsocks",
        "tag": outbound_spec.get("tag")
        or f"outbound-ss-{outbound_spec['ss']}-{outbound_spec.get('port')}",
        "settings": {"servers": [server]},
        "streamSettings": outbound_spec.get("stream_settings", {}),
    }


def build_trojan_outbound(outbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Trojan outbound configuration block."""
    server = {
        "address": outbound_spec["trojan"],
        "port": outbound_spec.get("port", 443),
        "password": outbound_spec.get("password", ""),
    }
    return {
        "protocol": "trojan",
        "tag": outbound_spec.get("tag")
        or f"outbound-trojan-{outbound_spec['trojan']}-{outbound_spec.get('port', 443)}",
        "settings": {"servers": [server]},
        "streamSettings": outbound_spec.get("stream_settings", {}),
    }


def build_socks_outbound(outbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a SOCKS outbound configuration block."""
    server: Dict[str, Any] = {
        "address": outbound_spec["socks"],
        "port": outbound_spec.get("port"),
    }
    users = []
    if "username" in outbound_spec and "password" in outbound_spec:
        users.append(
            {
                "user": outbound_spec["username"],
                "pass": outbound_spec["password"],
            }
        )
    if users:
        server["users"] = users

    return {
        "protocol": "socks",
        "tag": outbound_spec.get("tag")
        or f"outbound-socks-{outbound_spec['socks']}-{outbound_spec.get('port')}",
        "settings": {"servers": [server]},
    }


def build_http_outbound(outbound_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build an HTTP outbound configuration block."""
    server: Dict[str, Any] = {
        "address": outbound_spec["http"],
        "port": outbound_spec.get("port"),
    }
    users = []
    if "username" in outbound_spec and "password" in outbound_spec:
        users.append(
            {
                "user": outbound_spec["username"],
                "pass": outbound_spec["password"],
            }
        )
    if users:
        server["users"] = users

    return {
        "protocol": "http",
        "tag": outbound_spec.get("tag")
        or f"outbound-http-{outbound_spec['http']}-{outbound_spec.get('port')}",
        "settings": {"servers": [server]},
    }


class V2RayConfigBuilder:
    """Builder class orchestrating the V2Ray configuration generation."""

    def __init__(
        self,
        inbounds: List[Dict[str, Any]],
        outbounds_default: List[Dict[str, Any]],
        outbounds_custom: List[Dict[str, Any]],
        rules_default: List[Dict[str, Any]],
        ads_domains: List[str],
        telegram_ips: List[str],
        rules_custom: List[Dict[str, Any]],
        routing_strategy: str = "",
        dns_servers: Optional[List[str]] = None,
        policy: Optional[Dict[str, Any]] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._inbound_specs = force_list(inbounds)
        self._outbounds_default_specs = force_list(outbounds_default)
        self._outbounds_custom_specs = force_list(outbounds_custom)
        self._rules_default_specs = force_list(rules_default)
        self._ads_domains = force_list(ads_domains)
        self._telegram_ips = force_list(telegram_ips)
        self._rules_custom_specs = force_list(rules_custom)
        self._routing_strategy = routing_strategy
        self._dns_servers = dns_servers
        self._policy = policy
        self._extra_config = extra_config or {}

        # Shared builder state accumulated during construction
        self._tcp_relay_tags: List[str] = []
        self._telegram_tag = "inbound-tg"

    def build(self) -> Dict[str, Any]:
        """Orchestrate configuration segments to generate a final dictionary."""
        inbounds = self._build_inbounds()
        outbounds = self._build_outbounds()
        routing = self._build_routing()

        config: Dict[str, Any] = {
            "log": {"loglevel": "info"},
            "inbounds": inbounds,
            "outbounds": outbounds,
            "transport": {
                "tcpSettings": {
                    "header": {"type": "none"},
                }
            },
            "routing": routing,
        }

        if self._dns_servers:
            config["dns"] = {"servers": self._dns_servers}
        if self._policy:
            config["policy"] = self._policy

        self._merge_extra_config(config)

        return config

    def _build_inbounds(self) -> List[Dict[str, Any]]:
        blocks = []
        for spec in self._inbound_specs:
            blocks.extend(self._process_single_inbound(spec))
        return blocks

    def _process_single_inbound(self, inbound_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            block = build_telegram_inbound(inbound_spec)
            self._telegram_tag = block["tag"]
            return [block]
        if "dokodemo" in inbound_spec:
            return [build_dokodemo_inbound(inbound_spec)]

        if "tcp" in inbound_spec:
            blocks: List[Dict[str, Any]] = []
            tcp_mapping = inbound_spec["tcp"]
            if isinstance(tcp_mapping, dict):
                for port_str, dest_str in tcp_mapping.items():
                    port = int(port_str)
                    blocks.append(build_tcp_relay_inbound(port, dest_str))
                    self._tcp_relay_tags.append(f"tcp_relay_{port}")
            return blocks

        # Fallback for raw configuration blocks
        if isinstance(inbound_spec, dict) and "tag" not in inbound_spec:
            protocol = inbound_spec.get("protocol", "unknown")
            port = inbound_spec.get("port", "unknown")
            inbound_spec = dict(inbound_spec)
            inbound_spec["tag"] = f"inbound-{protocol}-{port}"
        return [inbound_spec]

    def _build_outbounds(self) -> List[Dict[str, Any]]:
        blocks = []
        for spec in self._outbounds_default_specs + self._outbounds_custom_specs:
            blocks.extend(self._process_single_outbound(spec))
        return blocks

    def _process_single_outbound(self, outbound_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        if "vless" in outbound_spec:
            return [build_vless_outbound(outbound_spec)]
        if "vmess" in outbound_spec:
            return [build_vmess_outbound(outbound_spec)]
        if "ss" in outbound_spec:
            return [build_shadowsocks_outbound(outbound_spec)]
        if "trojan" in outbound_spec:
            return [build_trojan_outbound(outbound_spec)]
        if "socks" in outbound_spec:
            return [build_socks_outbound(outbound_spec)]
        if "http" in outbound_spec:
            return [build_http_outbound(outbound_spec)]

        # Fallback for raw configuration blocks
        if isinstance(outbound_spec, dict) and "tag" not in outbound_spec:
            protocol = outbound_spec.get("protocol", "unknown")
            outbound_spec = dict(outbound_spec)
            outbound_spec["tag"] = f"outbound-{protocol}"
        return [outbound_spec]

    def _build_routing(self) -> Dict[str, Any]:
        rules = []

        # 1. TCP Relay routing rule
        if self._tcp_relay_tags:
            rules.append(
                {
                    "type": "field",
                    "inboundTag": list(self._tcp_relay_tags),
                    "outboundTag": "direct",
                }
            )

        # 2. Default routing rules
        for rule_spec in self._rules_default_specs:
            rule = {"type": "field"}
            rule.update(rule_spec)
            rules.append(rule)

        # 3. Ad blocking rules
        if self._ads_domains:
            ad_rules = [f"domain:{domain}" for domain in self._ads_domains]
            rules.append(
                {
                    "type": "field",
                    "domain": ad_rules,
                    "outboundTag": "blocked",
                }
            )

        # 4. Telegram IP/Routing rules
        if self._telegram_ips:
            rules.append(
                {
                    "type": "field",
                    "ip": list(self._telegram_ips),
                    "inboundTag": [self._telegram_tag],
                    "outboundTag": "direct",
                }
            )
            rules.append(
                {
                    "type": "field",
                    "inboundTag": [self._telegram_tag],
                    "outboundTag": "blocked",
                }
            )

        # 5. Custom routing rules
        for rule_spec in self._rules_custom_specs:
            rule = {"type": "field"}
            rule.update(rule_spec)
            rules.append(rule)

        routing: Dict[str, Any] = {"rules": rules}
        if self._routing_strategy:
            routing["domainStrategy"] = self._routing_strategy
        return routing

    def _merge_extra_config(self, config: Dict[str, Any]) -> None:
        for key, value in self._extra_config.items():
            if key == "routing" and isinstance(value, dict) and "routing" in config:
                config["routing"].update(value)
            elif key == "log" and isinstance(value, dict) and "log" in config:
                config["log"].update(value)
            else:
                config[key] = value


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
        routing_strategy: str = "",
        dns_servers: Optional[List[str]] = None,
        policy: Optional[Dict[str, Any]] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a complete V2Ray configuration dictionary."""
        builder = V2RayConfigBuilder(
            inbounds=inbounds,
            outbounds_default=outbounds_default,
            outbounds_custom=outbounds_custom,
            rules_default=rules_default,
            ads_domains=ads_domains,
            telegram_ips=telegram_ips,
            rules_custom=rules_custom,
            routing_strategy=routing_strategy,
            dns_servers=dns_servers,
            policy=policy,
            extra_config=extra_config,
        )
        return builder.build()
