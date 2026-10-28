from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings().database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False}
    if settings().database_url.startswith("sqlite")
    else {},
)
if settings().database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
