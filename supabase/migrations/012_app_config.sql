-- 应用配置表：api_base、baidu_map_ak、driver_id 等仅从 DB 读取，不依赖 config.js/localStorage
CREATE TABLE IF NOT EXISTS app_config (
  key text PRIMARY KEY,
  value text NOT NULL DEFAULT ''
);

COMMENT ON TABLE app_config IS '前端唯一配置源（除连接 DB 的 supabase url/anon 外）';

ALTER TABLE app_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_select_app_config" ON app_config;
CREATE POLICY "public_select_app_config" ON app_config FOR SELECT TO public USING (true);

-- 默认值（可后续在 Dashboard 或 SQL 中修改）
INSERT INTO app_config (key, value) VALUES
  ('api_base', 'https://xg.325218.xyz/api'),
  ('baidu_map_ak', 'W5IBbZpLZwYgEhpmeINcv5d8JqLtX1iG'),
  ('driver_id', 'a0000001-0000-4000-8000-000000000001')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
