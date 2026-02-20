-- =============================================================================
-- 登录用户表：控制台登录（用户名 + 密码），与 Supabase Auth 分离
-- 默认账号：admin / 123456（首次部署后建议改密或仅内网使用）
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE app_users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE app_users IS '控制台登录用户，用户名+密码校验';

CREATE INDEX idx_app_users_username ON app_users (username);

-- RLS 开启后 anon 无策略即无法访问；服务端用 SUPABASE_SERVICE_ROLE_KEY 请求会绕过 RLS
ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;

-- 默认账号 admin / 123456（bcrypt）
INSERT INTO app_users (username, password_hash)
VALUES ('admin', crypt('123456', gen_salt('bf')));
