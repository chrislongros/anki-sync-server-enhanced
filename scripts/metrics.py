#!/usr/bin/env python3
"""Prometheus metrics endpoint for the Anki sync server."""

import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_DIR = os.environ.get('SYNC_BASE', '/data')
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/backups')
LOG_DIR = os.environ.get('LOG_DIR', '/var/log/anki')
STATE_DIR = os.environ.get('STATE_DIR', '/var/lib/anki')
PORT = int(os.environ.get('METRICS_PORT', 9090))
ANKI_VERSION = os.environ.get('ANKI_VERSION', 'unknown')
TLS_ENABLED = os.environ.get('TLS_ENABLED', 'false')
START_TIME = time.time()

_size_cache = {}


def read_int(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return 0


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


_col_cache = {}


def collection_stats(db_path):
    """Cards/notes/decks/reviews; the server holds synced collections locked,
    so query a temp copy and cache by mtime"""
    import shutil
    import sqlite3
    import tempfile

    def query(conn):
        stats = {}
        stats['cards'] = conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]
        stats['notes'] = conn.execute('SELECT COUNT(*) FROM notes').fetchone()[0]
        for key, table in (('decks', 'decks'), ('reviews', 'revlog')):
            try:
                stats[key] = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            except sqlite3.Error:
                stats[key] = 0
        if not stats['decks']:
            # schema-11 collections keep decks as JSON in the col table
            try:
                import json
                stats['decks'] = len(json.loads(conn.execute('SELECT decks FROM col').fetchone()[0]))
            except Exception:
                pass
        return stats

    try:
        mtime = os.path.getmtime(db_path)
        cached = _col_cache.get(db_path)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=1)
            stats = query(conn)
            conn.close()
        except sqlite3.OperationalError:
            if os.path.getsize(db_path) >= 512 * 1024 * 1024:
                return None
            fd, tmp = tempfile.mkstemp(suffix='.anki2')
            os.close(fd)
            try:
                shutil.copyfile(db_path, tmp)
                conn = sqlite3.connect(f'file:{tmp}?mode=ro', uri=True)
                stats = query(conn)
                conn.close()
            finally:
                os.unlink(tmp)
        _col_cache[db_path] = (mtime, stats)
        return stats
    except Exception:
        return None


def tail(path, n=2000):
    try:
        out = subprocess.run(['tail', '-n', str(n), path],
                             capture_output=True, text=True, timeout=5).stdout
        return out.splitlines() if out else []
    except Exception:
        return []


def count_matches(path, needle):
    try:
        out = subprocess.run(['grep', '-c', needle, path],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out)
    except Exception:
        return 0


def get_users():
    try:
        return [u for u in Path(os.path.join(STATE_DIR, 'users.txt')).read_text().split() if u]
    except OSError:
        return []


def label(value):
    return value.replace('\\', '\\\\').replace('"', '\\"')


