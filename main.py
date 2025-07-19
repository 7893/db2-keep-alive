import os
import ibm_db
from datetime import datetime, timedelta
from flask import escape

# --- HTML 模板 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DB2 Keep-Alive Status</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background-color: #f0f2f5; padding: 20px; box-sizing: border-box; }}
        .container {{ text-align: center; background-color: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 600px; width: 100%; }}
        .status {{ font-size: 24px; font-weight: bold; padding: 10px 20px; border-radius: 50px; color: white; display: inline-block; margin-bottom: 20px; }}
        .ok {{ background-color: #28a745; }}
        .error {{ background-color: #dc3545; }}
        .info {{ margin-top: 20px; font-size: 16px; color: #333; }}
        .info p {{ margin: 8px 0; }}
        .info strong {{ color: #000; }}
        .details {{ font-size: 14px; color: #666; margin-top: 15px; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #888; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>DB2 Keep-Alive Status</h1>
        <p class="status {status_class}">{status_message}</p>
        <div class="info">
            <p><strong>最新心跳时间:</strong> {last_heartbeat}</p>
            <p><strong>数据库记录总数:</strong> {total_records}</p>
        </div>
        <div class="details">
            <p>{cleanup_message}</p>
        </div>
        <div class="footer">
            <p>页面自动刷新于: {current_time} (UTC)</p>
        </div>
    </div>
</body>
</html>
"""

def get_db_connection():
    """建立并返回数据库连接"""
    try:
        conn_str = os.getenv('DB2_CONNECTION_STRING')
        if not conn_str:
            raise ValueError("DB2_CONNECTION_STRING 环境变量未设置")
        return ibm_db.connect(conn_str, "", "")
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return None

def perform_cleanup(conn):
    """执行旧记录清理"""
    try:
        # 计算6个月前的时间点
        six_months_ago = datetime.utcnow() - timedelta(days=180)
        cutoff_time = six_months_ago.strftime('%Y-%m-%d-%H.%M.%S.%f')
        
        # 保留的最新记录数量
        retention_count = 262144

        # 找出需要删除的记录ID
        # 条件: 时间早于6个月前 且 不在最新的262144条记录中
        sql_find_to_delete = f"""
            SELECT ID FROM ZZG36949.CHRONOS_RECORDS
            WHERE RECORD_TIME < '{cutoff_time}'
            AND ID NOT IN (
                SELECT ID FROM ZZG36949.CHRONOS_RECORDS
                ORDER BY RECORD_TIME DESC
                FETCH FIRST {retention_count} ROWS ONLY
            )
            FETCH FIRST 1000 ROWS ONLY
        """
        
        stmt_find = ibm_db.exec_immediate(conn, sql_find_to_delete)
        ids_to_delete = []
        while True:
            row = ibm_db.fetch_tuple(stmt_find)
            if not row:
                break
            ids_to_delete.append(str(row[0]))

        if not ids_to_delete:
            return "无需清理旧记录。"

        # 执行删除
        id_list = ",".join(ids_to_delete)
        sql_delete = f"DELETE FROM ZZG36949.CHRONOS_RECORDS WHERE ID IN ({id_list})"
        stmt_delete = ibm_db.exec_immediate(conn, sql_delete)
        
        deleted_count = len(ids_to_delete)
        print(f"成功删除 {deleted_count} 条旧记录。")
        return f"成功删除 {deleted_count} 条旧记录。"

    except Exception as e:
        print(f"清理记录时出错: {e}")
        return f"清理记录时出错: {e}"


def db2_keep_alive(request):
    """
    云函数主入口。
    1. 清理旧记录。
    2. 插入新心跳。
    3. 查询状态并返回HTML页面。
    """
    conn = get_db_connection()
    if not conn:
        return HTML_TEMPLATE.format(
            status_class="error",
            status_message="数据库连接失败",
            last_heartbeat="N/A",
            total_records="N/A",
            cleanup_message="数据库连接失败，无法执行清理。",
            current_time=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ), 500

    # 1. 执行清理机制
    cleanup_msg = perform_cleanup(conn)

    # 2. 插入新心跳记录
    status = "OK"
    error_message = ""
    try:
        utc_now = datetime.utcnow()
        query_insert = "INSERT INTO ZZG36949.CHRONOS_RECORDS (RECORD_TIME, STATUS, ERROR_MESSAGE, TRIGGER_TYPE, RUNTIME_VERSION, MEMORY_ALLOCATED_MB) VALUES (?, ?, ?, ?, ?, ?)"
        stmt_insert = ibm_db.prepare(conn, query_insert)
        params = (
            utc_now.strftime('%Y-%m-%d-%H.%M.%S.%f'),
            status,
            error_message,
            os.getenv('TRIGGER_TYPE', 'HTTP'),
            os.getenv('K_SERVICE', 'Unknown'),
            os.getenv('MEMORY_ALLOCATED_MB', 128)
        )
        ibm_db.execute(stmt_insert, params)
    except Exception as e:
        print(f"插入记录时出错: {e}")
        status = "ERROR"
        error_message = str(e)


    # 3. 查询最新状态
    last_heartbeat_val = "查询失败"
    total_records_val = "查询失败"
    try:
        query_status = "SELECT MAX(RECORD_TIME), COUNT(*) FROM ZZG36949.CHRONOS_RECORDS"
        stmt_status = ibm_db.exec_immediate(conn, query_status)
        result = ibm_db.fetch_tuple(stmt_status)
        if result:
            last_heartbeat_val = result[0] if result[0] else "无记录"
            total_records_val = result[1] if result[1] else 0
    except Exception as e:
        print(f"查询状态时出错: {e}")

    # 关闭数据库连接
    ibm_db.close(conn)

    # 4. 返回最终的HTML页面
    page_status_class = "ok" if status == "OK" else "error"
    page_status_message = "运行正常" if status == "OK" else f"插入记录时出错: {error_message}"

    return HTML_TEMPLATE.format(
        status_class=page_status_class,
        status_message=page_status_message,
        last_heartbeat=escape(str(last_heartbeat_val)),
        total_records=escape(str(total_records_val)),
        cleanup_message=escape(cleanup_msg),
        current_time=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    )