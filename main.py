# db2_keep_alive.py

import os
import ibm_db
import ibm_db_dbi
from datetime import datetime, timedelta # timedelta for time calculations
import functions_framework
from flask import jsonify
import time
import uuid
import socket
import traceback

# --- Database Configuration ---
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

    # Initialize log fields
    record_time_val = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S.%f")
    status_val = "OK"
    duration_ms_val = 0
    error_message_val = None
    record_count_val = 0 
    note_val = ""

    # System environment info
    hostname_val = socket.gethostname()
    ip_address_val = request.headers.get('X-Forwarded-For', request.remote_addr)
    region_val = os.getenv("GCP_REGION", "unknown")
    env_mode_val = os.getenv("ENV_MODE", "practice")
    git_commit_val = os.getenv("GIT_COMMIT_SHA", "unknown")[:40]

    # Request context info
    request_method_val = request.method
    request_path_val = request.path[:999]
    accept_language_val = request.headers.get('Accept-Language', '')[:254]
    user_agent_val = request.headers.get('User-Agent', '')[:499]
    request_id_val = str(uuid.uuid4())
    trigger_source_val = request.args.get('trigger_source', 'HTTP_DIRECT')[:31]
    
    conn = None
    cursor = None

    try:
        conn = ibm_db_dbi.connect(conn_str)
        cursor = conn.cursor()

        # New Cleanup Logic: Keep top 30 OR records from the last 30 minutes
        cleanup_sql = """
        DELETE FROM ZZG36949.CHRONOS_RECORDS
        WHERE ID NOT IN (
            SELECT ID FROM ( -- Sub-select to handle UNION for NOT IN
                SELECT ID FROM ZZG36949.CHRONOS_RECORDS
                ORDER BY RECORD_TIME DESC
                FETCH FIRST 30 ROWS ONLY -- Changed to 30
            )
            UNION
            SELECT ID FROM ZZG36949.CHRONOS_RECORDS
            WHERE RECORD_TIME >= (CURRENT TIMESTAMP - 30 MINUTES) -- Changed to 30 MINUTES
        )
        """
        cursor.execute(cleanup_sql)
        record_count_val = cursor.rowcount if cursor.rowcount != -1 else 0 
        conn.commit() 
        note_val = f"Keep-alive successful, new cleanup (top 30 or last 30min) applied, {record_count_val} old records cleaned."

    except Exception as e:
        status_val = "FAIL"
        error_message_val = str(e)[:1999]
        note_val = f"Database operation failed: {error_message_val}"
        print(f"[ERROR] Database operation error: {status_val} - {error_message_val}")
        print(traceback.format_exc())
        if conn: 
            try:
                conn.rollback()
            except Exception as rb_err:
                print(f"[ERROR] Rollback failed: {rb_err}")

    finally:
        end_time = time.perf_counter()
        duration_ms_val = int((end_time - start_time) * 1000)

        request_note = request.args.get('note', '')[:999]
        if request_note and status_val == "OK": 
            note_val = request_note
        elif not note_val and status_val == "OK": 
             note_val = "Log entry with new cleanup strategy (top 30 or last 30min)."
        elif not note_val: 
             note_val = "Log entry."

        if cursor and conn: 
            try:
                log_insert_sql = """INSERT INTO ZZG36949.CHRONOS_RECORDS (
                                    RECORD_TIME, STATUS, DURATION_MS, ERROR_MESSAGE, RECORD_COUNT,
                                    HOSTNAME, IP_ADDRESS, REGION, ENV_MODE, GIT_COMMIT,
                                    REQUEST_METHOD, REQUEST_PATH, ACCEPT_LANGUAGE, USER_AGENT,
                                    REQUEST_ID, TRIGGER_SOURCE, NOTE
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

                params = [
                    record_time_val, status_val, duration_ms_val, error_message_val, record_count_val,
                    hostname_val, ip_address_val, region_val, env_mode_val, git_commit_val,
                    request_method_val, request_path_val, accept_language_val, user_agent_val,
                    request_id_val, trigger_source_val, note_val
                ]
                cursor.execute(log_insert_sql, params)
                conn.commit() 

            except Exception as log_error:
                print(f"[CRITICAL] Failed to insert log record: {log_error}")
                print(traceback.format_exc())
                if status_val == "OK":
                    status_val = "LOG_FAIL"
                    if not error_message_val:
                        error_message_val = str(log_error)[:1999]
                    note_val = "Main operation OK, but logging to DB failed."
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        elif conn: 
             conn.close()
        else:
            if not error_message_val: 
                status_val = "FAIL" 
                error_message_val = "No database connection available for primary operation or logging."
            if not note_val:
                note_val = "DB connection failed, unable to write log."
            print(f"[WARNING] Invocation logged to Cloud Logging (no DB connection): "
                  f"Status={status_val}, Error='{error_message_val}', Duration={duration_ms_val}ms, "
                  f"ReqID={request_id_val}, Note='{note_val}'")

    response_payload = {
        "status": status_val,
        "requestId": request_id_val,
        "recordTime": record_time_val,
        "durationMs": duration_ms_val,
        "cleanedRecordsImpact": record_count_val,
        "note": note_val
    }
    if error_message_val:
        response_payload["errorMessage"] = error_message_val
    else:
        response_payload["message"] = "Keep-alive processed successfully with new cleanup strategy."

    return jsonify(response_payload), 200 if status_val in ("OK", "LOG_FAIL") else 500