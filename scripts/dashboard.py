#!/usr/bin/env python3
"""
Anki Sync Server Enhanced Dashboard - Dark Theme
Matches the sleek dark design with interactive features
"""

import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, render_template_string, jsonify, request, Response

app = Flask(__name__)

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
        return True
    return username == expected[0] and password == expected[1]

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

def get_dir_size(path):
    total = 0
    try:
        for entry in Path(path).rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
    except:
        pass
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
    except:
        return default

def read_log_lines(path, lines=100):
    try:
        result = subprocess.run(['tail', '-n', str(lines), path],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip().split('\n') if result.stdout else []
    except:
        return []

def get_users():
    users_file = os.path.join(STATE_DIR, 'users.txt')
    if os.path.exists(users_file):
        with open(users_file, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def get_user_stats():
    stats = []
    for user in get_users():
        user_dir = os.path.join(DATA_DIR, user)
        if os.path.exists(user_dir):
            size = get_dir_size(user_dir)
            try:
                last_sync = datetime.fromtimestamp(os.path.getmtime(user_dir)).strftime('%Y-%m-%d %H:%M')
            except:
                last_sync = 'Unknown'
            collections = len(list(Path(user_dir).glob('*.anki2*')))
        else:
            size, last_sync, collections = 0, 'Never', 0
        stats.append({'username': user, 'size_formatted': format_bytes(size), 'last_sync': last_sync, 'collections': collections})
    return stats

def get_backups():
    backups = []
    if os.path.exists(BACKUP_DIR):
        for f in sorted(Path(BACKUP_DIR).glob('*.tar.gz'), reverse=True)[:20]:
            stat = f.stat()
            backups.append({
                'name': f.name,
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
    lines = read_log_lines(os.path.join(LOG_DIR, 'sync.log'), 5000)
    daily = {(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'): 0 for i in range(7)}
    for line in lines:
        if 'SYNC' in line and 'COMPLETE' in line:
            date = line.split()[0] if line.split() else ''
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
    except: pass
    try:
        with open('/proc/meminfo') as f:
            mem = {l.split()[0].rstrip(':'): int(l.split()[1]) * 1024 for l in f if len(l.split()) >= 2}
        stats['memory_total'] = mem.get('MemTotal', 0)
        stats['memory_used'] = stats['memory_total'] - mem.get('MemAvailable', mem.get('MemFree', 0))
        stats['memory_percent'] = (stats['memory_used'] / stats['memory_total'] * 100) if stats['memory_total'] else 0
    except: pass
    try:
        with open('/proc/loadavg') as f:
            p = f.read().split()
            stats['load_avg'] = [float(p[0]), float(p[1]), float(p[2])]
    except: pass
    return stats

def get_recent_syncs():
    lines = read_log_lines(os.path.join(LOG_DIR, 'sync.log'), 200)
    syncs = []
    for line in reversed(lines):
        if 'SYNC' in line and 'COMPLETE' in line:
            parts = line.split()
            if len(parts) >= 4:
                syncs.append({'time': parts[0] + ' ' + parts[1], 'user': parts[3].replace('user=', '')})
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
    return jsonify(get_user_stats())

@app.route('/api/backups')
@requires_auth
def api_backups():
    return jsonify(get_backups())

@app.route('/api/backups/create', methods=['POST'])
@requires_auth
def api_create_backup():
    try:
        result = subprocess.run(['/usr/local/bin/backup.sh'], capture_output=True, text=True, timeout=300)
        return jsonify({'success': result.returncode == 0, 'message': 'Backup created' if result.returncode == 0 else result.stderr or 'Failed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logs/<log_type>')
@requires_auth
def api_logs(log_type):
    files = {'sync': 'sync.log', 'auth': 'auth.log', 'backup': 'backup.log'}
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
                    [('Backups', 'BACKUP_ENABLED'), ('S3 Upload', 'S3_BACKUP_ENABLED'), ('Metrics', 'METRICS_ENABLED'),
                     ('Fail2Ban', 'FAIL2BAN_ENABLED'), ('Notifications', 'NOTIFY_ENABLED'), ('Rate Limit', 'RATE_LIMIT_ENABLED')]})

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
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>tailwind.config={theme:{extend:{colors:{card:'#1e293b',bg:'#0f172a'}}}}</script>
</head>
<body class="bg-bg min-h-screen text-slate-200 p-6">
    <div class="max-w-7xl mx-auto">
        <h1 class="text-center text-4xl font-light mb-8"><span class="text-white">Anki</span> <span class="text-cyan-400">Sync Server</span></h1>
        
        <!-- Tabs -->
        <div class="flex justify-center gap-2 mb-8">
            <button onclick="showTab('overview')" class="tab-btn px-5 py-2 rounded-lg bg-blue-600 text-white">Overview</button>
            <button onclick="showTab('users')" class="tab-btn px-5 py-2 rounded-lg bg-card text-slate-400 hover:bg-slate-700">Users</button>
            <button onclick="showTab('backups')" class="tab-btn px-5 py-2 rounded-lg bg-card text-slate-400 hover:bg-slate-700">Backups</button>
            <button onclick="showTab('logs')" class="tab-btn px-5 py-2 rounded-lg bg-card text-slate-400 hover:bg-slate-700">Logs</button>
            <button onclick="showTab('system')" class="tab-btn px-5 py-2 rounded-lg bg-card text-slate-400 hover:bg-slate-700">System</button>
        </div>

        <!-- Overview -->
        <div id="tab-overview" class="tab-content">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-6">
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Server Status</div><div class="flex items-center gap-2 mb-1"><span class="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse"></span><span class="text-lg text-green-400">Online</span></div><div class="text-sm text-slate-500">Version: <span id="version">--</span></div><div class="text-sm text-slate-500">Uptime: <span id="uptime">--</span></div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Users</div><div class="text-4xl font-bold text-green-400" id="users">--</div><div class="text-sm text-slate-500 mt-1">Active users</div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Data Size</div><div class="text-4xl font-bold text-cyan-400" id="datasize">--</div><div class="text-sm text-slate-500 mt-1">Total sync data</div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-2">Sync Operations</div><div class="text-4xl font-bold text-orange-400" id="syncs">--</div><div class="text-sm text-slate-500 mt-1">Since restart</div></div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Features</div><div id="features" class="space-y-2"></div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Backups</div><div class="text-4xl font-bold text-slate-300" id="backups">--</div><div class="text-sm text-slate-500 mt-1">Backup files</div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Auth Stats</div><div class="space-y-1 mt-2"><div>Success: <span class="text-green-400 font-semibold" id="auth-ok">0</span></div><div>Failed: <span class="text-red-400 font-semibold" id="auth-fail">0</span></div></div></div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Sync Activity (7 Days)</div><canvas id="chart" height="180"></canvas></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase tracking-wider mb-4">Recent Syncs</div><div id="recent" class="space-y-2 max-h-52 overflow-auto"></div></div>
            </div>
        </div>

        <!-- Users -->
        <div id="tab-users" class="tab-content hidden">
            <div class="bg-card rounded-xl p-5">
                <div class="flex justify-between mb-4"><span class="text-xs text-slate-500 uppercase">User Statistics</span><button onclick="loadUsers()" class="px-4 py-1.5 bg-blue-600 rounded-lg text-sm hover:bg-blue-700">Refresh</button></div>
                <table class="w-full"><thead><tr class="text-left text-slate-500 text-xs border-b border-slate-700"><th class="pb-2">Username</th><th class="pb-2">Size</th><th class="pb-2">Collections</th><th class="pb-2">Last Sync</th></tr></thead><tbody id="usertbl"></tbody></table>
            </div>
        </div>

        <!-- Backups -->
        <div id="tab-backups" class="tab-content hidden">
            <div class="bg-card rounded-xl p-5">
                <div class="flex justify-between mb-4"><span class="text-xs text-slate-500 uppercase">Backup Files</span><button id="bkbtn" onclick="createBackup()" class="px-4 py-1.5 bg-green-600 rounded-lg text-sm hover:bg-green-700">Create Backup</button></div>
                <div id="bkalert" class="hidden mb-3 p-3 rounded-lg text-sm"></div>
                <table class="w-full"><thead><tr class="text-left text-slate-500 text-xs border-b border-slate-700"><th class="pb-2">Filename</th><th class="pb-2">Size</th><th class="pb-2">Created</th></tr></thead><tbody id="bktbl"></tbody></table>
            </div>
        </div>

        <!-- Logs -->
        <div id="tab-logs" class="tab-content hidden">
            <div class="bg-card rounded-xl p-5">
                <div class="flex justify-between mb-4">
                    <div class="flex gap-2"><button onclick="loadLogs('sync')" class="logbtn px-4 py-1.5 bg-blue-600 rounded-lg text-sm">Sync</button><button onclick="loadLogs('auth')" class="logbtn px-4 py-1.5 bg-slate-700 rounded-lg text-sm hover:bg-slate-600">Auth</button><button onclick="loadLogs('backup')" class="logbtn px-4 py-1.5 bg-slate-700 rounded-lg text-sm hover:bg-slate-600">Backup</button></div>
                    <button onclick="refreshLogs()" class="px-4 py-1.5 bg-blue-600 rounded-lg text-sm hover:bg-blue-700">Refresh</button>
                </div>
                <div id="logview" class="bg-slate-900 rounded-lg p-4 font-mono text-xs max-h-96 overflow-auto"></div>
            </div>
        </div>

        <!-- System -->
        <div id="tab-system" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Disk Usage</div><div class="flex justify-between text-sm mb-1"><span id="du">--</span><span id="dt">--</span></div><div class="h-2 bg-slate-700 rounded-full overflow-hidden"><div id="dp" class="h-full bg-blue-500 rounded-full" style="width:0"></div></div><div class="text-xs text-slate-500 mt-1"><span id="dpc">0</span>% used</div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Memory Usage</div><div class="flex justify-between text-sm mb-1"><span id="mu">--</span><span id="mt">--</span></div><div class="h-2 bg-slate-700 rounded-full overflow-hidden"><div id="mp" class="h-full bg-green-500 rounded-full" style="width:0"></div></div><div class="text-xs text-slate-500 mt-1"><span id="mpc">0</span>% used</div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Load Average</div><div class="grid grid-cols-3 gap-4 text-center mt-2"><div><div class="text-2xl font-bold text-blue-400" id="l1">--</div><div class="text-xs text-slate-500">1m</div></div><div><div class="text-2xl font-bold text-blue-400" id="l5">--</div><div class="text-xs text-slate-500">5m</div></div><div><div class="text-2xl font-bold text-blue-400" id="l15">--</div><div class="text-xs text-slate-500">15m</div></div></div></div>
                <div class="bg-card rounded-xl p-5"><div class="text-xs text-slate-500 uppercase mb-3">Server Info</div><div class="space-y-1 text-sm"><div>Version: <span id="sv">--</span></div><div>Users: <span id="su">--</span></div><div>Backups: <span id="sb">--</span></div></div></div>
            </div>
        </div>

        <footer class="text-center text-slate-600 text-sm mt-8">Anki Sync Server Enhanced | Auto-refresh: <span id="cd">10</span>s</footer>
    </div>
<script>
let logType='sync',chart,cd=10;
document.addEventListener('DOMContentLoaded',()=>{initChart();refreshAll();setInterval(()=>{cd--;document.getElementById('cd').textContent=cd;if(cd<=0){cd=10;refreshAll();}},1000);});
function showTab(t){document.querySelectorAll('.tab-content').forEach(e=>e.classList.add('hidden'));document.getElementById('tab-'+t).classList.remove('hidden');document.querySelectorAll('.tab-btn').forEach(b=>{b.classList.remove('bg-blue-600','text-white');b.classList.add('bg-card','text-slate-400');});event.target.classList.remove('bg-card','text-slate-400');event.target.classList.add('bg-blue-600','text-white');if(t==='users')loadUsers();if(t==='backups')loadBackups();if(t==='logs')loadLogs(logType);if(t==='system')loadSystem();}
function initChart(){const ctx=document.getElementById('chart').getContext('2d');chart=new Chart(ctx,{type:'bar',data:{labels:[],datasets:[{data:[],backgroundColor:'rgba(6,182,212,0.5)',borderColor:'rgb(6,182,212)',borderWidth:1}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'rgba(255,255,255,0.05)'},ticks:{color:'#64748b'}},x:{grid:{display:false},ticks:{color:'#64748b'}}}}});}
async function refreshAll(){try{const r=await fetch('/api/stats');const d=await r.json();document.getElementById('version').textContent=d.version;document.getElementById('uptime').textContent=d.uptime_formatted;document.getElementById('users').textContent=d.user_count;document.getElementById('datasize').textContent=d.data_size_formatted;document.getElementById('syncs').textContent=d.sync_count;document.getElementById('backups').textContent=d.backup_count;document.getElementById('auth-ok').textContent=d.auth_success;document.getElementById('auth-fail').textContent=d.auth_failed;document.getElementById('sv').textContent=d.version;document.getElementById('su').textContent=d.user_count;document.getElementById('sb').textContent=d.backup_count;}catch(e){}
try{const r=await fetch('/api/features');const d=await r.json();document.getElementById('features').innerHTML=Object.entries(d).map(([k,v])=>`<div class="flex justify-between"><span>${k}</span><span class="px-2 py-0.5 rounded-full text-xs font-semibold ${v?'bg-green-500/20 text-green-400':'bg-slate-700 text-slate-500'}">${v?'ON':'OFF'}</span></div>`).join('');}catch(e){}
try{const r=await fetch('/api/chart');const d=await r.json();chart.data.labels=d.labels.map(l=>l.slice(5));chart.data.datasets[0].data=d.values;chart.update();}catch(e){}
try{const r=await fetch('/api/syncs');const d=await r.json();document.getElementById('recent').innerHTML=d.length?d.map(s=>`<div class="flex justify-between p-2 bg-slate-800/50 rounded"><span class="text-cyan-400">${s.user}</span><span class="text-slate-500 text-sm">${s.time}</span></div>`).join(''):'<div class="text-slate-500">No recent activity</div>';}catch(e){}}
async function loadUsers(){try{const r=await fetch('/api/users');const d=await r.json();document.getElementById('usertbl').innerHTML=d.map(u=>`<tr class="border-b border-slate-800"><td class="py-2 text-cyan-400">${u.username}</td><td class="py-2">${u.size_formatted}</td><td class="py-2">${u.collections}</td><td class="py-2 text-slate-500">${u.last_sync}</td></tr>`).join('')||'<tr><td colspan="4" class="py-4 text-center text-slate-500">No users</td></tr>';}catch(e){}}
async function loadBackups(){try{const r=await fetch('/api/backups');const d=await r.json();document.getElementById('bktbl').innerHTML=d.map(b=>`<tr class="border-b border-slate-800"><td class="py-2 font-mono text-xs">${b.name}</td><td class="py-2">${b.size_formatted}</td><td class="py-2 text-slate-500">${b.created}</td></tr>`).join('')||'<tr><td colspan="3" class="py-4 text-center text-slate-500">No backups</td></tr>';}catch(e){}}
async function createBackup(){const btn=document.getElementById('bkbtn'),al=document.getElementById('bkalert');btn.disabled=true;btn.textContent='Creating...';try{const r=await fetch('/api/backups/create',{method:'POST'});const d=await r.json();al.className='mb-3 p-3 rounded-lg text-sm '+(d.success?'bg-green-900/50 text-green-400':'bg-red-900/50 text-red-400');al.textContent=d.message;if(d.success)loadBackups();}catch(e){al.className='mb-3 p-3 rounded-lg text-sm bg-red-900/50 text-red-400';al.textContent='Failed';}btn.disabled=false;btn.textContent='Create Backup';}
async function loadLogs(t){logType=t;document.querySelectorAll('.logbtn').forEach(b=>{b.classList.remove('bg-blue-600');b.classList.add('bg-slate-700');});event.target.classList.remove('bg-slate-700');event.target.classList.add('bg-blue-600');try{const r=await fetch('/api/logs/'+t+'?lines=200');const d=await r.json();const v=document.getElementById('logview');if(!d.lines||!d.lines.length||!d.lines[0])v.innerHTML='<div class="text-slate-500">No logs</div>';else{v.innerHTML=d.lines.map(l=>{let c='';if(l.includes('ERROR')||l.includes('FAILED'))c='text-red-400';else if(l.includes('SUCCESS')||l.includes('COMPLETE'))c='text-green-400';else if(l.includes('WARN'))c='text-yellow-400';return`<div class="${c} border-b border-slate-800/50 py-1">${l.replace(/</g,'&lt;')}</div>`;}).join('');v.scrollTop=v.scrollHeight;}}catch(e){document.getElementById('logview').innerHTML='<div class="text-red-400">Failed to load</div>';}}
function refreshLogs(){loadLogs(logType);}
async function loadSystem(){try{const r=await fetch('/api/system');const d=await r.json();document.getElementById('du').textContent=d.disk_used_formatted;document.getElementById('dt').textContent=d.disk_total_formatted;document.getElementById('dp').style.width=d.disk_percent+'%';document.getElementById('dpc').textContent=d.disk_percent.toFixed(1);document.getElementById('mu').textContent=d.memory_used_formatted;document.getElementById('mt').textContent=d.memory_total_formatted;document.getElementById('mp').style.width=d.memory_percent+'%';document.getElementById('mpc').textContent=d.memory_percent.toFixed(1);document.getElementById('l1').textContent=d.load_avg[0].toFixed(2);document.getElementById('l5').textContent=d.load_avg[1].toFixed(2);document.getElementById('l15').textContent=d.load_avg[2].toFixed(2);}catch(e){}}
</script>
</body></html>'''

@app.route('/')
@requires_auth
def dashboard():
    return render_template_string(DASHBOARD_HTML)

if __name__ == '__main__':
    print(f"Starting dashboard on port {os.environ.get('DASHBOARD_PORT', 8081)}")
    app.run(host='0.0.0.0', port=int(os.environ.get('DASHBOARD_PORT', 8081)), threaded=True)
