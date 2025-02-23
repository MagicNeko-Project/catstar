from dataclasses import dataclass, field, fields

from jinja2.runtime import Undefined


def force_list(item):
    if isinstance(item, Undefined):
        return []
    if isinstance(item, list):
        return item
    return [item]


def dataclass_create(cls, data):
    """Create dataclass by filtering relevant attributes,
    and return extra attributes."""

    fields_ = set(field.name for field in fields(cls))
    relevant = {}
    extras = {}

    for name, value in data.items():
        if name in fields_:
            relevant[name] = value
        else:
            extras[name] = value

    obj = cls(**relevant)
    return obj, extras


HTTP_PORTS = [
    *range(80, 90),
    *range(8000, 8010),
    *range(8080, 8090)
]


class ListenPort:
    def __init__(self, port=0, ssl=True, v6=True, h2=True, full=None):
        self.port = port
        self.ssl = ssl
        self.v6 = v6
        self.h2 = h2
        self.full = full

    def __str__(self):
        if self.full:
            return self.full
        result = str(self.port)
        if self.ssl:
            result += " ssl"
            if self.h2:
                result += " http2"
        if self.v6:
            result = "[::]:" + result
        return result

    def has_ssl(self):
        if self.full:
            return " ssl " in self.full
        return self.ssl


def parse_listen(data):
    for line in force_list(data):
        args = str(line).split()

        ssl = False
        plain = False
        v4 = False
        v6 = False
        dual = True
        ports = []
        full_listen = []

        for item in args:
            if item == "plain":
                plain = True
            elif item == "ssl":
                ssl = True
            elif item in ["ipv4", "v4"]:
                dual = False
                v4 = True
            elif item in ["ipv6", "v6"]:
                dual = False
                v6 = True
            elif item.isnumeric():
                ports.append(int(item))
            else:
                full_listen.append(item)

        for port in ports:
            default_ssl = not (port in HTTP_PORTS or port % 100 == 80)
            do_ssl = ssl or (not plain and default_ssl)
            if v4 or dual:
                yield ListenPort(port, do_ssl, False)
            if v6 or dual:
                yield ListenPort(port, do_ssl, True)
        for full in full_listen:
            yield ListenPort(full=full)


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
    server_name: str = "_"
    template: str = None
    ssl_host: str = None
    listen: str | int = None
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
            "gather_ssl_hosts": self.gather_ssl_hosts
        }

    def nginx_location_block(self, location_config):
        return [self._nginx_location(config)
                for config in force_list(location_config)]

    def nginx_server_block(self, server_config):
        return [self._nginx_server(config)
                for config in force_list(server_config)]

    def gather_ssl_hosts(self, sites_enabled_config):
        ssl_hosts = set()
        for server_config in sites_enabled_config.values():
            for site in self.nginx_server_block(server_config):
                ssl_hosts.add(site.ssl_host)
        return filter(None, ssl_hosts)

    def _nginx_location(self, location_block):
        block, extras = dataclass_create(NginxLocationBlock, location_block)
        block.options.update(extras)
        return block

    def _nginx_server(self, server_block):
        block, extras = dataclass_create(NginxServerBlock, server_block)
        if extras:
            block.locations.append(extras)

        if not block.listen:
            block.listen = 443
        block.listen = list(parse_listen(block.listen))

        need_ssl = any(port.has_ssl() for port in block.listen)
        if not block.ssl_host and need_ssl:
            block.ssl_host = '.'.join(
                block.server_name.split()[0].split('.')[-2:])

        return block

    def nginx_options(self, options):
        if isinstance(options, Undefined):
            return
        for name, value in options.items():
            for v in force_list(value):
                if v is True:
                    yield f"{name} on;"
                elif v is False:
                    yield f"{name} off;"
                elif name in ['if']:
                    yield f"{name} {v}"
                else:
                    yield f"{name} {v};"


if __name__ == "__main__":
    # Testing
    module = FilterModule()
    block = module.nginx_location_block({})
    for b in block:
        print(b)
    server = module.nginx_server_block([{
        "server_name": "a.test.c",
        "a": "b"
    }])
    for s in server:
        print(s)
