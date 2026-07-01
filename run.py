#!/usr/bin/env python3
"""
电费电量管理平台 v3 — PostgreSQL + Waitress
Multi-user with session-based auth.
"""
import os, sys, argparse

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

from app import create_app
from config import Config

# Module-level app for gunicorn (Render requires this)
app = create_app()

# Also update port from env (Render sets PORT env var)
Config.PORT = int(os.environ.get('PORT', Config.PORT))


def main():
    parser = argparse.ArgumentParser(description='电费电量管理平台 v3')
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

    app = create_app()
    print(f"\n{'='*50}")
    print(f"  电费电量管理平台 v3 (PostgreSQL)")
    print(f"  http://{args.host}:{args.port}")
        print(f"  DB: {Config.db_url()[:50]}...")
        print(f"{'='*50}\n")

    try:
        from waitress import serve
        print("Using Waitress (production server)")
        serve(app, host=args.host, port=args.port, threads=8)
    except ImportError:
        print("Waitress not found, using Flask dev server")
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()
