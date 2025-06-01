import os
import ibm_db
from datetime import datetime
import functions_framework
from flask import jsonify
import time
import uuid
import socket

# --- 数据库配置 ---
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

@functions_framework.http
def db2_keep_alive(request):
    start_time = time.perf_counter()

    # 初始化字段
    record_time_val = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S.%f")
    status_val = "OK"
    duration_ms_val = 0
    error_message_val = None
    record_count_val = 0

    # 系统环境
    hostname_val = socket.gethostname()
    ip_address_val = request.headers.get('X-Forwarded-For', request.remote_addr)
    region_val = os.getenv("GCP_REGION", "unknown")
    env_mode_val = os.getenv("ENV_MODE", "practice")
    git_commit_val = os.getenv("GIT_COMMIT_SHA", "unknown")

    # 请求上下文
    request_method_val = request.method
    request_path_val = request.path[:999]
    accept_language_val = request.headers.get('Accept-Language', '')[:254]
    user_agent_val = request.headers.get('User-Agent', '')[:499]
    request_id_val = str(uuid.uuid4())
    trigger_source_val = request.args.get('trigger_source', 'HTTP_DIRECT')[:31]
    note_val = request.args.get('note', '')[:999]

    conn = None
    try:
        # 连接数据库
        conn = ibm_db.connect(conn_str, "", "")

        # 清理旧记录
        cleanup_sql = """
        DELETE FROM ZZG36949.CHRONOS_RECORDS
        WHERE RECORD_TIME < (
            SELECT MIN(RECORD_TIME)
            FROM (
                SELECT RECORD_TIME
                FROM ZZG36949.CHRONOS_RECORDS
                ORDER BY RECORD_TIME DESC
                FETCH FIRST 100 ROWS ONLY
            ) AS T_TOP_100
        )
        """
        stmt_cleanup = ibm_db.prepare(conn, cleanup_sql)
        ibm_db.execute(stmt_cleanup)
        record_count_val = ibm_db.row_count(stmt_cleanup)  # ✅ 正确函数
        if record_count_val == -1:
            record_count_val = 0

    except Exception as e:
        status_val = "FAIL"
        error_message_val = str(e)[:1999]
        print(f"Database operation error: {status_val} - {error_message_val}")

    finally:
        end_time = time.perf_counter()
        duration_ms_val = int((end_time - start_time) * 1000)

        # 插入日志记录
        if conn:
            try:
                log_insert_sql = """INSERT INTO ZZG36949.CHRONOS_RECORDS (
                    RECORD_TIME, STATUS, DURATION_MS, ERROR_MESSAGE, RECORD_COUNT,
                    HOSTNAME, IP_ADDRESS, REGION, ENV_MODE, GIT_COMMIT,
                    REQUEST_METHOD, REQUEST_PATH, ACCEPT_LANGUAGE, USER_AGENT,
                    REQUEST_ID, TRIGGER_SOURCE, NOTE
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                stmt_log_insert = ibm_db.prepare(conn, log_insert_sql)

                params_to_bind = [
                    record_time_val, status_val, duration_ms_val, error_message_val, record_count_val,
                    hostname_val, ip_address_val, region_val, env_mode_val, git_commit_val,
                    request_method_val, request_path_val, accept_language_val, user_agent_val,
                    request_id_val, trigger_source_val, note_val
                ]

                for i, param_val in enumerate(params_to_bind):
                    ibm_db.bind_param(stmt_log_insert, i + 1, param_val if param_val is not None else ibm_db.NULL)

                ibm_db.execute(stmt_log_insert)

            except Exception as final_insert_e:
                print(f"CRITICAL: Failed to insert final log record: {final_insert_e}")
                if status_val == "OK":
                    status_val = "LOG_FAIL"
                    error_message_val = str(final_insert_e)[:1999]
            finally:
                ibm_db.close(conn)
        else:
            if not error_message_val:
                status_val = "FAIL"
                error_message_val = "DB connection was not established for logging."
            print(f"Invocation logged to Cloud Logging (DB connection failed or other pre-log error): "
                  f"Status={status_val}, Error='{error_message_val}', Duration={duration_ms_val}ms, "
                  f"IP={ip_address_val}, UA='{user_agent_val}', ReqID={request_id_val}")

    response_payload = {
        "status": status_val,
        "requestId": request_id_val,
        "recordTime": record_time_val,
        "durationMs": duration_ms_val,
        "cleanedRecords": record_count_val
    }
    if error_message_val:
        response_payload["errorMessage"] = error_message_val
    else:
        response_payload["message"] = "Keep-alive processed successfully."

    return jsonify(response_payload), 200 if status_val == "OK" else 500
