"""Charge entry routes - PostgreSQL"""
import os, re, time, shutil
from datetime import datetime
from flask import Blueprint, request, jsonify
from config import Config
from app.database import db_session
from app.routes.auth_helper import user_id
from app.utils.helpers import strip_meter_id

charge_bp = Blueprint('charge', __name__)


@charge_bp.route('/api/check_meter_changes', methods=['POST'])
def check_meter_changes():
    data = request.get_json(force=True)
    month = data.get('month', '')
    rows = data.get('rows', [])
    uid = user_id()

    with db_session() as conn:
        c = conn.cursor()
        conflicts = []
        warnings = []
        for row in rows:
            ent = (row.get('entName') or '').strip()
            meter = strip_meter_id(row.get('hao') or '')
            if not ent or not meter:
                continue

            c.execute("""SELECT cm.meter_id, cm.valid_from, cm.valid_to
                         FROM customer_meters cm JOIN customers cus ON cm.customer_id=cus.id
                         WHERE cus.name=%s AND cus.user_id=%s ORDER BY cm.valid_from DESC""",
                      (ent, uid))
            history = c.fetchall()
            if not history:
                warnings.append({'msg': f'{ent}: 新企业，将创建户号关联 ({meter})'})
                continue

            historical_meters = set(h['meter_id'] for h in history)
            if meter not in historical_meters:
                last_meter = history[0]['meter_id'] if history else '未知'
                last_month = ''
                if history:
                    old_meter = history[0]['meter_id']
                    c.execute("""SELECT MAX(year_month) FROM transactions
                                 WHERE meter_id=%s AND counterparty=%s AND category IN ('电费收','电量收') AND user_id=%s""",
                              (old_meter, ent, uid))
                    lm = c.fetchone()
                    last_month = lm[0] if lm and lm[0] else '未知'
                conflicts.append({
                    'enterprise': ent, 'currentMeter': meter,
                    'historicalMeter': last_meter, 'lastMonth': last_month, 'month': month
                })
    return jsonify({'conflicts': conflicts, 'warnings': warnings})


@charge_bp.route('/api/upload_charge', methods=['POST'])
def upload_charge():
    data = request.get_json(force=True)
    month = data.get('month', '')
    rows = data.get('rows', [])
    apply_changes = data.get('apply_meter_changes', False)
    uid = user_id()

    os.makedirs(Config.BACKUP_DIR, exist_ok=True)
    # Cloud: skip file backup (Neon handles this)
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(Config.BACKUP_DIR, f'auto_upload_{ts}.db')
        if hasattr(Config, 'SQLITE_PATH') and os.path.exists(Config.SQLITE_PATH):
            shutil.copy2(Config.SQLITE_PATH, backup_path)
        with open(os.path.join(Config.BACKUP_DIR, 'last_upload_backup.txt'), 'w') as f:
            f.write(backup_path)
    except:
        pass

    with db_session() as conn:
        c = conn.cursor()
        count = 0
        changes = []

        for row in rows:
            ent = (row.get('entName') or '').strip()
            meter = strip_meter_id(row.get('hao') or '')
            fee = float(row.get('feeAmount') or 0)
            kwh = float(row.get('kwhAmount') or 0)

            if not ent or not meter:
                continue
            if fee == 0 and kwh == 0:
                continue

            c.execute('SELECT id FROM customers WHERE name=%s AND user_id=%s', (ent, uid))
            cust = c.fetchone()
            if not cust:
                c.execute('INSERT INTO customers (name, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (ent, uid))
                c.execute('SELECT id FROM customers WHERE name=%s AND user_id=%s', (ent, uid))
                cust = c.fetchone()
            cust_id = cust[0] if cust else None
            if not cust_id:
                continue

            c.execute("SELECT id FROM customer_meters WHERE customer_id=%s AND meter_id=%s AND valid_to IS NULL", (cust_id, meter))
            link = c.fetchone()
            if not link and apply_changes:
                c.execute('UPDATE customer_meters SET valid_to=%s WHERE customer_id=%s AND valid_to IS NULL', (month, cust_id))
                c.execute("INSERT INTO customer_meters (customer_id, meter_id, valid_from) VALUES (%s, %s, %s)", (cust_id, meter, month))
                changes.append({'msg': f'{ent}: 户号变更为 {meter} (自 {month} 起)'})
            elif not link:
                c.execute("INSERT INTO customer_meters (customer_id, meter_id, valid_from) VALUES (%s, %s, %s)", (cust_id, meter, month))

            c.execute("DELETE FROM transactions WHERE meter_id=%s AND year_month=%s AND counterparty=%s AND category IN ('电费收','电量收') AND user_id=%s",
                      (meter, month, ent, uid))

            if fee > 0:
                c.execute("INSERT INTO transactions (meter_id, year_month, category, amount, counterparty, user_id) VALUES (%s, %s, '电费收', %s, %s, %s)", (meter, month, fee, ent, uid))
                count += 1
            if kwh > 0:
                c.execute("INSERT INTO transactions (meter_id, year_month, category, amount, counterparty, user_id) VALUES (%s, %s, '电量收', %s, %s, %s)", (meter, month, kwh, ent, uid))
                count += 1

            full_meter = f'[{meter}]'
            if fee > 0:
                c.execute("DELETE FROM receivables WHERE meter_id=%s AND year_month=%s AND customer_name=%s AND user_id=%s",
                          (full_meter, month, ent, uid))
                c.execute("INSERT INTO receivables (meter_id, year_month, receivable_amount, customer_name, status, user_id) VALUES (%s, %s, %s, %s, 'pending', %s)", (full_meter, month, fee, ent, uid))

        conn.commit()
    return jsonify({'success': True, 'count': count, 'changes': changes, 'message': f'成功上传 {count} 条记录，已自动创建应收'})
