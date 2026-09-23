import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from urllib.parse import quote_plus

# Chuỗi kết nối SQL Server chuẩn Windows Authentication
# Driver: ODBC Driver 17 for SQL Server (hoặc SQL Server)
SERVER = os.getenv("DB_SERVER", "localhost")
DATABASE = os.getenv("DB_NAME", "HeThongGiamSatThi")
DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

connection_string = (
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

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

