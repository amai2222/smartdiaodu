-- =============================================================================
-- 预留多司机各自登录：登录用户绑定司机，各自资料与设置、各自探子脚本
-- 执行后：每个 app_users 行可绑定一个 driver_id，登录接口返回该 driver_id，前端/探子用其请求大脑
-- =============================================================================

ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS driver_id uuid REFERENCES drivers (id) ON DELETE SET NULL;

COMMENT ON COLUMN app_users.driver_id IS '该登录用户对应的司机 id；多司机时每人一个账号绑定一个司机，登录后前端用此 id 请求接口';

CREATE INDEX IF NOT EXISTS idx_app_users_driver_id ON app_users (driver_id);

-- 默认账号 admin 绑定默认司机（与 006 seed 一致）
UPDATE app_users
   SET driver_id = 'a0000001-0000-4000-8000-000000000001'
 WHERE username = 'admin'
   AND driver_id IS NULL;

-- 新司机单独登录示例：建新司机后执行下面（改用户名、密码、driver_id）
-- INSERT INTO app_users (username, password_hash, driver_id)
-- VALUES ('driver2', crypt('你的密码', gen_salt('bf')), 'a0000002-0000-4000-8000-000000000002')
-- ON CONFLICT (username) DO UPDATE SET driver_id = EXCLUDED.driver_id;
