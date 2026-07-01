"""Customer management - PostgreSQL"""
from flask import Blueprint, request, jsonify
from app.database import db_session
from app.routes.auth_helper import user_id

customers_bp = Blueprint('customers', __name__)


@customers_bp.route('/api/customers')
def list_customers():
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        c.execute("""SELECT c.id, c.name, STRING_AGG(cm.meter_id, ', ') as meters,
                     COUNT(CASE WHEN cm.valid_to IS NULL THEN 1 END) as active_links,
                     COUNT(cm.id) as total_links
                     FROM customers c LEFT JOIN customer_meters cm ON c.id=cm.customer_id
                     WHERE c.user_id=%s
                     GROUP BY c.id ORDER BY c.name""", (uid,))
        return jsonify([dict(r) for r in c.fetchall()])


@customers_bp.route('/api/customer_detail')
def customer_detail():
    cid = request.args.get('id', '')
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM customers WHERE id=%s", (cid,))
        cust = dict(c.fetchone() or {})
        c.execute("""SELECT cm.*, m.location FROM customer_meters cm
                     LEFT JOIN meters m ON cm.meter_id=m.meter_id
                     WHERE cm.customer_id=%s ORDER BY cm.valid_from DESC""", (cid,))
        links = [dict(r) for r in c.fetchall()]
    for lk in links:
        lk['current'] = (lk.get('valid_to') is None)
    return jsonify({"customer": cust, "links": links})


@customers_bp.route('/api/customer_meters')
def customer_meters_by_meter():
    mid = request.args.get('meter_id', '')
    with db_session() as conn:
        c = conn.cursor()
        c.execute("""SELECT c.id, c.name FROM customers c
                     JOIN customer_meters cm ON c.id=cm.customer_id
                     WHERE cm.meter_id=%s AND cm.valid_to IS NULL ORDER BY c.name""", (mid,))
        return jsonify([dict(r) for r in c.fetchall()])


@customers_bp.route('/api/customer_add', methods=['POST'])
def customer_add():
    from app.utils.helpers import strip_meter_id
    data = request.get_json(force=True)
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO customers (name, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (data['name'], uid))
            c.execute("SELECT id FROM customers WHERE name=%s AND user_id=%s", (data['name'], uid))
            row = c.fetchone()
            if not row:
                return jsonify({"success": False, "message": "企业名已存在"}), 400
            cid = row[0]
            if data.get('meter_id'):
                c.execute("INSERT INTO customer_meters (customer_id,meter_id,valid_from,note) VALUES (%s,%s,%s,%s)",
                          (cid, strip_meter_id(data['meter_id']), data.get('valid_from', ''), data.get('note', '')))
            c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('add','customers',%s,%s)",
                      (f"New: {data['name']}", uid))
            conn.commit()
            return jsonify({"success": True, "message": f"企业 {data['name']} 已创建", "id": cid})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500


@customers_bp.route('/api/customer_rename', methods=['POST'])
def customer_rename():
    data = request.get_json(force=True)
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM customers WHERE id=%s", (data['id'],))
        old = c.fetchone()
        c.execute("UPDATE customers SET name=%s WHERE id=%s", (data['name'], data['id']))
        c.execute("INSERT INTO audit_log (action,table_name,detail) VALUES ('rename','customers',%s)",
                  (f"{old[0]} -> {data['name']}",))
        conn.commit()
    return jsonify({"success": True, "message": f"已改名为 {data['name']}"})


@customers_bp.route('/api/customer_link', methods=['POST'])
def customer_link():
    from app.utils.helpers import strip_meter_id
    data = request.get_json(force=True)
    uid = user_id()
    with db_session() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO customer_meters (customer_id,meter_id,valid_from,note) VALUES (%s,%s,%s,%s)",
                      (data['customer_id'], strip_meter_id(data['meter_id']), data.get('valid_from', ''), data.get('note', '')))
            c.execute("INSERT INTO audit_log (action,table_name,detail,user_id) VALUES ('link','customer_meters',%s,%s)",
                      (f"Cust {data['customer_id']} -> {strip_meter_id(data['meter_id'])}", uid))
            conn.commit()
            return jsonify({"success": True, "message": "已关联到户号"})
        except Exception as e:
            return jsonify({"success": False, "message": f"关联失败: {str(e)}"}), 400


@customers_bp.route('/api/customer_unlink', methods=['POST'])
def customer_unlink():
    data = request.get_json(force=True)
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE customer_meters SET valid_to=%s WHERE id=%s", (data.get('valid_to', ''), data['id']))
        c.execute("INSERT INTO audit_log (action,table_name,detail) VALUES ('unlink','customer_meters',%s)",
                  (f"Unlinked #{data['id']}",))
        conn.commit()
    return jsonify({"success": True, "message": "已解绑"})
