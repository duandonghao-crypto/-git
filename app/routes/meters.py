"""Meter management routes"""
import sqlite3
from flask import Blueprint, request, jsonify
from app.database import db_session
from app.routes.auth_helper import user_id, ph

meters_bp = Blueprint('meters', __name__)


@meters_bp.route('/api/meters')
def list_meters():
    uid = user_id()
    p = ph()
    with db_session() as conn:
        c = conn.cursor()
        c.execute(f"""SELECT m.*,
                     (SELECT COUNT(*) FROM transactions WHERE meter_id=m.meter_id AND user_id={p}) as tx_count,
                     (SELECT MAX(year_month) FROM transactions WHERE meter_id=m.meter_id AND user_id={p}) as latest_month,
                     (SELECT COUNT(*) FROM customer_meters WHERE meter_id=m.meter_id AND valid_to IS NULL) as customer_count
                     FROM meters m WHERE m.user_id={p} ORDER BY m.meter_id""",
                 (uid, uid, uid))
        return jsonify([dict(r) for r in c.fetchall()])


@meters_bp.route('/api/meter_detail')
def meter_detail():
    mid = request.args.get('meter_id', '')
    uid = user_id()
    p = ph()
    with db_session() as conn:
        c = conn.cursor()
        c.execute(f"SELECT * FROM meters WHERE meter_id={p} AND user_id={p}", (mid, uid))
        info = dict(c.fetchone() or {})

        c.execute(f"""SELECT cm.*, c.name as customer_name FROM customer_meters cm
                     JOIN customers c ON cm.customer_id=c.id
                     WHERE cm.meter_id={p} ORDER BY cm.valid_from DESC""", (mid,))
        ch = [dict(r) for r in c.fetchall()]

        c.execute(f"""SELECT year_month, counterparty,
                     SUM(CASE WHEN category='电费支' THEN amount END) as fee_expense,
                     SUM(CASE WHEN category='电量支' THEN amount END) as kwh_expense,
                     SUM(CASE WHEN category='电费收' THEN amount END) as fee_income,
                     SUM(CASE WHEN category='电量收' THEN amount END) as kwh_income
                     FROM transactions WHERE meter_id={p} AND user_id={p}
                     GROUP BY year_month, counterparty ORDER BY year_month DESC LIMIT 100""",
                 (mid, uid))
        monthly = [dict(r) for r in c.fetchall()]

        c.execute(f"SELECT * FROM receivables WHERE meter_id={p} AND user_id={p} ORDER BY year_month DESC LIMIT 24", (mid, uid))
        recv = [dict(r) for r in c.fetchall()]

        c.execute(f"SELECT COALESCE(SUM(CASE WHEN category='电费支' THEN amount END),0), COALESCE(SUM(CASE WHEN category='电费收' THEN amount END),0) FROM transactions WHERE meter_id={p} AND user_id={p}", (mid, uid))
        te_ti = c.fetchone()

    for m in monthly:
        fe, fi = m.get('fee_expense') or 0, m.get('fee_income') or 0
        m['anomaly'] = bool(fe > 0 and fi == 0)
        m['counterparty'] = m.get('counterparty') or ''

    return jsonify({
        "info": info, "customer_history": ch, "monthly": monthly,
        "receivables": recv,
        "total_expense": te_ti[0] or 0, "total_income": te_ti[1] or 0
    })


@meters_bp.route('/api/meter_add', methods=['POST'])
def meter_add():
    from app.utils.helpers import strip_meter_id
    data = request.get_json(force=True)
    meter_id = strip_meter_id(data['meter_id'])
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        try:
            if Config.DB_TYPE == 'sqlite':
                c.execute("INSERT INTO meters (meter_id,location,usage_type,ownership,status,user_id) VALUES (?,?,?,?,'active',?)",
                          (meter_id, data.get('location', ''), data.get('usage_type', ''), data.get('ownership', ''), uid))
                c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('add','meters',?,?)",
                          (f"Added {meter_id}", uid))
            else:
                c.execute("INSERT INTO meters (meter_id,location,usage_type,ownership,status,user_id) VALUES (%s,%s,%s,%s,'active',%s)",
                          (meter_id, data.get('location', ''), data.get('usage_type', ''), data.get('ownership', ''), uid))
                c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('add','meters',%s,%s)",
                          (f"Added {meter_id}", uid))
            conn.commit()
            return jsonify({"success": True, "message": "户号添加成功"})
        except Exception as e:
            msg = "户号已存在" if "violat" in str(e).lower() or "UNIQUE" in str(e).upper() else str(e)
            return jsonify({"success": False, "message": msg}), 400


@meters_bp.route('/api/meter_update', methods=['POST'])
def meter_update():
    data = request.get_json(force=True)
    uid = user_id()
    p = ph()
    with db_session() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE meters SET location={p},usage_type={p},ownership={p},updated_at=datetime('now','localtime') WHERE meter_id={p} AND user_id={p}",
                  (data.get('location', ''), data.get('usage_type', ''), data.get('ownership', ''), data['meter_id'], uid))
        if Config.DB_TYPE == 'sqlite':
            c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('update','meters',?,?)",
                      (f"Updated {data['meter_id']}", uid))
        else:
            c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('update','meters',%s,%s)",
                      (f"Updated {data['meter_id']}", uid))
        conn.commit()
    return jsonify({"success": True, "message": "信息已更新"})


@meters_bp.route('/api/meter_toggle', methods=['POST'])
def meter_toggle():
    data = request.get_json(force=True)
    ns = data.get('status', 'inactive')
    uid = user_id()
    p = ph()
    with db_session() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE meters SET status={p},updated_at=datetime('now','localtime') WHERE meter_id={p} AND user_id={p}",
                  (ns, data['meter_id'], uid))
        action = 'deactivate' if ns == 'inactive' else 'reactivate'
        if Config.DB_TYPE == 'sqlite':
            c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES (?,?,?,?)",
                      (action, 'meters', f"{data['meter_id']} -> {ns}", uid))
        else:
            c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES (%s,%s,%s,%s)",
                      (action, 'meters', f"{data['meter_id']} -> {ns}", uid))
        conn.commit()
    msg = '户号已停用' if ns == 'inactive' else '户号已恢复'
    return jsonify({"success": True, "message": msg})
