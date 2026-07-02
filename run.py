#!/usr/bin/env python3
"""Electricity Manager v3"""
import os, sys, argparse, traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

env_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

_load_error = None
try:
    from app import create_app as _create
    app = _create()
    app.logger.info("Full app loaded successfully")
except Exception as ex:
    _load_error = str(ex)
    traceback.print_exc()

# Routes that use the FINAL app (fallback or full)
@app.route('/')
def index():
    err = str(_load_error) if _load_error else 'None'
    return f'Error: {err} | Health: <a href=/health>/health</a>'

from config import Config
Config.PORT = int(os.environ.get('PORT', Config.PORT))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--host', default=Config.HOST)
    parser.add_argument('--port', type=int, default=Config.PORT)
    args = parser.parse_args()
    try:
        from waitress import serve
        serve(app, host=args.host, port=args.port, threads=8)
    except ImportError:
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
