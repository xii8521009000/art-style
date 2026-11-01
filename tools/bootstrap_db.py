"""One-time existing-install migration, run with the previous database owner credentials.

Only changes the dedicated application's database objects. Never prints passwords.
The normal backend receives only the new non-superuser connection string.
"""
import os
import re
import psycopg
from psycopg import sql


def main():
    password=os.environ['APP_DB_PASSWORD']
    if not re.fullmatch(r'[a-f0-9]{64}',password):
        raise SystemExit('APP_DB_PASSWORD must be a generated 64-character hex secret')
    with psycopg.connect(os.getenv('ADMIN_DATABASE_URL') or os.environ['DATABASE_URL']) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='artstyle_web'").fetchone():
            conn.execute('CREATE ROLE artstyle_web LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION')
        conn.execute(sql.SQL('ALTER ROLE artstyle_web LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Literal(password)))
        name=conn.execute('SELECT current_database()').fetchone()[0]
        conn.execute(sql.SQL('ALTER DATABASE {} OWNER TO artstyle_web').format(sql.Identifier(name)))
        conn.execute('ALTER SCHEMA public OWNER TO artstyle_web')
        conn.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        kinds={'r':'TABLE','p':'TABLE','S':'SEQUENCE','v':'VIEW','m':'MATERIALIZED VIEW'}
        rows=conn.execute("SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m')").fetchall()
        for name,kind in rows:
            conn.execute(sql.SQL('ALTER {} public.{} OWNER TO artstyle_web').format(sql.SQL(kinds[kind]),sql.Identifier(name)))
    print('Application database role prepared with no superuser/create-role/create-database privileges.')


if __name__=='__main__': main()
