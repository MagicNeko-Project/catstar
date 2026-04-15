from filter_plugins import nginx

f = nginx.FilterModule()
print(list(f.parse_listen_ports("1 2 3")))
print(list(f.parse_listen_ports("1 2 3")))
