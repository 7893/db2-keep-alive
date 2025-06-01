from flask import Flask
import ibm_db
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz

load_dotenv()

app = Flask(__name__)

# DB config from .env
DB_DATABASE = "bludb"
DB_HOSTNAME = "6667d8e9-9d4d-4ccb-ba32-21da3bb5aafc.c1ogj3sd0tgtu0lqde00.databases.appdomain.cloud"
DB_PORT = "30376"
DB_PROTOCOL = "TCPIP"
DB_UID = "zzg36949"
DB_PWD = os.environ.get("DB_PWD")
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

def get_db_connection():
    return ibm_db.connect(conn_str, "", "")

def clean_old_records(conn):
    try:
        stmt = ibm_db.exec_immediate(conn, "SELECT ID, RECORD_TIME FROM KEEP_ALIVE ORDER BY ID DESC")
        ids_to_keep = []
        now = datetime.utcnow()

        count = 0
        while ibm_db.fetch_row(stmt):
            record_time_str = ibm_db.result(stmt, "RECORD_TIME")
            record_id = ibm_db.result(stmt, "ID")
            record_time = datetime.strptime(record_time_str, "%Y-%m-%d-%H.%M.%S.%f")

            if count < 100 or (now - record_time).days < 7:
                ids_to_keep.append(str(record_id))
                count += 1
            else:
                break

        if ids_to_keep:
            id_list = ",".join(ids_to_keep)
            delete_sql = f"DELETE FROM KEEP_ALIVE WHERE ID NOT IN ({id_list})"
            ibm_db.exec_immediate(conn, delete_sql)
    except Exception as e:
        print("Cleanup error:", e)

@app.route("/ping")
def ping():
    try:
        conn = get_db_connection()
        clean_old_records(conn)

        now = datetime.utcnow()
        now_str = now.strftime("%Y-%m-%d-%H.%M.%S.%f")
        insert_sql = f"INSERT INTO KEEP_ALIVE (RECORD_TIME, STATUS) VALUES ('{now_str}', 'OK')"
        ibm_db.exec_immediate(conn, insert_sql)
        ibm_db.close(conn)
        return "Ping OK"
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/")
def index():
    try:
        conn = get_db_connection()
        cur = ibm_db.exec_immediate(conn, "SELECT COUNT(*) AS TOTAL FROM KEEP_ALIVE")
        total = ibm_db.fetch_assoc(cur)["TOTAL"]

        latest_sql = "SELECT RECORD_TIME FROM KEEP_ALIVE ORDER BY ID DESC FETCH FIRST 1 ROWS ONLY"
        earliest_sql = "SELECT RECORD_TIME FROM KEEP_ALIVE ORDER BY ID ASC FETCH FIRST 1 ROWS ONLY"

        latest_time = "N/A"
        earliest_time = "N/A"

        stmt = ibm_db.exec_immediate(conn, latest_sql)
        if ibm_db.fetch_row(stmt):
            latest_time = ibm_db.result(stmt, 0)

        stmt = ibm_db.exec_immediate(conn, earliest_sql)
        if ibm_db.fetch_row(stmt):
            earliest_time = ibm_db.result(stmt, 0)

        ibm_db.close(conn)

        def format_time(dt_str):
            if dt_str == "N/A":
                return "N/A"
            utc = datetime.strptime(dt_str, "%Y-%m-%d-%H.%M.%S.%f")
            local = utc.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Shanghai'))
            return local.strftime("%Y-%m-%d %H:%M:%S")

        return f"""
        <html>
        <head><title>DB2 Keep Alive</title></head>
        <body style="font-family: sans-serif; padding: 20px;">
          <h1>DB2 Keep Alive Status</h1>
          <p><strong>Total Records:</strong> {total}</p>
          <p><strong>Earliest Record Time (UTC+8):</strong> {format_time(earliest_time)}</p>
          <p><strong>Latest Record Time (UTC+8):</strong> {format_time(latest_time)}</p>
        </body>
        </html>
        """
    except Exception as e:
        return f"Error: {str(e)}", 500
