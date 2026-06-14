from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_engine():
    return create_engine(current_app.config['SQLALCHEMY_DATABASE_URI'], future=True)


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def exec_query(sql: str, params: dict = None):
    with get_engine().connect() as conn:
        result = conn.execute(sql, params or {})
        return result
