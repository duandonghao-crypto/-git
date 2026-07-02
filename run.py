#!/usr/bin/env python3
"""
Electricity Manager v3 — PostgreSQL, Gunicorn/Waitress, Multi-user.
"""
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

from flask import Flask

# Always start with a minimal fallback app
app = Flask(__name__)

@app.route('/health')
def health():
    return 'ok'

@app.route('/')
def index():
    return 'Loading... <a href="/health">Health</a>'

# Try to replace with the full app
try:
    from app import create_app
    app = create_app()
    app.logger.info("Full app loaded successfully")
except Exception as e:
    print(f"ERROR loading full app: {e}", flush=True)
    traceback.print_exc()
    print("Using fallback app - check DATABASE_URL env var and DB connectivity", flush=True)

from config import Config
Config.PORT = int(os.environ.get('PORT', Config.PORT))


def main():
    parser = argparse.ArgumentParser(description='Electricity Manager v3')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--init-db', action='store_true')
    parser.add_argument('--host', default=Config.HOST)
    parser.add_argument('--port', type=int, default=Config.PORT)
    args = parser.parse_args()

    if args.init_db:
        from app.database import init_db
        init_db()
        print("Database initialized.")
        return

    print(f"\n{'='*50}")
    print(f"  Electricity Manager v3")
    print(f"  http://{args.host}:{args.port}")
    print(f"  DB: {Config.db_url()[:50]}...")
    print(f"{'='*50}\n")

    try:
        from waitress import serve
        serve(app, host=args.host, port=args.port, threads=8)
    except ImportError:
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()
