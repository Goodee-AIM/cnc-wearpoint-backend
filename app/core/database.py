import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


# 프로젝트 최상위 .env 파일을 한 번만 로드합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(
    dotenv_path=ENV_PATH,
    encoding="utf-8-sig",
)


def get_connection():
    """MySQL 연결을 생성합니다."""

    # 운영 환경에서는 SSL 인증을 기본으로 사용합니다.
    # 로컬 Docker MySQL에서는 .env의 DB_SSL_ENABLED=0으로
    # SSL을 명시적으로 비활성화합니다.
    ssl_options = (
        {
            "ssl_disabled": True,
        }
        if os.getenv("DB_SSL_ENABLED", "1") == "0"
        else {
            "ssl_ca": os.getenv(
                "DB_SSL_CA",
                "/etc/mysql/certs/ca.pem",
            ),
            "ssl_verify_cert": True,
            "ssl_verify_identity": False,
        }
    )

    # Isolated test tunnel only. TLS certificate verification is not enabled.
    # With DB_SSL_MODE unset, existing production settings remain unchanged.
    if os.getenv("DB_SSL_MODE") == "tls_test":
        test_host = os.getenv("DB_HOST", "127.0.0.1")
        test_port = int(os.getenv("DB_PORT", "3306"))
        if test_host != "127.0.0.1" or test_port != 13306:
            raise RuntimeError("tls_test is restricted to 127.0.0.1:13306")
        ssl_options = {"ssl_disabled": False}

    return mysql.connector.connect(
        host=os.getenv(
            "DB_HOST",
            "127.0.0.1",
        ),
        port=int(
            os.getenv(
                "DB_PORT",
                "3306",
            )
        ),
        user=os.getenv(
            "DB_USER",
            "root",
        ),
        password=os.environ[
            "DB_PASSWORD"
        ],
        database=os.getenv(
            "DB_NAME",
            "cnc_wearpoint",
        ),
        charset="utf8mb4",
        connection_timeout=5,
        **ssl_options,
    )


def check_connection():
    """DB 연결과 등록된 데이터 수를 확인합니다."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        try:
            cursor.execute(
                "SELECT DATABASE()"
            )
            print(
                "연결된 DB:",
                cursor.fetchone()[0],
            )

            cursor.execute(
                "SELECT COUNT(*) "
                "FROM tool_sets"
            )
            print(
                "등록된 Set:",
                cursor.fetchone()[0],
                "건",
            )

            cursor.execute(
                "SELECT COUNT(*) "
                "FROM measurements"
            )
            print(
                "등록된 측정:",
                cursor.fetchone()[0],
                "건",
            )

        finally:
            cursor.close()

    finally:
        connection.close()


if __name__ == "__main__":
    check_connection()