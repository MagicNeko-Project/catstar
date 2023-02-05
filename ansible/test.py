from filter_plugins import nginx

f = nginx.FilterModule()
print(f.nginx_listen("1 2 3"))
print(f.nginx_listen("1 2 3"))
