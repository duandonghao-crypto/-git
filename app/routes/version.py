"""Version management routes"""
import os
import time
import shutil
from flask import Blueprint, request, jsonify
from config import Config, BASE_DIR

version_bp = Blueprint('version', __name__)


@version_bp.route('/api/versions')
def list_versions():
    os.makedirs(Config.VERSIONS_DIR, exist_ok=True)
    files = sorted([f for f in os.listdir(Config.VERSIONS_DIR) if f.endswith('.html')], reverse=True)
    result = []
    for fn in files:
        fp = os.path.join(Config.VERSIONS_DIR, fn)
        st = os.stat(fp)
        result.append({
            'name': fn,
            'size': f'{st.st_size / 1024:.1f} KB',
            'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))
        })
    return jsonify({'versions': result, 'current': 'index.html'})


@version_bp.route('/api/version_save', methods=['POST'])
def version_save():
    os.makedirs(Config.VERSIONS_DIR, exist_ok=True)
    data = request.get_json(force=True)
    label = data.get('label', 'snapshot')
    ts = time.strftime('%Y%m%d_%H%M%S')
    safe_label = label.replace(' ', '_').replace('/', '_')[:30]
    fname = f'index_v{ts}_{safe_label}.html'
    dest = os.path.join(Config.VERSIONS_DIR, fname)
    src = os.path.join(BASE_DIR, 'static', 'index.html')
    shutil.copy2(src, dest)
    return jsonify({'success': True, 'message': f'版本已保存: {fname}', 'file': fname})


@version_bp.route('/api/version_switch', methods=['POST'])
def version_switch():
    data = request.get_json(force=True)
    fname = data.get('file', '')
    if not fname:
        return jsonify({'success': False, 'message': '请指定版本文件'}), 400
    src = os.path.join(Config.VERSIONS_DIR, fname)
    if not os.path.exists(src):
        return jsonify({'success': False, 'message': '版本文件不存在'}), 404

    ts = time.strftime('%Y%m%d_%H%M%S')
    current = os.path.join(BASE_DIR, 'static', 'index.html')
    before = os.path.join(Config.VERSIONS_DIR, f'index_v{ts}_before_switch.html')
    shutil.copy2(current, before)
    shutil.copy2(src, current)
    return jsonify({'success': True, 'message': f'已切换至 {fname}，重启服务后生效'})
