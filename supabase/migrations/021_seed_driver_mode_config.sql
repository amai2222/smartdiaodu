-- 将 app_config 中与司机模式相关的配置写入 driver_mode_config（每司机一行）
-- 默认司机（与 006 seed 一致）使用：mode2，绕路/高收益/接力参数与当前配置一致
INSERT INTO driver_mode_config (
  driver_id,
  mode,
  mode2_detour_min,
  mode2_detour_max,
  mode2_high_profit_threshold,
  mode3_max_minutes_to_pickup,
  mode3_max_detour_minutes,
  updated_at
) VALUES (
  'a0000001-0000-4000-8000-000000000001',
  'mode2',
  20,
  60,
  100,
  30,
  25,
  now()
)
ON CONFLICT (driver_id) DO UPDATE SET
  mode = EXCLUDED.mode,
  mode2_detour_min = EXCLUDED.mode2_detour_min,
  mode2_detour_max = EXCLUDED.mode2_detour_max,
  mode2_high_profit_threshold = EXCLUDED.mode2_high_profit_threshold,
  mode3_max_minutes_to_pickup = EXCLUDED.mode3_max_minutes_to_pickup,
  mode3_max_detour_minutes = EXCLUDED.mode3_max_detour_minutes,
  updated_at = EXCLUDED.updated_at;
