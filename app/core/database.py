import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")


# 프로젝트 최상위의 .env 파일 로드
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def get_connection():
    """MySQL 연결을 생성합니다."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "cnc_wearpoint"),
        charset="utf8mb4",
        connection_timeout=5,
    )


def check_connection():
    """DB 연결과 등록된 데이터 수를 확인합니다."""
    connection = get_connection()

    try:
        cursor = connection.cursor()

        try:
            cursor.execute("SELECT DATABASE()")
            print("연결된 DB:", cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM tool_sets")
            print("등록된 Set:", cursor.fetchone()[0], "건")

            cursor.execute("SELECT COUNT(*) FROM measurements")
            print("등록된 측정:", cursor.fetchone()[0], "건")
        finally:
            cursor.close()
    finally:
        connection.close()


if __name__ == "__main__":
    check_connection()