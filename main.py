from flask import Flask, jsonify
import ibm_db
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# 东八区（UTC+8）
tz = timezone(timedelta(hours=8))

DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_PWD = os.getenv("DB2_PASSWORD")
DB_SECURITY = "SSL"

conn_str = (
    f"DATABASE={DB_DATABASE};"
    f"HOSTNAME={DB_HOSTNAME};"
    f"PORT={DB_PORT};"
    f"PROTOCOL={DB_PROTOCOL};"
    f"UID={DB_UID};"
    f"PWD={DB_PWD};"
    f"SECURITY={DB_SECURITY};"
)

@app.route("/")
def index():
    try:
        conn = ibm_db.connect(conn_str, "", "")
        sql = "SELECT ID, RECORD_TIME, STATUS FROM DB2_KEEPALIVE ORDER BY ID DESC"
        stmt = ibm_db.exec_immediate(conn, sql)

        rows = []
        while True:
            row = ibm_db.fetch_assoc(stmt)
            if not row:
                break
            rows.append(row)

        total = len(rows)
        latest = rows[0]['RECORD_TIME'] if total else None
        earliest = rows[-1]['RECORD_TIME'] if total else None

        # 构建 HTML 页面
        html = "<html><head><title>DB2 Keep Alive</title></head><body style='font-family:sans-serif'>"
        html += "<h2>DB2 Keep Alive Status</h2>"

        if total > 0:
            latest_dt = datetime.strptime(latest, "%Y-%m-%d-%H.%M.%S.%f").astimezone(tz)
            earliest_dt = datetime.strptime(earliest, "%Y-%m-%d-%H.%M.%S.%f").astimezone(tz)
            html += f"<p><strong>Total Records:</strong> {total}</p>"
            html += f"<p><strong>Latest Record Time:</strong> {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}</p>"
            html += f"<p><strong>Earliest Record Time:</strong> {earliest_dt.strftime('%Y-%m-%d %H:%M:%S')}</p>"
        else:
            html += "<p>No data available.</p>"

        html += "</body></html>"
        return html

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            ibm_db.close(conn)

@app.route("/ping")
def ping():
    try:
        conn = ibm_db.connect(conn_str, "", "")

        # 删除策略：只保留最近100条或7天内的数据
        cleanup_sql = """
        DELETE FROM DB2_KEEPALIVE
        WHERE ID NOT IN (
            SELECT ID FROM DB2_KEEPALIVE
            ORDER BY RECORD_TIME DESC
            FETCH FIRST 100 ROWS ONLY
        )
        OR RECORD_TIME < ?
        """
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d-%H.%M.%S.%f")
        stmt = ibm_db.prepare(conn, cleanup_sql)
        ibm_db.bind_param(stmt, 1, seven_days_ago)
        ibm_db.execute(stmt)

        # 插入保活记录
        now = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S.%f")
        insert_sql = "INSERT INTO DB2_KEEPALIVE (RECORD_TIME, STATUS) VALUES (?, ?)"
        stmt = ibm_db.prepare(conn, insert_sql)
        ibm_db.bind_param(stmt, 1, now)
        ibm_db.bind_param(stmt, 2, "OK")
        ibm_db.execute(stmt)

        return jsonify({"message": "Keep-alive signal recorded", "time": now}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            ibm_db.close(conn)

@app.route("/debug")
def debug():
    return jsonify({
        "PORT": os.getenv("PORT"),
        "DB2_PASSWORD_SET": bool(os.getenv("DB2_PASSWORD")),
        "IBM_DB_HOME": os.getenv("IBM_DB_HOME"),
        "LD_LIBRARY_PATH": os.getenv("LD_LIBRARY_PATH"),
        "CurrentTimeUTC": datetime.utcnow().isoformat()
    })

# 本地调试时使用，仅 Cloud Run 部署时不执行
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting development server on port {port}...")
    app.run(host="0.0.0.0", port=port)
