-- 后端 smartdiaodu.py 从 app_config 读取的键（除 SUPABASE_URL / SERVICE_ROLE_KEY / JWT_SECRET 仍用环境变量）
INSERT INTO app_config (key, value) VALUES
  ('baidu_service_id', '119231078'),
  ('bark_key', 'bGPZAHqjNjdiQZTg5GeWWG'),
  ('max_detour_seconds', '900'),
  ('request_timeout', '5'),
  ('driver_mode', 'mode2'),
  ('mode2_detour_min', '20'),
  ('mode2_detour_max', '60'),
  ('mode2_high_profit_threshold', '100'),
  ('mode3_max_minutes_to_pickup', '30'),
  ('mode3_max_detour_minutes', '25'),
  ('response_timeout_seconds', '300'),
  ('response_page_base', '')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
