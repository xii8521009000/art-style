import os
import psycopg
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)


def query(sql, args=(), one=False):
    with connect() as conn:
        cur = conn.execute(sql, args)
        if cur.description:
            return cur.fetchone() if one else cur.fetchall()


def initialize():
    with connect() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (id integer PRIMARY KEY CHECK(id=1), value jsonb NOT NULL);
        INSERT INTO settings VALUES(1, '{"model":"","effort":"high","language":"en"}') ON CONFLICT DO NOTHING;
        CREATE TABLE IF NOT EXISTS sessions (token_hash text PRIMARY KEY, created_at timestamptz DEFAULT now());
        CREATE TABLE IF NOT EXISTS login_attempts (address text PRIMARY KEY, attempts integer NOT NULL, started_at timestamptz NOT NULL);
        CREATE TABLE IF NOT EXISTS images (
            id uuid PRIMARY KEY, filename text NOT NULL, stored_name text NOT NULL,
            original_bytes integer NOT NULL, stored_bytes integer NOT NULL,
            width integer NOT NULL, height integer NOT NULL, created_at timestamptz DEFAULT now());
        CREATE TABLE IF NOT EXISTS jobs (
            id uuid PRIMARY KEY, image_id uuid NOT NULL REFERENCES images(id),
            title text NOT NULL, mode text NOT NULL CHECK(mode IN ('both','style','character')),
            focus text NOT NULL DEFAULT '', status text NOT NULL DEFAULT 'queued',
            style_prompt text, character_prompt text, warnings jsonb NOT NULL DEFAULT '[]',
            engine jsonb NOT NULL, error text, created_at timestamptz DEFAULT now(), finished_at timestamptz);
        CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at DESC);
        CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
        CREATE TABLE IF NOT EXISTS job_images (
            job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            image_id uuid NOT NULL REFERENCES images(id),
            position integer NOT NULL CHECK(position >= 0 AND position < 8),
            PRIMARY KEY(job_id, position), UNIQUE(job_id, image_id));
        CREATE INDEX IF NOT EXISTS job_images_image ON job_images(image_id);
        INSERT INTO job_images(job_id,image_id,position)
            SELECT id,image_id,0 FROM jobs ON CONFLICT DO NOTHING;
        ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reference_summary jsonb;
        ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_json jsonb;
        ''')
        conn.execute("UPDATE jobs SET status='failed', error='서버가 재시작되어 분석이 중단되었습니다. 다시 분석을 눌러주세요.', finished_at=now() WHERE status='running'")
