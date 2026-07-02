#!/usr/bin/env python3
"""Ultra minimal test - no database, just Flask"""
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return 'OK v2'

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/stats')
def stats():
    return jsonify({'active_meters': 0, 'customers': 0, 'total_transactions': 0})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8018))
    app.run(host='0.0.0.0', port=port, threaded=True)
