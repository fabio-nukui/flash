# flake8: noqa
c.ExtensionApp.open_browser = False
c.ServerApp.allow_origin = '*'
c.ServerApp.allow_password_change = False
c.ServerApp.certfile = '/home/flash/work/docker/jupyter-server.pem'
c.ServerApp.ip = '*'
c.ServerApp.keyfile = '/home/flash/work/docker/jupyter-server.key'
c.ServerApp.password = 'argon2:$argon2id$v=19$m=10240,t=10,p=8$1GnzWJ6NTZPmQXkDt3rO2A$JaSJFBZh+NXWbIDp3ApD+g'
