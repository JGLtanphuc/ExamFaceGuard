import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from urllib.parse import quote_plus

import pyodbc

def _get_best_driver():
    """Tự động phát hiện driver ODBC SQL Server mới nhất có trên máy tính"""
    available = pyodbc.drivers()
    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server"
    ]
    for d in preferred:
        if d in available:
            return d
    return "SQL Server"

def _build_connection_string():
    """Tự động dò tìm SQL Server instance (localhost, .\\SQLEXPRESS, (local), ...)"""
    driver = os.getenv("DB_DRIVER") or _get_best_driver()
    db_name = os.getenv("DB_NAME", "HeThongGiamSatThi")

    # Các instance phổ biến khi cài SQL Server trên Windows
    server_candidates = [
        os.getenv("DB_SERVER"),
        "localhost",
        r".\SQLEXPRESS",
        r"localhost\SQLEXPRESS",
        "(local)",
        "."
    ]
    server_candidates = [s for s in server_candidates if s]

    for s in server_candidates:
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={s};"
            f"DATABASE={db_name};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
        if "ODBC Driver 18" in driver:
            conn_str += "Encrypt=no;"

        try:
            test_conn = pyodbc.connect(conn_str, timeout=2)
            test_conn.close()
            return conn_str
        except Exception:
            continue

    # Fallback mặc định
    return (
        f"DRIVER={{{driver}}};"
        "SERVER=localhost;"
        f"DATABASE={db_name};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

connection_string = _build_connection_string()
params = quote_plus(connection_string)
SQLALCHEMY_DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={params}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    fast_executemany=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency injection session cho FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

