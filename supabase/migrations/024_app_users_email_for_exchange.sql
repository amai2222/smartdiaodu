-- =============================================================================
-- app_users 增加 email，用于邮箱登录后换我们 JWT（/auth/exchange）
-- 邮箱与 app_users 关联后，前端用 Supabase token 换大脑 JWT，地图/首页都能带正确 token
-- =============================================================================

ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;

COMMENT ON COLUMN app_users.email IS '可选，与 Supabase Auth 邮箱一致时可用于 /auth/exchange 换 JWT';

CREATE INDEX IF NOT EXISTS idx_app_users_email ON app_users (email) WHERE email IS NOT NULL;

-- 默认 admin 对应邮箱 admin@test.com（与 004 里 Supabase Auth 一致）
UPDATE app_users
   SET email = 'admin@test.com'
 WHERE username = 'admin'
   AND (email IS NULL OR email = '');
