from flask import Flask, request, jsonify
import ibm_db
from google.cloud import secretmanager

app = Flask(__name__)

# --- 配置 ---
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_SECURITY = "SSL"

PROJECT_NUMBER = "817261716888"
SECRET_ID = "db2-password-global"
SECRET_VERSION = "latest"
SECRET_RESOURCE_NAME = f"projects/{PROJECT_NUMBER}/secrets/{SECRET_ID}/versions/{SECRET_VERSION}"

try:
    secret_manager_client = secretmanager.SecretManagerServiceClient()
except Exception as e:
    print(f"CRITICAL: Failed to initialize SecretManagerServiceClient: {e}")

@app.route("/", methods=["GET", "POST"])
def db2_keep_alive():
    conn = None
    log_messages = ["Function triggered."]
    
    try:
        log_messages.append(f"Fetching secret: {SECRET_RESOURCE_NAME}")
        access_response = secret_manager_client.access_secret_version(name=SECRET_RESOURCE_NAME)
        password = access_response.payload.data.decode("UTF-8")
        log_messages.append("Successfully fetched password from Secret Manager.")

        dsn = (
            f"DATABASE={DB_DATABASE};"
            f"HOSTNAME={DB_HOSTNAME};"
            f"PORT={DB_PORT};"
            f"PROTOCOL={DB_PROTOCOL};"
            f"UID={DB_UID};"
            f"PWD={password};"
            f"Security={DB_SECURITY};"
        )

        log_messages.append("Attempting to connect to Db2...")
        conn = ibm_db.connect(dsn, "", "")
        log_messages.append("Successfully connected to Db2.")

        insert_sql = "INSERT INTO chronos_records (status) VALUES ('OK')"
        log_messages.append(f"Executing INSERT: {insert_sql}")
        stmt_insert = ibm_db.exec_immediate(conn, insert_sql)
        if stmt_insert is False:
            raise Exception(f"INSERT failed: {ibm_db.stmt_errormsg()}")
        ibm_db.free_result(stmt_insert)
        log_messages.append("INSERT successful.")

        delete_sql = "DELETE FROM chronos_records WHERE record_time < CURRENT_TIMESTAMP - 90 DAYS"
        log_messages.append(f"Executing DELETE: {delete_sql}")
        stmt_delete = ibm_db.exec_immediate(conn, delete_sql)
        if stmt_delete is False:
            raise Exception(f"DELETE failed: {ibm_db.stmt_errormsg()}")
        affected_rows = ibm_db.num_rows(stmt_delete)
        ibm_db.free_result(stmt_delete)
        log_messages.append(f"DELETE successful. {affected_rows} records deleted.")

        final_message = f"Success. {affected_rows} old records deleted."
        log_messages.append(final_message)
        print("\n".join(log_messages))
        return jsonify(success=True, message=final_message)

    except Exception as e:
        error_message = f"Error: {str(e)}"
        if conn:
            db_conn_error = ibm_db.conn_errormsg()
            db_stmt_error = ibm_db.stmt_errormsg()
            if db_conn_error: error_message += f" | Db2 Conn Error: {db_conn_error}"
            if db_stmt_error: error_message += f" | Db2 Stmt Error: {db_stmt_error}"
        log_messages.append(error_message)
        print("\n".join(log_messages))
        return jsonify(success=False, error=error_message), 500

    finally:
        if conn:
            try:
                ibm_db.close(conn)
                print("Db2 connection closed.")
            except Exception as e_close:
                print(f"Error closing Db2 connection: {e_close}")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
