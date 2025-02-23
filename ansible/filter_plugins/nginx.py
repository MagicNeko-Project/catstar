from dataclasses import dataclass, field, fields
from jinja2.runtime import Undefined


def force_list(item):
    """Ensure the item is a list."""
    if isinstance(item, Undefined):
        return []
    return item if isinstance(item, list) else [item]


def dataclass_from_dict(cls, data):
    """Create a dataclass instance from a dictionary, separating extra attributes."""
    field_names = {f.name for f in fields(cls)}
    relevant = {k: v for k, v in data.items() if k in field_names}
    extras = {k: v for k, v in data.items() if k not in field_names}
    return cls(**relevant), extras


HTTP_PORTS = set(range(80, 90)) | set(range(8000, 8010)) | set(range(8080, 8090)) | set(range(80, 65536, 100))


@dataclass
class ListenPort:
    port: int = 0
    ssl: bool = True
    v6: bool = True
    h2: bool = True
    full: str = None

    def __str__(self):
        if self.full:
            return self.full
        result = f"[::]:{self.port}" if self.v6 else str(self.port)
        if self.ssl:
            result += " ssl"
            if self.h2:
                result += " http2"
        return result

    def has_ssl(self) -> bool:
        return " ssl" in self.full if self.full else self.ssl


def parse_listen_ports(data):
    """Parse listen directives from a configuration input."""
    for line in force_list(data):
        args = str(line).split()
        force_ssl, force_http, v4, v6, dual = False, False, False, False, True
        ports = []

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
                yield ListenPort(full=arg)

        for port in ports:
            ssl = force_ssl or (port not in HTTP_PORTS and not force_http)
            if v4 or dual:
                yield ListenPort(port, ssl, v6=False)
            if v6 or dual:
                yield ListenPort(port, ssl, v6=True)


@dataclass
class NginxLocationBlock:
    location: str = "/"
    proxy: str = ""
    auth_basic: str = None
    static: str = None
    snippets: str = ""
    php_fpm: str = None
    options: dict[str, str | list[str]] = field(default_factory=dict)


@dataclass
class NginxServerBlock:
    server_name: str = None
    template: str = None
    ssl_host: str = None
    listen: str | int = None  # Space-separated string, or a single number.
    locations: list[dict] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    options_global: dict[str, str] = field(default_factory=dict)
    blocked_location: str = r"~ /\.(?!well-known\/|file).*"


class FilterModule:
    def filters(self):
        return {
            "nginx_location_block": self.nginx_location_block,
            "nginx_options": self.nginx_options,
            "nginx_server_block": self.nginx_server_block,
            "gather_ssl_hosts": self.gather_ssl_hosts,
        }

    def nginx_location_block(self, location_config):
        return [self._create_nginx_location(config) for config in force_list(location_config)]

    def nginx_server_block(self, server_config, name):
        return [self._create_nginx_server(config, name) for config in force_list(server_config)]

    def gather_ssl_hosts(self, sites_enabled_config):
        return [
            site.ssl_host for name, server in sites_enabled_config.items()
            for site in self.nginx_server_block(server, name)
        ]

    def _create_nginx_location(self, location_block):
        location_block, extras = dataclass_from_dict(NginxLocationBlock, location_block)
        # Merge all extras into options
        location_block.options.update(extras)
        return location_block

    def _create_nginx_server(self, server_block, name):
        server_block, extras = dataclass_from_dict(NginxServerBlock, server_block)

        # Treat the extras as a separate location block
        if extras:
            server_block.locations.append(extras)

        # Server name defaults to the name of the block
        if server_block.server_name is None:
            server_block.server_name = name

        server_block.listen = list(parse_listen_ports(server_block.listen or 443))

        if server_block.ssl_host is None:
            if any(port.has_ssl() for port in server_block.listen):
                server_block.ssl_host = '.'.join(server_block.server_name.split()[0].split('.')[-2:])

        return server_block

    def nginx_options(self, options):
        """Generate nginx options directives."""
        if isinstance(options, Undefined):
            return []

        formatted_options = []
        for name, values in options.items():
            for value in force_list(values):
                if value is True:
                    formatted_options.append(f"{name} on;")
                elif value is False:
                    formatted_options.append(f"{name} off;")
                elif name == 'if':
                    formatted_options.append(f"{name} {value}")
                else:
                    formatted_options.append(f"{name} {value};")

        return formatted_options


if __name__ == "__main__":
    # Example test cases
    module = FilterModule()
    print(module.nginx_location_block([{"location": "/app", "proxy": "http://backend"}]))
    print(module.nginx_server_block([{"server_name": "example.com", "locations": [{"location": "/", "proxy": "http://frontend"}]}], "default_name"))
    print(module.gather_ssl_hosts({
        "default": {},
        "c5.example.com": {},
        "c6.example.com": {
            "server_name": "c6.example.com"
        }
    }))
