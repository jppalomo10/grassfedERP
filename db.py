import streamlit as st
import psycopg2
import psycopg2.extras

@st.cache_resource
def get_conn():
    # Lee la URL desde secrets
    db_url = st.secrets["DATABASE_URL"]
    conn = psycopg2.connect(db_url)
    return conn

def run_query(query: str, params=None, fetch: str = "all"):
    conn = get_conn()

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)

            if fetch == "one":
                result = cur.fetchone()
            elif fetch == "all":
                result = cur.fetchall()
            else:
                result = None

        conn.commit()
        return result

    except Exception:
        conn.rollback()
        raise

    finally:
        pass