def build_metrics():
    lines = []

    def metric(name, help_text, mtype, samples):
        lines.append(f'# HELP {name} {help_text}')
        lines.append(f'# TYPE {name} {mtype}')
        lines.extend(samples)
        lines.append('')

    users = get_users()
    metric('anki_sync_users_total', 'Configured users', 'gauge',
           [f'anki_sync_users_total {len(users)}'])

    metric('anki_sync_data_bytes', 'Total sync data size in bytes', 'gauge',
           [f'anki_sync_data_bytes {dir_size(DATA_DIR)}'])

    metric('anki_sync_user_data_bytes', 'Per-user data size in bytes', 'gauge',
           [f'anki_sync_user_data_bytes{{user="{label(u)}"}} {dir_size(os.path.join(DATA_DIR, u))}'
            for u in users])

    col_bytes = {}
    media_bytes = {}
    media_files = {}
    col_stats = {}
    for u in users:
        udir = Path(DATA_DIR) / u
        col_bytes[u] = sum(f.stat().st_size for f in udir.glob('*.anki2') if f.is_file())
        mdir = udir / 'collection.media'
        media_bytes[u] = dir_size(str(mdir)) if mdir.is_dir() else 0
        try:
            media_files[u] = sum(1 for f in mdir.iterdir() if f.is_file()) if mdir.is_dir() else 0
        except OSError:
            media_files[u] = 0
        col = udir / 'collection.anki2'
        if col.is_file():
            stats = collection_stats(str(col))
            if stats:
                col_stats[u] = stats

    metric('anki_sync_collections_bytes', 'Total collection database size', 'gauge',
           [f'anki_sync_collections_bytes {sum(col_bytes.values())}'])
    metric('anki_sync_media_bytes', 'Total media size', 'gauge',
           [f'anki_sync_media_bytes {sum(media_bytes.values())}'])
    metric('anki_sync_user_collection_bytes', 'Per-user collection database size', 'gauge',
           [f'anki_sync_user_collection_bytes{{user="{label(u)}"}} {v}' for u, v in col_bytes.items()])
    metric('anki_sync_user_media_bytes', 'Per-user media size', 'gauge',
           [f'anki_sync_user_media_bytes{{user="{label(u)}"}} {v}' for u, v in media_bytes.items()])
    metric('anki_sync_media_files_total', 'Per-user media file count', 'gauge',
           [f'anki_sync_media_files_total{{user="{label(u)}"}} {v}' for u, v in media_files.items()])
    for key, help_text in (('cards', 'Cards in collection'), ('notes', 'Notes in collection'),
                           ('decks', 'Decks in collection'), ('reviews', 'Reviews logged')):
        metric(f'anki_sync_{key}_total', help_text, 'gauge',
               [f'anki_sync_{key}_total{{user="{label(u)}"}} {s[key]}' for u, s in col_stats.items()])

    backups = []
    if os.path.isdir(BACKUP_DIR):
        backups = sorted(Path(BACKUP_DIR).glob('anki_backup_*.tar.gz'),
                         key=lambda f: f.stat().st_mtime)
    samples = [f'anki_sync_backup_count {len(backups)}']
    metric('anki_sync_backup_count', 'Number of backup archives', 'gauge', samples)
    metric('anki_sync_backup_bytes', 'Total size of backup archives', 'gauge',
           [f'anki_sync_backup_bytes {sum(f.stat().st_size for f in backups)}'])
    metric('anki_sync_backup_last_timestamp_seconds', 'mtime of newest backup', 'gauge',
           [f'anki_sync_backup_last_timestamp_seconds {int(backups[-1].stat().st_mtime) if backups else 0}'])

    metric('anki_sync_operations_total', 'Completed collection syncs', 'counter',
           [f'anki_sync_operations_total {read_int(os.path.join(STATE_DIR, "sync_count.txt"))}'])

    auth_log = os.path.join(LOG_DIR, 'auth.log')
    metric('anki_sync_auth_success_total', 'Successful logins', 'counter',
           [f'anki_sync_auth_success_total {count_matches(auth_log, "AUTH_SUCCESS")}'])
    metric('anki_sync_auth_failed_total', 'Failed logins', 'counter',
           [f'anki_sync_auth_failed_total {count_matches(auth_log, "AUTH_FAILED")}'])

    vals = []
    for line in tail(os.path.join(LOG_DIR, 'latency.log')):
        m = re.search(r'ms=(\d+)', line)
        if m:
            vals.append(int(m.group(1)))
    vals.sort()
    if vals:
        avg = sum(vals) / len(vals)
        p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
        mx = vals[-1]
    else:
        avg = p95 = mx = 0
    metric('anki_sync_request_latency_ms', 'Authenticated request latency (recent window)', 'gauge',
           [f'anki_sync_request_latency_ms{{stat="avg"}} {avg:.1f}',
            f'anki_sync_request_latency_ms{{stat="p95"}} {p95}',
            f'anki_sync_request_latency_ms{{stat="max"}} {mx}'])

    devices = {}
    for line in tail(os.path.join(LOG_DIR, 'devices.log')):
        m = re.search(r'uid="([^"]*)" client="([^"]*)"', line)
        if m:
            devices.setdefault(m.group(1), set()).add(m.group(2))
    metric('anki_sync_devices_total', 'Distinct devices per user', 'gauge',
           [f'anki_sync_devices_total{{user="{label(u)}"}} {len(c)}'
            for u, c in devices.items()])

    metric('anki_sync_uptime_seconds', 'Metrics exporter uptime', 'counter',
           [f'anki_sync_uptime_seconds {int(time.time() - START_TIME)}'])

    metric('anki_sync_info', 'Server information', 'gauge',
           [f'anki_sync_info{{version="{label(ANKI_VERSION)}",tls="{label(TLS_ENABLED)}"}} 1'])

    return '\n'.join(lines).encode()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/metrics'):
            self.send_error(404)
            return
        body = build_metrics()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', PORT), MetricsHandler).serve_forever()
