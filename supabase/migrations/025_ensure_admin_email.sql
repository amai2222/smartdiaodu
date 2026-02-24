-- =============================================================================
-- 确保 app_users 有 admin 且邮箱已关联 admin@test.com（若没有 admin 则先插入）
-- 在 Supabase SQL 编辑器里执行本文件或下面命令
-- =============================================================================

-- 1. 确保有 email 列
ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;

-- 2. 若没有 admin 用户则插入（密码 123456）
INSERT INTO app_users (username, password_hash, created_at)
SELECT 'admin', crypt('123456', gen_salt('bf')), now()
WHERE NOT EXISTS (SELECT 1 FROM app_users WHERE username = 'admin');

-- 3. 把 admin 关联到邮箱 admin@test.com
UPDATE app_users
   SET email = 'admin@test.com'
 WHERE username = 'admin';

-- 4. 若有 driver_id 列，确保 admin 绑定默认司机（无则忽略报错）
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'app_users' AND column_name = 'driver_id'
  ) THEN
    UPDATE app_users
       SET driver_id = 'a0000001-0000-4000-8000-000000000001'
     WHERE username = 'admin' AND driver_id IS NULL;
  END IF;
END $$;

-- 5. 查看结果（执行后看是否有 username=admin, email=admin@test.com）
SELECT id, username, email, driver_id FROM app_users WHERE username = 'admin';
