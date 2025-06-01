from flask import Flask, request, jsonify, render_template_string
import ibm_db
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)

# 东八区时区定义
TZ = timezone(timedelta(hours=8))

# --- Db2 配置 ---
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_SECURITY = "SSL"
DB_PWD = os.getenv("DB2_PASSWORD", "")

@app.route("/", methods=["GET"])
def keep_alive_api():
    return get_status(json_mode=True)

@app.route("/view", methods=["GET"])
def keep_alive_page():
    return get_status(json_mode=False)

def get_status(json_mode=True):
    conn = None
    try:
        dsn = (
            f"DATABASE={DB_DATABASE};"
            f"HOSTNAME={DB_HOSTNAME};"
            f"PORT={DB_PORT};"
            f"PROTOCOL={DB_PROTOCOL};"
            f"UID={DB_UID};"
            f"PWD={DB_PWD};"
            f"Security={DB_SECURITY};"
        )
        conn = ibm_db.connect(dsn, "", "")
        sql = """
        SELECT COUNT(*) AS TOTAL,
               MIN(record_time) AS OLDEST,
               MAX(record_time) AS NEWEST
        FROM chronos_records
        """
        stmt = ibm_db.exec_immediate(conn, sql)
        result = ibm_db.fetch_assoc(stmt)
        if not result:
            raise Exception("No result returned.")

        total = result["TOTAL"]
        oldest = parse_and_format_time(result["OLDEST"])
        newest = parse_and_format_time(result["NEWEST"])

        if json_mode:
            return jsonify(success=True, total=total, oldest=oldest, newest=newest)
        else:
            html = f"""
            <html><head><title>Db2 保活状态</title></head><body>
            <h2>Db2 保活统计页面</h2>
            <p><strong>总记录数：</strong> {total}</p>
            <p><strong>最早记录时间：</strong> {oldest}</p>
            <p><strong>最新记录时间：</strong> {newest}</p>
            </body></html>
            """
            return render_template_string(html)

    except Exception as e:
        if json_mode:
            return jsonify(success=False, error=str(e)), 500
        else:
            return render_template_string(f"<h2>出错了：{str(e)}</h2>"), 500
    finally:
        if conn:
            ibm_db.close(conn)

def parse_and_format_time(db_time_str):
    try:
        # 输入格式如：2025-06-01-06.10.05.667405
        ts = datetime.strptime(db_time_str, "%Y-%m-%d-%H.%M.%S.%f")
        ts = ts.replace(tzinfo=timezone.utc).astimezone(TZ)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return db_time_str

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
