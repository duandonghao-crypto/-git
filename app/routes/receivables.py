"""Receivables and payment history - PostgreSQL"""
from flask import Blueprint, request, jsonify
from app.database import db_session, Config
from app.routes.auth_helper import user_id

receivables_bp = Blueprint('receivables', __name__)


@receivables_bp.route('/api/receivables')
def list_receivables():
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        c.execute("""SELECT r.*, m.location FROM receivables r
                     LEFT JOIN meters m ON REPLACE(REPLACE(r.meter_id,'[',''),']','')=m.meter_id AND m.user_id=%s
                     WHERE r.user_id=%s
                     ORDER BY CASE r.status WHEN 'pending' THEN 0 WHEN 'partial' THEN 1 ELSE 2 END, r.year_month DESC""",
                  (uid, uid))
        return jsonify([dict(r) for r in c.fetchall()])


@receivables_bp.route('/api/receivable_create', methods=['POST'])
def receivable_create():
    data = request.get_json(force=True)
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO receivables (meter_id,year_month,receivable_amount,received_amount,customer_name,status,confirmed_date,note,user_id) VALUES (%s,%s,%s,0,%s,'pending',%s,%s,%s)",
                  (data['meter_id'], data['year_month'], data['receivable_amount'],
                   data.get('customer_name', ''), data.get('confirmed_date', ''), data.get('note', ''), uid))
        c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('create','receivables',%s,%s)",
                  (f"AR: {data['meter_id']} {data['year_month']} {data['receivable_amount']}", uid))
        conn.commit()
        rid = c.fetchone() if hasattr(c, 'lastrowid') else None
        if rid:
            rid = rid[0] if isinstance(rid, tuple) else rid['id']
    return jsonify({"success": True, "message": "应收账款已创建", "id": rid})


@receivables_bp.route('/api/receivable_pay', methods=['POST'])
def receivable_pay():
    data = request.get_json(force=True)
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM receivables WHERE id=%s AND user_id=%s", (data['id'], uid))
        r = c.fetchone()
        if not r:
            return jsonify({"success": False}), 404

        recv = float(r['received_amount'] or 0) + float(data.get('amount', 0))
        total = float(r['receivable_amount'] or 0)
        if recv >= total:
            status, recv = 'paid', total
        elif recv > 0:
            status = 'partial'
        else:
            status = 'pending'

        c.execute("UPDATE receivables SET received_amount=%s,status=%s,received_date=%s,updated_at=NOW() WHERE id=%s AND user_id=%s",
                  (recv, status, data.get('received_date', ''), data['id'], uid))
        c.execute("INSERT INTO payment_history (receivable_id, meter_id, year_month, amount, payment_date, customer_name) VALUES (%s, %s, %s, %s, %s, %s)",
                  (data['id'], r['meter_id'], r['year_month'], data.get('amount', 0),
                   data.get('received_date', ''), r['customer_name']))
        c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('pay','receivables',%s,%s)",
                  (f"Payment #{data['id']}: +{data.get('amount', 0)} = {recv}/{total}", uid))
        conn.commit()
    return jsonify({"success": True, "message": "到账记录成功", "status": status, "received": recv, "total": total})


@receivables_bp.route('/api/receivable_delete', methods=['POST'])
def receivable_delete():
    data = request.get_json(force=True)
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM receivables WHERE id=%s AND user_id=%s", (data['id'], uid))
        c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('delete','receivables',%s,%s)",
                  (f"Deleted #{data['id']}", uid))
        conn.commit()
    return jsonify({"success": True, "message": "已删除"})


@receivables_bp.route('/api/payment_history')
def payment_history():
    uid = user_id()
    recv_id = request.args.get('receivable_id', '')
    with db_session() as conn:
        c = conn.cursor()
        if recv_id:
            c.execute("SELECT ph.* FROM payment_history ph JOIN receivables r ON ph.receivable_id=r.id WHERE ph.receivable_id=%s AND r.user_id=%s ORDER BY ph.id", (recv_id, uid))
        else:
            c.execute("SELECT ph.* FROM payment_history ph JOIN receivables r ON ph.receivable_id=r.id WHERE r.user_id=%s ORDER BY ph.id DESC", (uid,))
        return jsonify([dict(r) for r in c.fetchall()])
