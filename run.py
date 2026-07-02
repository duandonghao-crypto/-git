#!/usr/bin/env python3
"""Electricity Manager v3"""
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

env_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK'

error_msg = None
try:
    from app import create_app
    app = create_app()
except Exception as e:
    import traceback
    traceback.print_exc()
    error_msg = str(e)[:300]

if error_msg:
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        return 'AppError: ' + str(error_msg)
else:
    try:
        return  # Routes already registered by create_app(), nothing to add
    finally:
        pass

from config import Config
Config.PORT = int(os.environ.get('PORT', Config.PORT))

if __name__ == '__main__':
    import argparse
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
