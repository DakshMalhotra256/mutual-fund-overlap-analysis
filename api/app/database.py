import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Defaults to a local SQLite file so the API runs with zero setup.
# For MySQL, set e.g.  DATABASE_URL=mysql+pymysql://root:<password>@localhost:3306/mutual_fund_db
_default_sqlite = Path(__file__).resolve().parents[2] / "data" / "mutual_fund_api.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_default_sqlite}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
