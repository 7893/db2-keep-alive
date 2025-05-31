import functions_framework
import ibm_db
from google.cloud import secretmanager
import json # 用于构建 JSON 响应
import os # 用于获取环境变量（虽然我们主要从Secret获取）

# --- 全局配置 ---
# Db2 连接参数 (密码将从 Secret Manager 获取)
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_SECURITY = "SSL" # 对于 Db2 on Cloud 通常需要 SSL

# Secret Manager 配置
# 使用你的项目编号 (Project Number)
PROJECT_NUMBER = "817261716888" 
SECRET_ID = "db2-password-global" # 我们创建的全局 Secret 名称
SECRET_VERSION = "latest" # 总是获取最新版本的密码

# 构建 Secret 的完整资源名称
SECRET_RESOURCE_NAME = f"projects/{PROJECT_NUMBER}/secrets/{SECRET_ID}/versions/{SECRET_VERSION}"

# 初始化 Secret Manager 客户端 (全局，以便复用)
# Python 客户端库能很好地处理全局 Secret，无需特殊配置
try:
    secret_manager_client = secretmanager.SecretManagerServiceClient()
except Exception as e:
    print(f"CRITICAL: Failed to initialize SecretManagerServiceClient: {e}")
    # 在实际生产中，这可能需要更复杂的错误处理或启动失败机制
    # 但对于 Cloud Function，如果这里失败，函数在第一次调用时会报错

@functions_framework.http
def db2_keep_alive_python(request):
    """
    HTTP Cloud Function to perform a keep-alive operation on a Db2 database.
    Fetches credentials from Secret Manager, connects to Db2,
    inserts a heartbeat record, and deletes old records.
    """
    conn = None  # 初始化 conn，确保在 finally 中可用
    log_messages = ["Function triggered."]

    try:
        # 1. 从 Secret Manager 获取密码
        log_messages.append(f"Fetching secret: {SECRET_RESOURCE_NAME}")
        access_response = secret_manager_client.access_secret_version(name=SECRET_RESOURCE_NAME)
        password = access_response.payload.data.decode("UTF-8")
        log_messages.append("Successfully fetched password from Secret Manager.")

        # 2. 构建完整的 DSN (Data Source Name) 字符串
        dsn = (
            f"DATABASE={DB_DATABASE};"
            f"HOSTNAME={DB_HOSTNAME};"
            f"PORT={DB_PORT};"
            f"PROTOCOL={DB_PROTOCOL};"
            f"UID={DB_UID};"
            f"PWD={password};"
            f"Security={DB_SECURITY};"
        )

        # 3. 连接到 Db2 数据库 (ibm_db 的连接是同步操作)
        log_messages.append("Attempting to connect to Db2...")
        conn = ibm_db.connect(dsn, "", "")
        log_messages.append("Successfully connected to Db2.")

        # 4. 执行 INSERT 语句
        insert_sql = "INSERT INTO chronos_records (status) VALUES ('OK')"
        log_messages.append(f"Executing INSERT: {insert_sql}")
        stmt_insert = ibm_db.exec_immediate(conn, insert_sql)
        if stmt_insert is False: # 检查语句执行是否失败
             raise Exception(f"INSERT statement failed: {ibm_db.stmt_errormsg()}")
        log_messages.append("INSERT successful.")
        ibm_db.free_result(stmt_insert) # 释放语句句柄

        # 5. 执行 DELETE 语句
        delete_sql = "DELETE FROM chronos_records WHERE record_time < CURRENT_TIMESTAMP - 90 DAYS"
        log_messages.append(f"Executing DELETE: {delete_sql}")
        stmt_delete = ibm_db.exec_immediate(conn, delete_sql)
        if stmt_delete is False: # 检查语句执行是否失败
            raise Exception(f"DELETE statement failed: {ibm_db.stmt_errormsg()}")
        affected_rows = ibm_db.num_rows(stmt_delete) # 获取DELETE影响的行数
        log_messages.append(f"DELETE successful. {affected_rows} old records deleted.")
        ibm_db.free_result(stmt_delete) # 释放语句句柄
        
        final_message = f"Heartbeat successful (Python, global secret via client library) and {affected_rows} old logs cleaned."
        log_messages.append(final_message)
        print("\n".join(log_messages)) # 打印所有日志
        
        response_payload = {"success": True, "message": final_message}
        return (json.dumps(response_payload), 200, {'Content-Type': 'application/json'})

    except Exception as e:
        error_message = f"Function execution failed: {str(e)}"
        # 如果连接存在且发生错误，尝试获取更详细的数据库错误信息
        if conn:
            db_conn_error = ibm_db.conn_errormsg()
            db_stmt_error = ibm_db.stmt_errormsg()
            if db_conn_error: error_message += f" | Db2 Connection Error: {db_conn_error}"
            if db_stmt_error: error_message += f" | Db2 Statement Error: {db_stmt_error}"
        
        log_messages.append(error_message)
        print("\n".join(log_messages)) # 打印所有日志，包括错误
        
        response_payload = {"success": False, "error": error_message}
        return (json.dumps(response_payload), 500, {'Content-Type': 'application/json'})

    finally:
        # 6. 无论成功或失败，都尝试关闭数据库连接
        if conn:
            try:
                ibm_db.close(conn)
                print("Db2 connection closed.") # 这个日志可能在函数返回后才显示
            except Exception as e_close:
                print(f"Error closing Db2 connection: {str(e_close)}")