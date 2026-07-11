#!/usr/bin/env python3
"""Prometheus metrics endpoint for the Anki sync server."""

import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_DIR = os.environ.get('SYNC_BASE', '/data')
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/backups')
STATE_DIR = os.environ.get('STATE_DIR', '/var/lib/anki')
PORT = int(os.environ.get('METRICS_PORT', 9090))
ANKI_VERSION = os.environ.get('ANKI_VERSION', 'unknown')
TLS_ENABLED = os.environ.get('TLS_ENABLED', 'false')
START_TIME = time.time()


def read_int(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return 0


_size_cache = {}


def dir_size(path, ttl=60):
    now = time.time()
    cached = _size_cache.get(path)
    if cached and now - cached[0] < ttl:
        return cached[1]
    total = 0
    try:
        for entry in Path(path).rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError:
        pass
    _size_cache[path] = (now, total)
    return total


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/metrics'):
            self.send_error(404)
            return
        backups = len(list(Path(BACKUP_DIR).glob('*.tar.gz'))) if os.path.isdir(BACKUP_DIR) else 0
        body = f"""# HELP anki_sync_users_total Total number of configured users
# TYPE anki_sync_users_total gauge
anki_sync_users_total {read_int(os.path.join(STATE_DIR, 'user_count.txt'))}

# HELP anki_sync_data_bytes Total data size in bytes
# TYPE anki_sync_data_bytes gauge
anki_sync_data_bytes {dir_size(DATA_DIR)}

# HELP anki_sync_backup_count Number of backup files
# TYPE anki_sync_backup_count gauge
anki_sync_backup_count {backups}

# HELP anki_sync_operations_total Completed sync operations since start
# TYPE anki_sync_operations_total counter
anki_sync_operations_total {read_int(os.path.join(STATE_DIR, 'sync_count.txt'))}

# HELP anki_sync_uptime_seconds Server uptime in seconds
# TYPE anki_sync_uptime_seconds counter
anki_sync_uptime_seconds {int(time.time() - START_TIME)}

# HELP anki_sync_info Server information
# TYPE anki_sync_info gauge
anki_sync_info{{version="{ANKI_VERSION}",tls="{TLS_ENABLED}"}} 1
""".encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', PORT), MetricsHandler).serve_forever()
