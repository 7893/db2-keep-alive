from flask import Flask, jsonify
import ibm_db
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# IBM Db2 连接参数
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_PWD = os.environ.get("DB2_PASSWORD")
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

@app.route("/ping")
def ping():
    try:
        conn = ibm_db.connect(conn_str, "", "")

        # 删除早于7天或非最新100条以外的记录
        delete_sql = """
        DELETE FROM DB2_KEEPALIVE
        WHERE ID NOT IN (
            SELECT ID FROM DB2_KEEPALIVE
            ORDER BY RECORD_TIME DESC
            FETCH FIRST 100 ROWS ONLY
        )
        OR RECORD_TIME < ?
        """
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d-%H.%M.%S.%f")
        stmt = ibm_db.prepare(conn, delete_sql)
        ibm_db.bind_param(stmt, 1, seven_days_ago)
        ibm_db.execute(stmt)

        # 插入当前记录
        now = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S.%f")
        insert_sql = "INSERT INTO DB2_KEEPALIVE (RECORD_TIME, STATUS) VALUES (?, ?)"
        stmt = ibm_db.prepare(conn, insert_sql)
        ibm_db.bind_param(stmt, 1, now)
        ibm_db.bind_param(stmt, 2, "OK")
        ibm_db.execute(stmt)

        return jsonify({"message": "Keep-alive recorded", "time": now}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            ibm_db.close(conn)
