"""
Flask application factory with logging, auth, CORS.
"""
import os, sys, logging, shutil
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from config import Config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__, static_folder=Config.STATIC_DIR, static_url_path='')
    app.config.from_object(config_class)
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    CORS(app, supports_credentials=True)

    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.StreamHandler(), logging.FileHandler(Config.LOG_FILE, encoding='utf-8')]
    )

    # ===== Auth APIs =====
    @app.route('/api/auth/login', methods=['POST'])
    def auth_login():
        data = request.get_json(force=True)
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'message': '请输入名字'}), 400

        from app.database import get_db
        conn = get_db()
        try:
            c = conn.cursor()
            if Config.DB_TYPE == "sqlite":
                c.execute("SELECT id FROM users WHERE name=?", (name,))
            else:
                c.execute("SELECT id FROM users WHERE name=%s", (name,))
            row = c.fetchone()
            if not row:
                if Config.DB_TYPE == "sqlite":
                    c.execute("INSERT INTO users (name) VALUES (?)", (name,))
                else:
                    c.execute("INSERT INTO users (name) VALUES (%s) ON CONFLICT DO NOTHING", (name,))
                    c.execute("SELECT id FROM users WHERE name=%s", (name,))
                    row = c.fetchone()
                if not row:
                    return jsonify({'success': False, 'message': '创建用户失败'}), 500
                conn.commit()
            user_id = row[0] if isinstance(row, tuple) else row['id']
        finally:
            conn.close()

        session['user_id'] = user_id
        session['user_name'] = name
        return jsonify({'success': True, 'user_id': user_id, 'user_name': name})

    @app.route('/api/auth/me')
    def auth_me():
        uid = session.get('user_id')
        uname = session.get('user_name')
        return jsonify({'user_id': uid, 'user_name': uname})

    @app.route('/api/auth/logout', methods=['POST'])
    def auth_logout():
        session.clear()
        return jsonify({'success': True})

    @app.route('/api/auth/users')
    def auth_users():
        from app.database import get_db
        conn = get_db()
        try:
            c = conn.cursor()
            if Config.DB_TYPE == "sqlite":
                c.execute("SELECT id, name FROM users ORDER BY id")
            else:
                c.execute("SELECT id, name FROM users ORDER BY id")
            rows = c.fetchall()
            if Config.DB_TYPE == "sqlite":
                return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])
            else:
                keys = [d[0] for d in c.description]
                return jsonify([dict(zip(keys, r)) for r in rows])
        finally:
            conn.close()

    # ===== Current user helper =====
    def current_user_id():
        return session.get('user_id', 1)

    @app.before_request
    def ensure_user():
        if request.endpoint and '/api/' in request.path and '/api/auth/' not in request.path:
            if not session.get('user_id'):
                if request.path.startswith('/api/') and request.method in ('POST', 'GET'):
                    pass  # Allow public APIs

    # ===== Static routes =====
    @app.route('/')
    def index():
        from flask import send_from_directory
        try:
            return send_from_directory(Config.STATIC_DIR, 'index.html')
        except Exception:
            return 'OK - Electricity Manager v3<br><a href="/电费支出给国网.html">支出</a> | <a href="/收费录入.html">收费</a>'

    @app.route('/<path:filename>')
    def serve_static(filename):
        if not filename or filename == '/':
            return index()
        from flask import send_from_directory
        fp = os.path.join(Config.STATIC_DIR, filename)
        if os.path.exists(fp):
            return send_from_directory(Config.STATIC_DIR, filename)
        return '', 404

    @app.route('/attachments/<path:filename>')
    def serve_attachment(filename):
        from flask import send_from_directory
        filepath = os.path.join(Config.ATTACHMENTS_DIR, filename)
        if not os.path.exists(filepath):
            return '', 404
        return send_from_directory(Config.ATTACHMENTS_DIR, filename)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        import traceback
        app.logger.error("Internal error:\n" + traceback.format_exc())
        return jsonify({'error': 'Internal server error'}), 500

    # ===== Register blueprints FIRST (routes available even if DB fails) =====
    from app.routes.stats import stats_bp
    from app.routes.meters import meters_bp
    from app.routes.customers import customers_bp
    from app.routes.receivables import receivables_bp
    from app.routes.backup import backup_bp
    from app.routes.version import version_bp
    from app.routes.expense import expense_bp
    from app.routes.charge import charge_bp

    app.register_blueprint(stats_bp)
    app.register_blueprint(meters_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(receivables_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(version_bp)
    app.register_blueprint(expense_bp)
    app.register_blueprint(charge_bp)

    # Health check
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

    # ===== Init directories and DB (try, don't crash) =====
    with app.app_context():
        try:
            os.makedirs(Config.ATTACHMENTS_DIR, exist_ok=True)
            os.makedirs(Config.BACKUP_DIR, exist_ok=True)
            os.makedirs(Config.VERSIONS_DIR, exist_ok=True)
            src = os.path.join(Config.STATIC_DIR, '_browse.html')
            dst = os.path.join(Config.ATTACHMENTS_DIR, '_browse.html')
            if os.path.isfile(src) and not os.path.isfile(dst):
                shutil.copy2(src, dst)
            from app.database import init_db
            init_db()
            app.logger.info("Database initialized.")
        except Exception as e:
            app.logger.error(f"Init error (may be OK on first deploy): {e}")

    return app


def get_current_user_id():
    """Importable helper for routes to get current user_id."""
    from flask import session
    return session.get('user_id', 1)
