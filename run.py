#!/usr/bin/env python3
"""Electricity Manager v3 - Direct static file serving"""
import os, sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK'

@app.route('/', defaults={'filename': 'index.html'})
@app.route('/<path:filename>')
def serve_file(filename):
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    path = os.path.join(static_dir, filename.lstrip('/'))
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return 'Not Found: ' + filename, 404

# Try loading full app
error = None
try:
    from app import create_app
    app = create_app()
    print('Full app loaded', flush=True)
except Exception as e:
    import traceback
    traceback.print_exc()
    error = str(e)[:300]
    print(f'Full app failed: {error}', flush=True)

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
