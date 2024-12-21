import multiprocessing

# Server socket settings
bind = "0.0.0.0:3003"
backlog = 2048

# Worker processes
workers = 2  # Use 2 workers to handle WebSocket connections
worker_class = "gevent"
worker_connections = 1000

# Timeout settings
timeout = 3600  # 1 hour timeout
graceful_timeout = 120
keepalive = 5

# Process naming
proc_name = "web-toolkit"
default_proc_name = "web-toolkit"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Development settings
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

# SSL (uncomment if using HTTPS)
# keyfile = "path/to/keyfile"
# certfile = "path/to/certfile" 