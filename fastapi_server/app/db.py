"""MySQL 헬퍼. 모든 SQL은 %s 바인딩만 사용한다(n8n의 문자열 치환 방식과 달리 인젝션/따옴표 오류 없음)."""
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from .config import settings


def connect():
    return pymysql.connect(
        host=settings.db_host, port=settings.db_port, user=settings.db_user,
        password=settings.db_password, database=settings.db_name,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


@contextmanager
def tx():
    """여러 문장을 한 트랜잭션으로 실행: with tx() as cur: cur.execute(...)"""
    conn = connect()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def q(sql, params=None):
    """SELECT → list[dict]"""
    with tx() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def x(sql, params=None):
    """INSERT/UPDATE/DELETE → 영향 행 수"""
    with tx() as cur:
        return cur.execute(sql, params)
