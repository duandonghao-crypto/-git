"""Stats and search routes"""
from flask import Blueprint, request, jsonify
from app.database import db_session, Config
from app.routes.auth_helper import user_id, ph

stats_bp = Blueprint('stats', __name__)


@stats_bp.route('/api/stats')
def stats():
    uid = user_id()
    p = ph()
    with db_session() as conn:
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM meters WHERE status='active' AND user_id={p}", (uid,))
        active = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM meters WHERE user_id={p}", (uid,))
        total_m = c.fetchone()[0]

        c.execute(f"SELECT MIN(year_month), MAX(year_month), MAX(year_month) FROM transactions WHERE user_id={p}", (uid,))
        r = c.fetchone()
        dr = f"{r[0]} ~ {r[1]}" if r and r[0] else "-"
        latest = r[2]

        def s(cat):
            c.execute(f"SELECT COALESCE(SUM(amount),0), COUNT(*) FROM transactions WHERE category={p} AND user_id={p}", (cat, uid))
            return c.fetchone()

        fe_exp, fe_exp_c = s('电费支')
        fe_inc, fe_inc_c = s('电费收')
        kw_exp, kw_exp_c = s('电量支')
        kw_inc, kw_inc_c = s('电量收')
        c.execute(f"SELECT COUNT(*) FROM transactions WHERE user_id={p}", (uid,))
        total_tx = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM customers WHERE user_id={p}", (uid,))
        cust_cnt = c.fetchone()[0]

        c.execute(f"SELECT status, COUNT(*), COALESCE(SUM(receivable_amount),0), COALESCE(SUM(received_amount),0) FROM receivables WHERE user_id={p} GROUP BY status", (uid,))
        rs = {r2[0]: {"cnt": r2[1], "recv": r2[2], "paid": r2[3]} for r2 in c.fetchall()}
        pend = rs.get('pending', {"cnt": 0, "recv": 0, "paid": 0})

        c.execute(f"SELECT COALESCE(SUM(CASE WHEN category='电费支' THEN amount END),0), COALESCE(SUM(CASE WHEN category='电费收' THEN amount END),0) FROM transactions WHERE year_month={p} AND user_id={p}", (latest, uid))
        lm = c.fetchone()

        return jsonify({
            "active_meters": active, "total_meters": total_m, "date_range": dr, "latest_month": latest,
            "total_fee_expense": fe_exp, "total_fee_income": fe_inc,
            "total_kwh_expense": kw_exp, "total_kwh_income": kw_inc,
            "fee_expense_count": fe_exp_c, "fee_income_count": fe_inc_c,
            "total_transactions": total_tx, "customer_count": cust_cnt,
            "pending_count": pend["cnt"],
            "pending_amount": round(pend["recv"] - pend["paid"], 2),
            "latest_month_expense": lm[0] or 0, "latest_month_income": lm[1] or 0
        })


@stats_bp.route('/api/months')
def months():
    uid = user_id()
    p = ph()
    with db_session() as conn:
        c = conn.cursor()
        c.execute(f"SELECT DISTINCT year_month FROM transactions WHERE user_id={p} ORDER BY year_month", (uid,))
        return jsonify([r[0] for r in c.fetchall()])


@stats_bp.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    month = request.args.get('month', '').strip()
    cat = request.args.get('cat', '').strip()
    meter_id = request.args.get('meter_id', '').strip()
    cust = request.args.get('customer', '').strip()
    uid = user_id()
    p = ph()

    with db_session() as conn:
        c = conn.cursor()
        args = []
        sql = f"""SELECT m.meter_id, m.location, m.usage_type, m.ownership, t.year_month, t.counterparty,
                 SUM(CASE WHEN t.category='电费支' THEN t.amount ELSE 0 END) as fee_expense,
                 SUM(CASE WHEN t.category='电量支' THEN t.amount ELSE 0 END) as kwh_expense,
                 SUM(CASE WHEN t.category='电费收' THEN t.amount ELSE 0 END) as fee_income,
                 SUM(CASE WHEN t.category='电量收' THEN t.amount ELSE 0 END) as kwh_income
                 FROM meters m LEFT JOIN transactions t ON m.meter_id=t.meter_id AND m.user_id=t.user_id
                 WHERE m.user_id={p}"""
        args.append(uid)
        if meter_id:
            sql += f" AND m.meter_id = {p}"; args.append(meter_id)
        elif q:
            like = f"%{q}%"
            sql += f" AND (m.meter_id LIKE {p} OR m.location LIKE {p} OR t.counterparty LIKE {p})"
            args.extend([like, like, like])
        if month:
            sql += f" AND (t.year_month = {p} OR t.year_month IS NULL)"; args.append(month)
        if cat:
            sql += f" AND t.category = {p}"; args.append(cat)
        if cust:
            sql += f" AND t.counterparty LIKE {p}"; args.append(f"%{cust}%")
        sql += " GROUP BY m.meter_id, m.location, m.usage_type, m.ownership, t.counterparty, t.year_month ORDER BY t.year_month DESC, m.meter_id LIMIT 500"
        try:
            c.execute(sql, args)
            return jsonify([dict(r) for r in c.fetchall() if r['year_month']])
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'sql': sql[-200:], 'detail': traceback.format_exc()[-300:]})
