-- 后端地理编码/路线规划用：服务器端百度 AK（与前端 baidu_map_ak 可不同）
INSERT INTO app_config (key, value) VALUES
  ('baidu_ak_server', 'wxw2PvK3nWeOCGk1rZDe2krnlc1jbzsc')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
