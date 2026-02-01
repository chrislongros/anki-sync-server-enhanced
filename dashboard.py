#!/usr/bin/env python3
"""
Anki Sync Server Enhanced - Web Dashboard
A simple status dashboard showing server health, users, and statistics.
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template_string, jsonify, request, Response

app = Flask(__name__)

# Configuration
DASHBOARD_PORT = int(os.environ.get('DASHBOARD_PORT', 8081))
DASHBOARD_AUTH = os.environ.get('DASHBOARD_AUTH', '')  # user:pass
DATA_DIR = os.environ.get('SYNC_BASE', '/data')
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/backups')

# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Anki Sync Server Dashboard</title>
    <style>
        :root {
            --bg: #1a1a2e;
            --card: #16213e;
            --accent: #0f3460;
            --text: #eee;
            --muted: #888;
            --green: #00d26a;
            --red: #ff6b6b;
            --blue: #4dabf7;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { 
            text-align: center; 
            margin-bottom: 30px;
            font-weight: 300;
        }
        h1 span { color: var(--blue); }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--accent);
        }
        .card h2 {
            font-size: 14px;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 15px;
            letter-spacing: 1px;
        }
        .stat {
            font-size: 36px;
            font-weight: 600;
            margin-bottom: 5px;
        }
        .stat.green { color: var(--green); }
        .stat.blue { color: var(--blue); }
        .label { color: var(--muted); font-size: 14px; }
        .status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--green);
        }
        .status-dot.offline { background: var(--red); }
        .feature-list { list-style: none; }
        .feature-list li {
            padding: 8px 0;
            border-bottom: 1px solid var(--accent);
            display: flex;
            justify-content: space-between;
        }
        .feature-list li:last-child { border-bottom: none; }
        .badge {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge.on { background: var(--green); color: #000; }
        .badge.off { background: var(--accent); color: var(--muted); }
        .user-list { list-style: none; }
        .user-list li {
            padding: 10px;
            background: var(--accent);
            border-radius: 6px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .backup-list { max-height: 200px; overflow-y: auto; }
        .backup-item {
            padding: 8px;
            background: var(--accent);
            border-radius: 4px;
            margin-bottom: 6px;
            font-size: 13px;
            font-family: monospace;
        }
        .refresh-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--blue);
            color: #fff;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
        }
        .refresh-btn:hover { opacity: 0.9; }
        footer {
            text-align: center;
            color: var(--muted);
            margin-top: 40px;
            font-size: 13px;
        }
        @media (max-width: 600px) {
            .stat { font-size: 28px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Anki <span>Sync Server</span></h1>
        
        <div class="grid">
            <div class="card">
                <h2>Server Status</h2>
                <div class="status">
                    <span class="status-dot" id="status-dot"></span>
                    <span id="status-text">Loading...</span>
                </div>
                <p class="label" style="margin-top: 15px;">Version: <span id="version">-</span></p>
                <p class="label">Uptime: <span id="uptime">-</span></p>
            </div>
            
            <div class="card">
                <h2>Users</h2>
                <div class="stat blue" id="user-count">-</div>
                <p class="label">Active users</p>
            </div>
            
            <div class="card">
                <h2>Data Size</h2>
                <div class="stat green" id="data-size">-</div>
                <p class="label">Total sync data</p>
            </div>
            
            <div class="card">
                <h2>Sync Operations</h2>
                <div class="stat" id="sync-count">-</div>
                <p class="label">Since last restart</p>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>Features</h2>
                <ul class="feature-list">
                    <li>Backups <span class="badge" id="feat-backup">-</span></li>
                    <li>S3 Upload <span class="badge" id="feat-s3">-</span></li>
                    <li>Metrics <span class="badge" id="feat-metrics">-</span></li>
                    <li>Fail2Ban <span class="badge" id="feat-fail2ban">-</span></li>
                </ul>
            </div>
            
            <div class="card">
                <h2>Backups</h2>
                <div class="stat" id="backup-count">-</div>
                <p class="label">Backup files</p>
                <div class="backup-list" id="backup-list" style="margin-top: 15px;"></div>
            </div>
            
            <div class="card">
                <h2>Authentication</h2>
                <p class="label">Successful: <span id="auth-success">0</span></p>
                <p class="label">Failed: <span id="auth-failed">0</span></p>
            </div>
        </div>
        
        <footer>
            Last updated: <span id="last-update">-</span><br>
            Anki Sync Server Enhanced
        </footer>
    </div>
    
    <button class="refresh-btn" onclick="loadData()">Refresh</button>
    
    <script>
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }
        
        function formatUptime(seconds) {
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            if (days > 0) return days + 'd ' + hours + 'h';
            if (hours > 0) return hours + 'h ' + mins + 'm';
            return mins + 'm';
        }
        
        function setBadge(id, value) {
            const el = document.getElementById(id);
            if (value === 'true' || value === true) {
                el.textContent = 'ON';
                el.className = 'badge on';
            } else {
                el.textContent = 'OFF';
                el.className = 'badge off';
            }
        }
        
        async function loadData() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                // Status
                document.getElementById('status-dot').className = 'status-dot';
                document.getElementById('status-text').textContent = 'Online';
                document.getElementById('version').textContent = data.anki_version || '-';
                document.getElementById('uptime').textContent = formatUptime(data.uptime_seconds || 0);
                
                // Stats
                document.getElementById('user-count').textContent = data.users || 0;
                document.getElementById('data-size').textContent = formatBytes(data.data_size_bytes || 0);
                document.getElementById('sync-count').textContent = data.sync_count || 0;
                document.getElementById('backup-count').textContent = data.backup_count || 0;
                
                // Features
                setBadge('feat-backup', data.backup_enabled);
                setBadge('feat-s3', data.s3_enabled);
                setBadge('feat-metrics', data.metrics_enabled);
                setBadge('feat-fail2ban', data.fail2ban_enabled);
                
                // Auth
                document.getElementById('auth-success').textContent = data.auth_success || 0;
                document.getElementById('auth-failed').textContent = data.auth_failed || 0;
                
                // Backups list
                if (data.backups && data.backups.length > 0) {
                    document.getElementById('backup-list').innerHTML = data.backups
                        .slice(0, 5)
                        .map(b => `<div class="backup-item">${b}</div>`)
                        .join('');
                }
                
                // Last update
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                
            } catch (e) {
                document.getElementById('status-dot').className = 'status-dot offline';
                document.getElementById('status-text').textContent = 'Error';
            }
        }
        
        loadData();
        setInterval(loadData, 30000);
    </script>
</body>
</html>
"""

