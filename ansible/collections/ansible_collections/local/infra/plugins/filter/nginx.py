from dataclasses import dataclass, field, fields
from typing import Any, TypeVar

from jinja2.runtime import Undefined

T = TypeVar("T")


def force_list(item: Any) -> list[Any]:
    """Ensure the item is a list."""
    if isinstance(item, Undefined):
        return []
    return item if isinstance(item, list) else [item]


def dataclass_from_dict(cls: type[T], data: dict[str, Any]) -> tuple[T, dict[str, Any]]:
    """Create a dataclass instance from a dictionary, separating extra attributes."""
    field_names = {f.name for f in fields(cls)}
    relevant = {k: v for k, v in data.items() if k in field_names}
    extras = {k: v for k, v in data.items() if k not in field_names}
    return cls(**relevant), extras


HTTP_PORTS: frozenset[int] = frozenset(
    set(range(80, 90))
    | set(range(8000, 8010))
    | set(range(8080, 8090))
    | set(range(80, 65536, 100))
)


@dataclass
class ListenPort:
    port: int = 0
    ssl: bool = True
    v6: bool = True
    full: str | None = None

    def __str__(self) -> str:
        if self.full:
            return self.full
        result = f"[::]:{self.port}" if self.v6 else str(self.port)
        if self.ssl:
            result += " ssl"
        return result

    def has_ssl(self) -> bool:
        return " ssl" in self.full if self.full else self.ssl


def parse_listen_ports(data: Any) -> list[ListenPort]:
    """Parse listen directives from a configuration input."""
    parsed_ports: list[ListenPort] = []
    for line in force_list(data):
        args = str(line).split()
        force_ssl, force_http, v4, v6, dual = False, False, False, False, True
        ports: list[int] = []

        for arg in args:
            if arg in ["plain", "http"]:
                force_http = True
            elif arg == "ssl":
                force_ssl = True
            elif arg in ["ipv4", "v4"]:
                v4, dual = True, False
            elif arg in ["ipv6", "v6"]:
                v6, dual = True, False
            elif arg.isnumeric():
                ports.append(int(arg))
            else:
                parsed_ports.append(ListenPort(full=arg))

        for port in ports:
            ssl = force_ssl or (port not in HTTP_PORTS and not force_http)
            if v4 or dual:
                parsed_ports.append(ListenPort(port, ssl, v6=False))
            if v6 or dual:
                parsed_ports.append(ListenPort(port, ssl, v6=True))

    return parsed_ports


@dataclass
class NginxLocationBlock:
    location: str = "/"
    proxy: str = ""
    auth_basic: str | None = None
    static: str | None = None
    snippets: str = ""
    php_fpm: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class NginxServerBlock:
    server_name: str | None = None
    template: str | None = None
    ssl_host: str | None = None
    listen: Any = None
    http2: bool | None = None
    locations: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    options_global: dict[str, Any] = field(default_factory=dict)
    blocked_location: str = r"~ /\.(?!well-known\/|file).*"


class FilterModule:
    def filters(self) -> dict[str, Any]:
        return {
            "nginx_location_block": self.nginx_location_block,
            "nginx_options": self.nginx_options,
            "nginx_server_block": self.nginx_server_block,
            "gather_ssl_hosts": self.gather_ssl_hosts,
        }

    def nginx_location_block(self, location_config: Any) -> list[NginxLocationBlock]:
        return [
            self._create_nginx_location(config)
            for config in force_list(location_config)
        ]

    def nginx_server_block(
        self, server_config: Any, name: str
    ) -> list[NginxServerBlock]:
        return [
            self._create_nginx_server(config, name)
            for config in force_list(server_config)
        ]

    def gather_ssl_hosts(self, sites_enabled_config: dict[str, Any]) -> list[str]:
        return [
            site.ssl_host
            for name, server in sites_enabled_config.items()
            for site in self.nginx_server_block(server, name)
            if site.ssl_host is not None
        ]

    def _create_nginx_location(
        self, location_data: dict[str, Any]
    ) -> NginxLocationBlock:
        location_block, extras = dataclass_from_dict(NginxLocationBlock, location_data)
        location_block.options.update(extras)
        return location_block

    def _create_nginx_server(
        self, server_data: dict[str, Any], name: str
    ) -> NginxServerBlock:
        server_block, extras = dataclass_from_dict(NginxServerBlock, server_data)

        if extras:
            server_block.locations.append(extras)

        if server_block.server_name is None:
            server_block.server_name = name

        listen_ports = parse_listen_ports(server_block.listen or 443)
        server_block.listen = listen_ports
        has_ssl = server_block.template != "default" and any(
            port.has_ssl() for port in listen_ports
        )

        if server_block.http2 is None:
            server_block.http2 = has_ssl

        if server_block.ssl_host is None and has_ssl:
            server_block.ssl_host = ".".join(
                server_block.server_name.split()[0].split(".")[-2:]
            )

        return server_block

    def nginx_options(self, options: Any) -> list[str]:
        """Generate nginx options directives."""
        if isinstance(options, Undefined):
            return []

        formatted_options: list[str] = []
        for name, values in options.items():
            for value in force_list(values):
                if value is True:
                    formatted_options.append(f"{name} on;")
                elif value is False:
                    formatted_options.append(f"{name} off;")
                elif name == "if":
                    formatted_options.append(f"{name} {value}")
                else:
                    formatted_options.append(f"{name} {value};")

        return formatted_options
