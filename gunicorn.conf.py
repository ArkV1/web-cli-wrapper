import multiprocessing

bind = "0.0.0.0:3003"
backlog = 2048

##############################################################################
# We are using gevent to support real-time WebSocket connections with Flask-SocketIO.
# This enables asynchronous concurrency needed to keep long-lived connections open.
#
# Note:
#  - gevent monkey-patches Python's I/O, which commonly breaks `multiprocessing.Manager()`
#    on macOS (the dreaded "[Errno 35]" error).
#  - If you want CPU-heavy tasks with a Manager-based queue, you must avoid gevent
#    or use a file/Redis-based solution for progress updates.
##############################################################################
workers = 2
worker_class = "gevent"
worker_connections = 1000

# Timeout settings
timeout = 3600  # 1 hour
graceful_timeout = 120
keepalive = 5

# Process naming
proc_name = "web-toolkit"
default_proc_name = "web-toolkit"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Development auto-reload
reload = True
reload_engine = "auto"

# Process management
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# WebSocket settings
websocket_ping_interval = 25
websocket_ping_timeout = 60

# SSL (uncomment if using HTTPS)
# keyfile = "path/to/keyfile"
# certfile = "path/to/certfile"
