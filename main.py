import os
import ibm_db
from datetime import datetime, timedelta
from dotenv import load_dotenv
import functions_framework
from flask import jsonify

# 加载环境变量 (主要用于本地测试)
load_dotenv()

# --- 数据库配置 ---
# 这部分配置保持不变
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_PWD = os.getenv("DB2_PASSWORD") # 从环境变量获取密码
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

# 使用 @functions_framework.http 声明这是一个HTTP触发的云函数
@functions_framework.http
def db2_keep_alive(request):
    """
    一个由HTTP请求触发的GCP云函数。
    它会连接到DB2数据库，插入一条保活记录，并清理旧记录。
    """
    try:
        # 建立数据库连接
        conn = ibm_db.connect(conn_str, "", "")
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return jsonify({"error": "Database connection failed", "details": str(e)}), 500

    try:
        # --- 清理策略：只保留最近100条记录 ---
        # 注意：为了简化，这里移除了按日期清理的逻辑，只保留按数量清理。
        # 如果需要，可以重新加入日期清理逻辑。
        cleanup_sql = """
        DELETE FROM DB2_KEEPALIVE
        WHERE ID NOT IN (
            SELECT ID FROM (
                SELECT ID FROM DB2_KEEPALIVE
                ORDER BY RECORD_TIME DESC
                FETCH FIRST 100 ROWS ONLY
            ) AS T
        )
        """
        stmt_cleanup = ibm_db.exec_immediate(conn, cleanup_sql)
        
        # --- 插入新的保活记录 ---
        now_utc = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S.%f")
        insert_sql = "INSERT INTO DB2_KEEPALIVE (RECORD_TIME, STATUS) VALUES (?, ?)"
        stmt_insert = ibm_db.prepare(conn, insert_sql)
        ibm_db.bind_param(stmt_insert, 1, now_utc)
        ibm_db.bind_param(stmt_insert, 2, "OK")
        ibm_db.execute(stmt_insert)

        # 关闭连接
        ibm_db.close(conn)

        return jsonify({"message": "Keep-alive signal recorded successfully", "time_utc": now_utc}), 200

    except Exception as e:
        # 如果在执行SQL时出错，也要确保关闭连接
        if 'conn' in locals() and conn:
            ibm_db.close(conn)
        print(f"SQL执行出错: {e}")
        return jsonify({"error": "An error occurred during DB operation", "details": str(e)}), 500