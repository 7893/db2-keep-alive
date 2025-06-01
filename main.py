import os
import ibm_db
from datetime import datetime
import functions_framework
from flask import jsonify

# --- 数据库配置 ---
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_PWD = os.getenv("DB2_PASSWORD")
DB_SECURITY = "SSL"

# 构建连接字符串
conn_str = (
    f"DATABASE={DB_DATABASE};"
    f"HOSTNAME={DB_HOSTNAME};"
    f"PORT={DB_PORT};"
    f"PROTOCOL={DB_PROTOCOL};"
    f"UID={DB_UID};"
    f"PWD={DB_PWD};"
    f"SECURITY={DB_SECURITY};"
)

@functions_framework.http
def db2_keep_alive(request):
    """
    一个由HTTP请求触发的GCP云函数。
    它会连接到DB2数据库，先插入一条保活记录，再清理旧记录，确保总数不超过100。
    """
    try:
        # 建立数据库连接
        conn = ibm_db.connect(conn_str, "", "")
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return jsonify({"error": "Database connection failed", "details": str(e)}), 500

    try:
        # 第一步：先插入新的保活记录
        now_utc = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S.%f")
        insert_sql = "INSERT INTO ZZG36949.CHRONOS_RECORDS (RECORD_TIME, STATUS) VALUES (?, ?)"
        stmt_insert = ibm_db.prepare(conn, insert_sql)
        ibm_db.bind_param(stmt_insert, 1, now_utc)
        ibm_db.bind_param(stmt_insert, 2, "OK")
        ibm_db.execute(stmt_insert)

        # 第二步：再执行清理，确保只保留最新的100条
        cleanup_sql = """
        DELETE FROM ZZG36949.CHRONOS_RECORDS
        WHERE RECORD_TIME < (
            SELECT MIN(RECORD_TIME)
            FROM (
                SELECT RECORD_TIME
                FROM ZZG36949.CHRONOS_RECORDS
                ORDER BY RECORD_TIME DESC
                FETCH FIRST 100 ROWS ONLY
            ) AS T
        )
        """
        stmt_cleanup = ibm_db.exec_immediate(conn, cleanup_sql)

        # 关闭连接
        ibm_db.close(conn)

        return jsonify({"message": "Keep-alive recorded, total records capped at 100.", "time_utc": now_utc}), 200

    except Exception as e:
        # 如果在执行SQL时出错，也要确保关闭连接
        if 'conn' in locals() and conn:
            ibm_db.close(conn)
        print(f"SQL执行出错: {e}")
        return jsonify({"error": "An error occurred during DB operation", "details": str(e)}), 500