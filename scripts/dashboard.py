#!/usr/bin/env python3
"""
Anki Sync Server Enhanced Dashboard v2
Features: Dark/light mode, storage breakdown, collection details, container info, download backups
"""

import hmac
import os
import re
import subprocess
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, render_template_string, jsonify, request, Response, send_from_directory

app = Flask(__name__)

STATIC_DIR = os.environ.get('DASHBOARD_STATIC_DIR', '/usr/local/share/anki-dashboard')

# Configuration
DATA_DIR = os.environ.get('SYNC_BASE', '/data')
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/backups')
LOG_DIR = os.environ.get('LOG_DIR', '/var/log/anki')
STATE_DIR = os.environ.get('STATE_DIR', '/var/lib/anki')
DASHBOARD_AUTH = os.environ.get('DASHBOARD_AUTH', '')

def check_auth(username, password):
    if not DASHBOARD_AUTH:
        return True
    expected = DASHBOARD_AUTH.split(':', 1)
    if len(expected) != 2:
        return False  # malformed DASHBOARD_AUTH locks, never opens
    return (hmac.compare_digest(username, expected[0])
            & hmac.compare_digest(password, expected[1]))

def authenticate():
    return Response('Authentication required', 401,
                    {'WWW-Authenticate': 'Basic realm="Anki Dashboard"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_AUTH:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

_dir_size_cache = {}

def get_dir_size(path, ttl=60):
    # the 10s poll shouldn't rescan all media every time
    now = time.time()
    cached = _dir_size_cache.get(path)
    if cached and now - cached[0] < ttl:
        return cached[1]
    total = 0
    try:
        for entry in Path(path).rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception:
        pass
    _dir_size_cache[path] = (now, total)
    return total

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}" if size != int(size) else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

def format_duration(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
    else:
        return f"{int(seconds // 86400)}d {int((seconds % 86400) // 3600)}h"

def read_file_safe(path, default=''):
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except Exception:
        return default

def read_log_lines(path, lines=100):
    try:
        result = subprocess.run(['tail', '-n', str(lines), path],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip().split('\n') if result.stdout else []
    except Exception:
        return []

def get_users():
    users_file = os.path.join(STATE_DIR, 'users.txt')
    if os.path.exists(users_file):
        with open(users_file, 'r') as f:
            content = f.read().strip()
        if not content:
            return []
        users = []
        for line in content.split('\n'):
            # Handle both one-per-line and comma-separated formats
            for user in line.split(','):
                user = user.strip()
                if user:
                    users.append(user)
        return users
    return []

def get_collection_info(db_path):
    """Get card count from Anki collection database"""
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cards")
        cards = cursor.fetchone()[0]
        conn.close()
        return {'cards': cards}
    except Exception:
        return {'cards': 0}

def get_user_details():
    """Get detailed user statistics including collection info"""
    users = get_users()
    details = []
    for user in users:
        user_dir = os.path.join(DATA_DIR, user)
        if not os.path.exists(user_dir):
            continue
        
        total_size = get_dir_size(user_dir)
        collections = []
        
        for db_file in Path(user_dir).glob('**/*.anki2'):
            size = db_file.stat().st_size
            info = get_collection_info(str(db_file))
            try:
                mtime = datetime.fromtimestamp(db_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            except Exception:
                mtime = 'Unknown'
            collections.append({
                'name': db_file.name,
                'size': size,
                'size_formatted': format_bytes(size),
                'cards': info['cards'],
                'modified': mtime,
                'type': 'database'
            })
        
        media_dir = os.path.join(user_dir, 'collection.media')
        if os.path.exists(media_dir):
            media_size = get_dir_size(media_dir)
            try:
                media_files = len([f for f in os.listdir(media_dir) if os.path.isfile(os.path.join(media_dir, f))])
            except Exception:
                media_files = 0
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(media_dir)).strftime('%Y-%m-%d %H:%M')
            except Exception:
                mtime = 'Unknown'
            collections.append({
                'name': 'collection.media',
                'size': media_size,
                'size_formatted': format_bytes(media_size),
                'files': media_files,
                'modified': mtime,
                'type': 'media'
            })
        
        try:
            last_sync = datetime.fromtimestamp(os.path.getmtime(user_dir)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            last_sync = 'Unknown'
        
        details.append({
            'username': user,
            'total_size': total_size,
            'total_size_formatted': format_bytes(total_size),
            'last_sync': last_sync,
            'collections': collections
        })
    
    return details

def get_storage_breakdown():
    """Get storage breakdown by category"""
    collections_size = 0
    media_size = 0
    
    for user in get_users():
        user_dir = os.path.join(DATA_DIR, user)
        if os.path.exists(user_dir):
            for db_file in Path(user_dir).glob('**/*.anki2'):
                collections_size += db_file.stat().st_size
            media_dir = os.path.join(user_dir, 'collection.media')
            if os.path.exists(media_dir):
                media_size += get_dir_size(media_dir)
    
    backups_size = get_dir_size(BACKUP_DIR) if os.path.exists(BACKUP_DIR) else 0
    logs_size = get_dir_size(LOG_DIR) if os.path.exists(LOG_DIR) else 0
    
    return {
        'collections': collections_size,
        'collections_formatted': format_bytes(collections_size),
        'media': media_size,
        'media_formatted': format_bytes(media_size),
        'backups': backups_size,
        'backups_formatted': format_bytes(backups_size),
        'logs': logs_size,
        'logs_formatted': format_bytes(logs_size),
        'total': collections_size + media_size + backups_size + logs_size,
        'total_formatted': format_bytes(collections_size + media_size + backups_size + logs_size)
    }

def get_container_info():
    """Get Docker container information"""
    info = {
        'container_id': 'N/A',
        'image_name': 'anki-sync-server',
        'restarts': 0
    }
    
    try:
        with open('/proc/self/cgroup', 'r') as f:
            for line in f:
                if 'docker' in line or 'containerd' in line:
                    parts = line.strip().split('/')
                    if parts:
                        cid = parts[-1]
                        if len(cid) >= 12:
                            info['container_id'] = cid[:12]
                    break
    except Exception:
        pass
    
    if info['container_id'] == 'N/A':
        try:
            info['container_id'] = os.environ.get('HOSTNAME', 'unknown')[:12]
        except Exception:
            pass
    
    return info

def get_backups():
    backups = []
    if os.path.exists(BACKUP_DIR):
        files = sorted(Path(BACKUP_DIR).glob('*.tar.gz'),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[:20]:
            stat = f.stat()
            backups.append({
                'name': f.name,
                'kind': 'safety' if f.name.startswith('pre_restore_') else 'scheduled',
                'size': stat.st_size,
                'size_formatted': format_bytes(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
            })
    return backups

def get_auth_stats():
    lines = read_log_lines(os.path.join(LOG_DIR, 'auth.log'), 1000)
    success = sum(1 for l in lines if 'SUCCESS' in l)
    failed = sum(1 for l in lines if 'FAILED' in l or 'FAILURE' in l)
    return {'success': success, 'failed': failed}

def get_sync_chart_data():
    # [2026-07-11 15:04:05] SYNC_COMPLETE uid="user"
    lines = read_log_lines(os.path.join(LOG_DIR, 'sync.log'), 5000)
    daily = {(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'): 0 for i in range(7)}
    for line in lines:
        if 'SYNC_COMPLETE' in line or ('SYNC' in line and 'COMPLETE' in line):
            date = line[1:11]
            if date in daily:
                daily[date] += 1
    data = sorted(daily.items())
    return {'labels': [d[0] for d in data], 'values': [d[1] for d in data]}

def get_system_stats():
    stats = {'disk_total': 0, 'disk_used': 0, 'disk_percent': 0,
             'memory_total': 0, 'memory_used': 0, 'memory_percent': 0, 'load_avg': [0, 0, 0]}
    try:
        st = os.statvfs(DATA_DIR)
        stats['disk_total'] = st.f_frsize * st.f_blocks
        stats['disk_used'] = stats['disk_total'] - st.f_frsize * st.f_bavail
        stats['disk_percent'] = (stats['disk_used'] / stats['disk_total'] * 100) if stats['disk_total'] else 0
    except Exception: pass
    try:
        with open('/proc/meminfo') as f:
            mem = {l.split()[0].rstrip(':'): int(l.split()[1]) * 1024 for l in f if len(l.split()) >= 2}
        stats['memory_total'] = mem.get('MemTotal', 0)
        stats['memory_used'] = stats['memory_total'] - mem.get('MemAvailable', mem.get('MemFree', 0))
        stats['memory_percent'] = (stats['memory_used'] / stats['memory_total'] * 100) if stats['memory_total'] else 0
    except Exception: pass
    try:
        with open('/proc/loadavg') as f:
            p = f.read().split()
            stats['load_avg'] = [float(p[0]), float(p[1]), float(p[2])]
    except Exception: pass
    return stats

def get_recent_syncs():
    lines = read_log_lines(os.path.join(LOG_DIR, 'sync.log'), 200)
    syncs = []
    for line in reversed(lines):
        if 'SYNC_COMPLETE' in line or ('SYNC' in line and 'COMPLETE' in line):
            m = re.search(r'uid="([^"]*)"', line)
            user = m.group(1) if m else 'unknown'
            try:
                epoch = time.mktime(datetime.strptime(line[1:20], '%Y-%m-%d %H:%M:%S').timetuple())
            except Exception:
                epoch = None
            # collapse bursts: same user within a minute becomes one row
            if (syncs and syncs[-1]['user'] == user and epoch and syncs[-1]['epoch']
                    and syncs[-1]['epoch'] - epoch < 60):
                syncs[-1]['count'] += 1
                continue
            syncs.append({'time': line[1:20], 'epoch': epoch, 'user': user, 'count': 1})
            if len(syncs) >= 10:
                break
    return syncs

# API Routes
@app.route('/api/stats')
@requires_auth
def api_stats():
    start_time = float(read_file_safe(os.path.join(STATE_DIR, 'start_time.txt'), str(time.time())))
    users = get_users()
    auth = get_auth_stats()
    backup_count = len(list(Path(BACKUP_DIR).glob('*.tar.gz'))) if os.path.exists(BACKUP_DIR) else 0
    return jsonify({
        'version': read_file_safe(os.path.join(STATE_DIR, 'version.txt'), 'Unknown'),
        'uptime_formatted': format_duration(time.time() - start_time),
        'user_count': len(users),
        'data_size_formatted': format_bytes(get_dir_size(DATA_DIR)),
        'sync_count': int(read_file_safe(os.path.join(STATE_DIR, 'sync_count.txt'), '0')),
        'backup_count': backup_count,
        'auth_success': auth['success'],
        'auth_failed': auth['failed']
    })

@app.route('/api/users')
@requires_auth
def api_users():
    return jsonify(get_user_details())

@app.route('/api/storage')
@requires_auth
def api_storage():
    return jsonify(get_storage_breakdown())

@app.route('/api/container')
@requires_auth
def api_container():
    return jsonify(get_container_info())

@app.route('/api/backups')
@requires_auth
def api_backups():
    return jsonify(get_backups())

@app.route('/api/backups/create', methods=['POST'])
@requires_auth
def api_create_backup():
    try:
        result = subprocess.run(['/usr/local/bin/backup.sh'], capture_output=True, text=True, timeout=1800)
        return jsonify({'success': result.returncode == 0, 'message': 'Backup created' if result.returncode == 0 else result.stderr or 'Failed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/backups/download/<filename>')
@requires_auth
def api_download_backup(filename):
    if filename != os.path.basename(filename) or not filename.endswith('.tar.gz'):
        return jsonify({'error': 'Invalid filename'}), 400
    try:
        return send_from_directory(BACKUP_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/backups/delete/<filename>', methods=['POST'])
@requires_auth
def api_delete_backup(filename):
    if filename != os.path.basename(filename) or not filename.endswith('.tar.gz'):
        return jsonify({'error': 'Invalid filename'}), 400
    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    os.remove(filepath)
    return jsonify({'success': True})

_update_cache = {'ts': 0.0, 'latest': ''}

@app.route('/api/update')
@requires_auth
def api_update():
    import json as _json
    from urllib.request import urlopen, Request
    now = time.time()
    if now - _update_cache['ts'] > 21600:
        latest = ''
        try:
            req = Request('https://api.github.com/repos/ankitects/anki/releases/latest',
                          headers={'User-Agent': 'anki-sync-dashboard'})
            with urlopen(req, timeout=5) as r:
                latest = _json.load(r).get('tag_name', '')
        except Exception:
            pass
        _update_cache.update(ts=now, latest=latest)
    current = read_file_safe(os.path.join(STATE_DIR, 'version.txt'), '')
    latest = _update_cache['latest']
    return jsonify({'current': current, 'latest': latest,
                    'update_available': bool(latest) and bool(current) and latest != current})

@app.route('/static/<filename>')
def static_assets(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/api/notify/test', methods=['POST'])
@requires_auth
def api_test_notify():
    try:
        result = subprocess.run(['/usr/local/bin/notify.sh', 'Test notification from Anki Dashboard'],
                                capture_output=True, text=True, timeout=30)
        detail = (result.stdout or result.stderr or '').strip()
        ok = result.returncode == 0
        return jsonify({'success': ok, 'message': detail or ('Notification sent' if ok else 'Failed to send')})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logs/<log_type>')
@requires_auth
def api_logs(log_type):
    files = {'sync': 'sync.log', 'auth': 'auth.log', 'backup': 'backup.log', 'server': 'server.log'}
    if log_type not in files:
        return jsonify({'error': 'Invalid'}), 400
    return jsonify({'lines': read_log_lines(os.path.join(LOG_DIR, files[log_type]), int(request.args.get('lines', 100)))})

@app.route('/api/chart')
@requires_auth
def api_chart():
    return jsonify(get_sync_chart_data())

@app.route('/api/system')
@requires_auth
def api_system():
    s = get_system_stats()
    return jsonify({**s, 'disk_used_formatted': format_bytes(s['disk_used']), 'disk_total_formatted': format_bytes(s['disk_total']),
                    'memory_used_formatted': format_bytes(s['memory_used']), 'memory_total_formatted': format_bytes(s['memory_total'])})

@app.route('/api/features')
@requires_auth
def api_features():
    return jsonify({k: os.environ.get(v, 'false').lower() == 'true' for k, v in
                    [('TLS', 'TLS_ENABLED'), ('Backups', 'BACKUP_ENABLED'), ('S3 Upload', 'S3_BACKUP_ENABLED'), ('Metrics', 'METRICS_ENABLED'),
                     ('Fail2Ban', 'FAIL2BAN_ENABLED'), ('Notifications', 'NOTIFY_ENABLED'), ('Email', 'EMAIL_ENABLED')]})

@app.route('/api/syncs')
@requires_auth
def api_syncs():
    return jsonify(get_recent_syncs())

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

# Dashboard HTML
DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Anki Sync Server</title>
    <script src="/static/tailwind.js"></script>
    <script src="/static/chart.umd.js"></script>
</head>
<body class="min-h-screen p-6 bg-slate-900 text-slate-200" id="body">
    <div class="max-w-6xl mx-auto">
        <div class="flex justify-between items-center mb-8">
            <div class="flex items-center gap-3">
                <h1 class="text-3xl font-light"><span class="text-white">Anki</span> <span class="text-cyan-400">Sync Server</span></h1>
                <a id="update-badge" class="hidden px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-400 hover:bg-amber-500/30" href="https://github.com/ankitects/anki/releases/latest" target="_blank" rel="noopener"></a>
            </div>
            <button onclick="toggleTheme()" id="theme-btn" class="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition">☀️</button>
        </div>
        
        <div class="flex gap-2 mb-6 flex-wrap" id="tabs">
            <button onclick="showTab('overview')" class="tab-btn px-4 py-2 rounded-lg bg-blue-600 text-white">Overview</button>
            <button onclick="showTab('users')" class="tab-btn px-4 py-2 rounded-lg bg-slate-800 text-slate-400 hover:bg-slate-700">Users</button>
            <button onclick="showTab('backups')" class="tab-btn px-4 py-2 rounded-lg bg-slate-800 text-slate-400 hover:bg-slate-700">Backups</button>
            <button onclick="showTab('logs')" class="tab-btn px-4 py-2 rounded-lg bg-slate-800 text-slate-400 hover:bg-slate-700">Logs</button>
            <button onclick="showTab('system')" class="tab-btn px-4 py-2 rounded-lg bg-slate-800 text-slate-400 hover:bg-slate-700">System</button>
        </div>

        <!-- Overview -->
        <div id="tab-overview" class="tab-content">
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Server Status</div><div class="flex items-center gap-2 mb-1"><span class="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse"></span><span class="text-lg text-green-400">Online</span></div><div class="text-sm text-slate-500">Version: <span id="version">--</span></div><div class="text-sm text-slate-500">Uptime: <span id="uptime">--</span></div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Users</div><div class="text-4xl font-bold text-green-400" id="users">--</div><div class="text-sm text-slate-500 mt-1">Active users</div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Data Size</div><div class="text-4xl font-bold text-cyan-400" id="datasize">--</div><div class="text-sm text-slate-500 mt-1">Total sync data</div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Sync Operations</div><div class="text-4xl font-bold text-orange-400" id="syncs">--</div><div class="text-sm text-slate-500 mt-1">Since restart</div></div>
            </div>
            
            <div class="card bg-slate-800 rounded-xl p-5 mb-6">
                <div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Storage Breakdown</div>
                <div class="h-4 rounded-full overflow-hidden flex mb-4" id="storage-bar"></div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="storage-legend"></div>
            </div>
            
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Features</div><div id="features" class="space-y-2"></div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Backups</div><div class="text-4xl font-bold text-slate-300" id="backups">--</div><div class="text-sm text-slate-500 mt-1" id="backups-size">--</div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Auth Stats</div><div class="space-y-1 mt-2"><div>Success: <span class="text-green-400 font-semibold" id="auth-ok">0</span></div><div>Failed: <span class="text-red-400 font-semibold" id="auth-fail">0</span></div></div><button id="notify-btn" onclick="testNotify()" class="mt-4 w-full px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm transition text-white disabled:opacity-40 disabled:cursor-not-allowed">Test Notification</button></div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Sync Activity (7 Days)</div><canvas id="chart" height="180"></canvas></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Recent Syncs</div><div id="recent" class="space-y-2 max-h-52 overflow-auto"></div></div>
            </div>
        </div>

        <!-- Users -->
        <div id="tab-users" class="tab-content hidden">
            <div class="card bg-slate-800 rounded-xl p-5">
                <div class="flex justify-between mb-4"><span class="text-xs text-slate-500 uppercase">User Statistics</span><button onclick="loadUsers()" class="px-4 py-1.5 bg-blue-600 rounded-lg text-sm hover:bg-blue-700 text-white">Refresh</button></div>
                <div id="user-storage-chart" class="bg-slate-700/50 rounded-lg p-4 mb-4"></div>
                <div id="users-list" class="space-y-2"></div>
            </div>
        </div>

        <!-- Backups -->
        <div id="tab-backups" class="tab-content hidden">
            <div class="card bg-slate-800 rounded-xl p-5">
                <div class="flex justify-between mb-4"><span class="text-xs text-slate-500 uppercase">Backup Files</span><button id="bkbtn" onclick="createBackup()" class="px-4 py-1.5 bg-green-600 rounded-lg text-sm hover:bg-green-700 text-white">Create Backup</button></div>
                <div id="bkalert" class="hidden mb-4 p-3 rounded-lg text-sm"></div>
                <table class="w-full"><thead><tr class="text-left text-slate-500 text-xs border-b border-slate-700"><th class="pb-2">Filename</th><th class="pb-2">Size</th><th class="pb-2">Created</th><th class="pb-2 text-right">Actions</th></tr></thead><tbody id="bktbl"></tbody></table>
            </div>
        </div>

        <!-- Logs -->
        <div id="tab-logs" class="tab-content hidden">
            <div class="card bg-slate-800 rounded-xl p-5">
                <div class="flex justify-between mb-4 flex-wrap gap-2">
                    <div class="flex gap-2"><button onclick="loadLogs('sync')" class="logbtn px-4 py-1.5 bg-blue-600 rounded-lg text-sm text-white">Sync</button><button onclick="loadLogs('auth')" class="logbtn px-4 py-1.5 bg-slate-700 rounded-lg text-sm hover:bg-slate-600 text-slate-300">Auth</button><button onclick="loadLogs('backup')" class="logbtn px-4 py-1.5 bg-slate-700 rounded-lg text-sm hover:bg-slate-600 text-slate-300">Backup</button><button onclick="loadLogs('server')" class="logbtn px-4 py-1.5 bg-slate-700 rounded-lg text-sm hover:bg-slate-600 text-slate-300">Server</button></div>
                    <div class="flex gap-2 items-center">
                        <input id="logfilter" oninput="renderLogs()" placeholder="filter…" class="px-3 py-1.5 rounded-lg bg-slate-700 text-sm text-slate-200 w-40 placeholder-slate-500">
                        <label class="text-sm text-slate-400 flex items-center gap-1.5"><input type="checkbox" id="logfollow" checked> follow</label>
                        <button onclick="refreshLogs()" class="px-4 py-1.5 bg-blue-600 rounded-lg text-sm hover:bg-blue-700 text-white">Refresh</button>
                    </div>
                </div>
                <div id="logview" class="bg-slate-900 rounded-lg p-4 font-mono text-xs max-h-96 overflow-auto"></div>
            </div>
        </div>

        <!-- System -->
        <div id="tab-system" class="tab-content hidden">
            <div class="card bg-slate-800 rounded-xl p-5 mb-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Docker Container</div>
                <div class="grid grid-cols-2 md:grid-cols-3 gap-4" id="container-info"></div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Disk Usage</div><div class="flex justify-between text-sm mb-2"><span id="du">--</span><span id="dt">--</span></div><div class="h-2 bg-slate-700 rounded-full overflow-hidden"><div id="dp" class="h-full bg-blue-500 rounded-full" style="width:0"></div></div><div class="text-sm text-slate-500 mt-1"><span id="dpc">0</span>% used</div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Memory Usage</div><div class="flex justify-between text-sm mb-2"><span id="mu">--</span><span id="mt">--</span></div><div class="h-2 bg-slate-700 rounded-full overflow-hidden"><div id="mp" class="h-full bg-green-500 rounded-full" style="width:0"></div></div><div class="text-sm text-slate-500 mt-1"><span id="mpc">0</span>% used</div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Load Average</div><div class="grid grid-cols-3 gap-4 text-center mt-2"><div><div class="text-2xl font-bold text-blue-400" id="l1">--</div><div class="text-xs text-slate-500">1m</div></div><div><div class="text-2xl font-bold text-blue-400" id="l5">--</div><div class="text-xs text-slate-500">5m</div></div><div><div class="text-2xl font-bold text-blue-400" id="l15">--</div><div class="text-xs text-slate-500">15m</div></div></div></div>
                <div class="card bg-slate-800 rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Server Info</div><div class="space-y-2 text-sm"><div class="flex justify-between"><span class="text-slate-500">Version:</span><span id="sv">--</span></div><div class="flex justify-between"><span class="text-slate-500">Users:</span><span id="su">--</span></div><div class="flex justify-between"><span class="text-slate-500">Backups:</span><span id="sb">--</span></div></div></div>
            </div>
        </div>

        <footer class="text-center text-slate-600 text-sm mt-8">Anki Sync Server Enhanced | Auto-refresh: <span id="cd">10</span>s</footer>
    </div>
<script>
let logType='sync',chart,cd=10,darkMode=true,expandedUser=null;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function rel(epoch){const d=Date.now()/1000-epoch;if(d<60)return Math.max(0,Math.floor(d))+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';if(d<86400)return Math.floor(d/3600)+'h ago';return Math.floor(d/86400)+'d ago';}
const storageColors={collections:'#06b6d4',media:'#3b82f6',backups:'#a855f7',logs:'#64748b'};

document.addEventListener('DOMContentLoaded',()=>{initChart();if(localStorage.getItem('theme')==='light')toggleTheme();refreshAll();setInterval(()=>{if(document.hidden)return;cd--;document.getElementById('cd').textContent=cd;if(cd<=0){cd=10;refreshAll();}},1000);});
document.addEventListener('visibilitychange',()=>{if(!document.hidden){cd=10;refreshAll();}});

function toggleTheme(){
    darkMode=!darkMode;
    const body=document.getElementById('body');
    const btn=document.getElementById('theme-btn');
    if(darkMode){
        body.className='min-h-screen p-6 bg-slate-900 text-slate-200';
        btn.textContent='☀️';
        document.querySelectorAll('.card').forEach(c=>c.classList.replace('bg-white','bg-slate-800'));
        document.querySelectorAll('.tab-btn:not(.bg-blue-600)').forEach(b=>{b.classList.remove('bg-gray-200','text-gray-600');b.classList.add('bg-slate-800','text-slate-400');});
    }else{
        body.className='min-h-screen p-6 bg-gray-100 text-gray-800';
        btn.textContent='🌙';
        document.querySelectorAll('.card').forEach(c=>c.classList.replace('bg-slate-800','bg-white'));
        document.querySelectorAll('.tab-btn:not(.bg-blue-600)').forEach(b=>{b.classList.remove('bg-slate-800','text-slate-400');b.classList.add('bg-gray-200','text-gray-600');});
    }
    applyChartTheme();
    localStorage.setItem('theme',darkMode?'dark':'light');
}

function showTab(t){
    document.querySelectorAll('.tab-content').forEach(e=>e.classList.add('hidden'));
    document.getElementById('tab-'+t).classList.remove('hidden');
    document.querySelectorAll('.tab-btn').forEach(b=>{
        b.classList.remove('bg-blue-600','text-white');
        b.classList.add(darkMode?'bg-slate-800':'bg-gray-200',darkMode?'text-slate-400':'text-gray-600');
    });
    event.target.classList.remove(darkMode?'bg-slate-800':'bg-gray-200',darkMode?'text-slate-400':'text-gray-600');
    event.target.classList.add('bg-blue-600','text-white');
    if(t==='users')loadUsers();
    if(t==='backups')loadBackups();
    if(t==='logs')loadLogs(logType);
    if(t==='system')loadSystem();
}

function chartTheme(){return darkMode?{grid:'rgba(255,255,255,0.05)',ticks:'#64748b'}:{grid:'rgba(0,0,0,0.07)',ticks:'#6b7280'};}

function initChart(){
    const ctx=document.getElementById('chart').getContext('2d');
    const t=chartTheme();
    chart=new Chart(ctx,{type:'bar',data:{labels:[],datasets:[{data:[],backgroundColor:'rgba(6,182,212,0.5)',borderColor:'rgb(6,182,212)',borderWidth:1}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:t.grid},ticks:{color:t.ticks}},x:{grid:{display:false},ticks:{color:t.ticks}}}}});
}

function applyChartTheme(){
    if(!chart)return;
    const t=chartTheme();
    chart.options.scales.y.grid.color=t.grid;
    chart.options.scales.y.ticks.color=t.ticks;
    chart.options.scales.x.ticks.color=t.ticks;
    chart.update();
}

async function refreshAll(){
    try{
        const r=await fetch('/api/stats');const d=await r.json();
        document.getElementById('version').textContent=d.version;
        document.getElementById('uptime').textContent=d.uptime_formatted;
        document.getElementById('users').textContent=d.user_count;
        document.getElementById('datasize').textContent=d.data_size_formatted;
        document.getElementById('syncs').textContent=d.sync_count;
        document.getElementById('backups').textContent=d.backup_count;
        document.getElementById('auth-ok').textContent=d.auth_success;
        document.getElementById('auth-fail').textContent=d.auth_failed;
        document.getElementById('sv').textContent=d.version;
        document.getElementById('su').textContent=d.user_count;
        document.getElementById('sb').textContent=d.backup_count;
    }catch(e){}
    
    try{
        const r=await fetch('/api/storage');const d=await r.json();
        const total=d.total||1;
        document.getElementById('storage-bar').innerHTML=Object.entries(storageColors).map(([k,c])=>`<div style="width:${((d[k]||0)/total)*100}%;background:${c}" title="${k}: ${d[k+'_formatted']}"></div>`).join('');
        document.getElementById('storage-legend').innerHTML=Object.entries(storageColors).map(([k,c])=>`<div class="flex items-center gap-2"><span class="w-3 h-3 rounded" style="background:${c}"></span><span class="text-sm text-slate-500">${k.charAt(0).toUpperCase()+k.slice(1)}</span><span class="text-sm font-medium ml-auto">${d[k+'_formatted']}</span></div>`).join('');
        document.getElementById('backups-size').textContent=d.backups_formatted+' total';
    }catch(e){}
    
    try{
        const r=await fetch('/api/features');const d=await r.json();
        document.getElementById('features').innerHTML=Object.entries(d).map(([k,v])=>`<div class="flex justify-between"><span>${k}</span><span class="px-2 py-0.5 rounded-full text-xs font-semibold ${v?'bg-green-500/20 text-green-400':'bg-slate-700 text-slate-500'}">${v?'ON':'OFF'}</span></div>`).join('');
        const nb=document.getElementById('notify-btn');
        if(nb){const on=d['Notifications']||d['Email'];nb.disabled=!on;nb.title=on?'':'Set NOTIFY_ENABLED or EMAIL_ENABLED first';}
    }catch(e){}
    
    try{
        const r=await fetch('/api/chart');const d=await r.json();
        chart.data.labels=d.labels.map(l=>l.slice(5));
        chart.data.datasets[0].data=d.values;
        chart.update();
    }catch(e){}
    
    try{
        const r=await fetch('/api/syncs');const d=await r.json();
        document.getElementById('recent').innerHTML=d.length?d.map(s=>`<div class="flex justify-between p-2 ${darkMode?'bg-slate-700/50':'bg-gray-100'} rounded"><span class="text-cyan-400">${esc(s.user)}${s.count>1?` <span class="text-slate-500 text-xs">×${s.count}</span>`:''}</span><span class="text-slate-500 text-sm" title="${s.time}">${s.epoch?rel(s.epoch):s.time}</span></div>`).join(''):'<div class="text-slate-500">No recent activity</div>';
    }catch(e){}

    try{
        const r=await fetch('/api/update');const d=await r.json();
        const b=document.getElementById('update-badge');
        if(d.update_available){b.textContent='Anki '+d.latest+' available';b.classList.remove('hidden');}
        else b.classList.add('hidden');
    }catch(e){}
}

async function loadUsers(){
    try{
        const r=await fetch('/api/users');const d=await r.json();
        const totalSize=d.reduce((a,b)=>a+b.total_size,0)||1;
        
        document.getElementById('user-storage-chart').innerHTML='<div class="text-xs text-slate-500 uppercase mb-3">Storage per User</div>'+d.map(u=>`<div class="mb-3"><div class="flex justify-between text-sm mb-1"><span class="text-cyan-400 font-medium">${u.username}</span><span>${u.total_size_formatted}</span></div><div class="h-2 ${darkMode?'bg-slate-600':'bg-gray-300'} rounded-full overflow-hidden"><div class="h-full bg-cyan-500 rounded-full" style="width:${(u.total_size/totalSize)*100}%"></div></div></div>`).join('');
        
        document.getElementById('users-list').innerHTML=d.map((u,i)=>`
            <div class="border ${darkMode?'border-slate-700':'border-gray-200'} rounded-lg overflow-hidden">
                <div class="flex items-center justify-between p-4 cursor-pointer ${darkMode?'hover:bg-slate-700':'hover:bg-gray-100'}" onclick="toggleUser(${i})">
                    <div class="flex items-center gap-3">
                        <span class="transition-transform ${expandedUser===i?'rotate-90':''}" id="arrow-${i}">▶</span>
                        <span class="text-cyan-400 font-medium">${u.username}</span>
                    </div>
                    <div class="flex gap-6 text-sm">
                        <span>${u.total_size_formatted}</span>
                        <span class="text-slate-500">${u.last_sync}</span>
                    </div>
                </div>
                <div id="detail-${i}" class="${expandedUser===i?'':'hidden'} ${darkMode?'bg-slate-700/50':'bg-gray-100'} p-4 border-t ${darkMode?'border-slate-700':'border-gray-200'}">
                    <div class="text-xs text-slate-500 uppercase mb-3">Collection Details</div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        ${u.collections.map(c=>`
                            <div class="${darkMode?'bg-slate-800':'bg-white'} rounded-lg p-3">
                                <div class="flex justify-between mb-2">
                                    <span class="font-mono text-sm">${c.name}</span>
                                    <span class="text-cyan-400 font-semibold">${c.size_formatted}</span>
                                </div>
                                <div class="text-xs text-slate-500">${c.cards?c.cards.toLocaleString()+' cards':c.files+' files'}</div>
                                <div class="text-xs text-slate-500">Modified: ${c.modified}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `).join('');
    }catch(e){}
}

function toggleUser(i){expandedUser=expandedUser===i?null:i;loadUsers();}

async function loadBackups(){
    try{
        const r=await fetch('/api/backups');const d=await r.json();
        document.getElementById('bktbl').innerHTML=d.map(b=>`
            <tr class="border-b ${darkMode?'border-slate-700':'border-gray-200'}">
                <td class="py-3 font-mono text-xs">${esc(b.name)}${b.kind==='safety'?' <span class="ml-1 px-1.5 py-0.5 rounded text-[10px] bg-purple-500/20 text-purple-400">pre-restore</span>':''}</td>
                <td class="py-3">${b.size_formatted}</td>
                <td class="py-3 text-slate-500">${b.created}</td>
                <td class="py-3 text-right whitespace-nowrap"><a href="/api/backups/download/${encodeURIComponent(b.name)}" class="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs text-white">↓ Download</a> <button onclick="deleteBackup('${esc(b.name)}')" class="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-xs text-white">✕ Delete</button></td>
            </tr>
        `).join('')||'<tr><td colspan="4" class="py-4 text-center text-slate-500">No backups</td></tr>';
    }catch(e){}
}

async function deleteBackup(n){
    if(!confirm('Delete backup '+n+'?'))return;
    try{
        const r=await fetch('/api/backups/delete/'+encodeURIComponent(n),{method:'POST'});
        const d=await r.json();
        if(d.success)loadBackups();else alert(d.error||'Failed');
    }catch(e){alert('Failed to delete');}
}

async function createBackup(){
    const btn=document.getElementById('bkbtn'),al=document.getElementById('bkalert');
    btn.disabled=true;btn.textContent='Creating...';
    try{
        const r=await fetch('/api/backups/create',{method:'POST'});const d=await r.json();
        al.className='mb-4 p-3 rounded-lg text-sm '+(d.success?'bg-green-900/50 text-green-400':'bg-red-900/50 text-red-400');
        al.textContent=d.message;
        if(d.success)loadBackups();
    }catch(e){
        al.className='mb-4 p-3 rounded-lg text-sm bg-red-900/50 text-red-400';
        al.textContent='Failed';
    }
    btn.disabled=false;btn.textContent='Create Backup';
}

async function testNotify(){
    try{
        const r=await fetch('/api/notify/test',{method:'POST'});const d=await r.json();
        alert(d.message);
    }catch(e){alert('Failed to send notification');}
}

let logLines=[];
async function loadLogs(t){
    logType=t;
    document.querySelectorAll('.logbtn').forEach(b=>{b.classList.remove('bg-blue-600','text-white');b.classList.add('bg-slate-700','text-slate-300');});
    const btn=window.event&&event.target&&event.target.classList.contains('logbtn')?event.target:document.querySelector('.logbtn');
    if(btn){btn.classList.remove('bg-slate-700','text-slate-300');btn.classList.add('bg-blue-600','text-white');}
    try{
        const r=await fetch('/api/logs/'+t+'?lines=500');const d=await r.json();
        logLines=(d.lines&&d.lines[0])?d.lines:[];
        renderLogs();
    }catch(e){document.getElementById('logview').innerHTML='<div class="text-red-400">Failed to load</div>';}
}

function renderLogs(){
    const v=document.getElementById('logview');
    const q=(document.getElementById('logfilter').value||'').toLowerCase();
    const lines=q?logLines.filter(l=>l.toLowerCase().includes(q)):logLines;
    if(!lines.length){
        v.innerHTML='<div class="text-slate-500">'+(q?'No matching lines':'No logs')+'</div>';
        return;
    }
    v.innerHTML=lines.map(l=>{
        let c='text-slate-400';
        if(l.includes('ERROR')||l.includes('FAILED'))c='text-red-400';
        else if(l.includes('SUCCESS')||l.includes('COMPLETE'))c='text-green-400';
        else if(l.includes('WARN'))c='text-yellow-400';
        return`<div class="${c} border-b border-slate-800/50 py-1">${esc(l)}</div>`;
    }).join('');
    if(document.getElementById('logfollow').checked)v.scrollTop=v.scrollHeight;
}

function refreshLogs(){loadLogs(logType);}

async function loadSystem(){
    try{
        const r=await fetch('/api/system');const d=await r.json();
        document.getElementById('du').textContent=d.disk_used_formatted;
        document.getElementById('dt').textContent=d.disk_total_formatted;
        document.getElementById('dp').style.width=d.disk_percent+'%';
        document.getElementById('dpc').textContent=d.disk_percent.toFixed(1);
        document.getElementById('mu').textContent=d.memory_used_formatted;
        document.getElementById('mt').textContent=d.memory_total_formatted;
        document.getElementById('mp').style.width=d.memory_percent+'%';
        document.getElementById('mpc').textContent=d.memory_percent.toFixed(1);
        document.getElementById('l1').textContent=d.load_avg[0].toFixed(2);
        document.getElementById('l5').textContent=d.load_avg[1].toFixed(2);
        document.getElementById('l15').textContent=d.load_avg[2].toFixed(2);
    }catch(e){}
    
    try{
        const r=await fetch('/api/container');const d=await r.json();
        document.getElementById('container-info').innerHTML=`
            <div><div class="text-xs text-slate-500">Container ID</div><div class="text-sm font-mono">${d.container_id}</div></div>
            <div><div class="text-xs text-slate-500">Image</div><div class="text-sm">${d.image_name}</div></div>
            <div><div class="text-xs text-slate-500">Restarts</div><div class="text-lg font-semibold text-green-400">${d.restarts}</div></div>
        `;
    }catch(e){}
}
</script>
</body></html>'''

@app.route('/')
@requires_auth
def dashboard():
    return render_template_string(DASHBOARD_HTML)

if __name__ == '__main__':
    port = int(os.environ.get('DASHBOARD_PORT', 8081))
    print(f"Starting dashboard on port {port}")
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)
