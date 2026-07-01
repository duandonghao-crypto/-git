#!/usr/bin/env python3
"""
Electricity Manager v3 — PostgreSQL, Gunicorn/Waitress, Multi-user.
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

# Module-level app for gunicorn (Render)
app = create_app()
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
        print("Using Waitress")
        serve(app, host=args.host, port=args.port, threads=8)
    except ImportError:
        print("Using Flask dev server")
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()
