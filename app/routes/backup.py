"""Backup and restore routes"""
import os, time, glob, shutil, sqlite3
from flask import Blueprint, request, jsonify
from config import Config

backup_bp = Blueprint('backup', __name__)


@backup_bp.route('/api/backups')
def list_backups():
    os.makedirs(Config.BACKUP_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(Config.BACKUP_DIR, 'electricity_*.bak')), reverse=True)
    result = []
    for fp in files[:Config.MAX_BACKUPS]:
        st = os.stat(fp)
        sz = st.st_size
        size_str = f'{sz / 1024 / 1024:.1f} MB' if sz > 1024 * 1024 else f'{sz / 1024:.1f} KB' if sz > 1024 else f'{sz} B'
        result.append({'name': os.path.basename(fp), 'size': size_str, 'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))})
    return jsonify({'backups': result})


@backup_bp.route('/api/backup', methods=['POST'])
def backup():
    os.makedirs(Config.BACKUP_DIR, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    fname = f'electricity_{ts}.bak'
    dest = os.path.join(Config.BACKUP_DIR, fname)
    if hasattr(Config, 'SQLITE_PATH') and os.path.exists(Config.SQLITE_PATH):
        shutil.copy2(Config.SQLITE_PATH, dest)
    else:
        return jsonify({'success': True, 'message': '云数据库无需备份'})
    files = sorted(glob.glob(os.path.join(Config.BACKUP_DIR, 'electricity_*.bak')))
    for old in files[:-Config.MAX_BACKUPS]:
        try: os.remove(old)
        except: pass
    return jsonify({'success': True, 'message': f'备份成功: {fname}', 'file': fname})


@backup_bp.route('/api/restore', methods=['POST'])
def restore():
    if not hasattr(Config, 'SQLITE_PATH') or not os.path.exists(Config.SQLITE_PATH):
        return jsonify({'success': False, 'message': '云数据库不支持恢复'}), 400
    os.makedirs(Config.BACKUP_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(Config.BACKUP_DIR, 'electricity_*.bak')))
    if not files:
        return jsonify({'success': False, 'message': '没有可用的备份文件'}), 400
    latest = files[-1]
    ts = time.strftime('%Y%m%d_%H%M%S')
    pre_bak = os.path.join(Config.BACKUP_DIR, f'electricity_before_restore_{ts}.bak')
    if os.path.exists(Config.SQLITE_PATH):
        shutil.copy2(Config.SQLITE_PATH, pre_bak)
        shutil.copy2(latest, Config.SQLITE_PATH)
    return jsonify({'success': True, 'message': f'已从 {os.path.basename(latest)} 恢复'})


@backup_bp.route('/api/upload_backups')
def list_upload_backups():
    os.makedirs(Config.BACKUP_DIR, exist_ok=True)
    files = []
    for fn in sorted(os.listdir(Config.BACKUP_DIR), reverse=True):
        if not fn.endswith('.db'): continue
        if not (fn.startswith('auto_upload_') or fn.startswith('auto_upload_before_')): continue
        fp = os.path.join(Config.BACKUP_DIR, fn)
        st = os.stat(fp)
        label = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime + 8 * 3600))
        sz = st.st_size
        cnt = 0
        try:
            tc = sqlite3.connect(fp)
            tc.execute("SELECT COUNT(*) FROM transactions WHERE year_month LIKE '%-%'")
            cnt = tc.fetchone()[0]; tc.close()
        except: pass
        files.append({'file': fn, 'time': label, 'label': fn[:-3],
                       'size': f'{sz / 1024:.1f} KB' if sz < 1024 * 1024 else f'{sz / 1024 / 1024:.1f} MB',
                       'records': cnt})
    return jsonify({'backups': files})


@backup_bp.route('/api/undo_specific_upload', methods=['POST'])
def undo_specific_upload():
    data = request.get_json(force=True) or {}
    fn = data.get('file', '')
    if not fn: return jsonify({'success': False, 'message': '请指定备份文件'})
    backup_path = os.path.join(Config.BACKUP_DIR, fn)
    if not os.path.exists(backup_path): return jsonify({'success': False, 'message': '备份文件不存在'})
    if not hasattr(Config, 'SQLITE_PATH') or not os.path.exists(Config.SQLITE_PATH):
        return jsonify({'success': False, 'message': '云数据库不支持撤销'})
    ts = time.strftime('%Y%m%d_%H%M%S')
    pre_bak = os.path.join(Config.BACKUP_DIR, f'auto_upload_before_undo_{ts}.db')
    shutil.copy2(Config.SQLITE_PATH, pre_bak)
    shutil.copy2(backup_path, Config.SQLITE_PATH)
    return jsonify({'success': True, 'message': f'已从备份 {fn} 恢复'})