def check_auth(username, password):
    """Check if username/password is valid."""
    if not DASHBOARD_AUTH:
        return True
    expected_user, expected_pass = DASHBOARD_AUTH.split(':', 1)
    return username == expected_user and password == expected_pass

def requires_auth(f):
    """Decorator for routes that require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_AUTH:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="Anki Dashboard"'}
            )
        return f(*args, **kwargs)
    return decorated

def get_dir_size(path):
    """Get total size of directory in bytes."""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total += os.path.getsize(fp)
    except:
        pass
    return total

def get_backups():
    """Get list of backup files."""
    try:
        files = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith('.tar.gz')],
            reverse=True
        )
        return files
    except:
        return []

def get_auth_stats():
    """Get authentication statistics from log."""
    success = 0
    failed = 0
    try:
        with open('/var/log/anki/auth.log', 'r') as f:
            for line in f:
                if 'AUTH_SUCCESS' in line:
                    success += 1
                elif 'AUTH_FAILED' in line:
                    failed += 1
    except:
        pass
    return success, failed

def read_file(path, default='0'):
    """Read a file and return its contents."""
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except:
        return default

@app.route('/')
@requires_auth
def dashboard():
    """Serve the dashboard HTML."""
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/status')
@requires_auth
def api_status():
    """Return server status as JSON."""
    start_time = int(read_file('/var/lib/anki/start_time.txt', str(int(time.time()))))
    auth_success, auth_failed = get_auth_stats()
    
    status = {
        'anki_version': read_file('/var/lib/anki/version.txt', 'unknown'),
        'status': 'running',
        'users': int(read_file('/var/lib/anki/user_count.txt', '0')),
        'user_names': read_file('/var/lib/anki/users.txt', ''),
        'uptime_seconds': int(time.time()) - start_time,
        'sync_count': int(read_file('/var/lib/anki/sync_count.txt', '0')),
        'data_size_bytes': get_dir_size(DATA_DIR),
        'backup_count': len(get_backups()),
        'backups': get_backups()[:10],
        'backup_enabled': os.environ.get('BACKUP_ENABLED', 'false'),
        'metrics_enabled': os.environ.get('METRICS_ENABLED', 'false'),
        'dashboard_enabled': 'true',
        'fail2ban_enabled': os.environ.get('FAIL2BAN_ENABLED', 'false'),
        's3_enabled': os.environ.get('S3_BACKUP_ENABLED', 'false'),
        'auth_success': auth_success,
        'auth_failed': auth_failed,
        'last_updated': datetime.now().isoformat()
    }
    
    return jsonify(status)

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print(f"Starting dashboard on port {DASHBOARD_PORT}")
    app.run(host='0.0.0.0', port=DASHBOARD_PORT, threaded=True)
