from filter_plugins import nginx

print(list(nginx.parse_listen_ports("1 2 3")))
print(list(nginx.parse_listen_ports("1 2 3")))
