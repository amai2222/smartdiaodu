-- 网页端地图底图专用 AK（与 baidu_map_ak 可不同：一个服务器端、一个浏览器端）
INSERT INTO app_config (key, value) VALUES
  ('baidu_map_ak_browser', '')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
