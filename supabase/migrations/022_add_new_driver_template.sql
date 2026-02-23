-- =============================================================================
-- 添加新司机模板：在 Supabase SQL Editor 中执行前，把下面姓名、车牌、UUID 改为实际值
-- 执行后可选：
--   A) 该司机单独登录：在 app_users 插入一行并绑定本 driver_id（见 023），用该账号调 POST /login 登录后前端自动用此司机
--   B) 探子脚本：把 tanzi.py / moni.py 的 DRIVER_ID 改为本司机 id
--   C) 临时切换默认：把 app_config 表 key=driver_id 的 value 改为本司机 id
-- =============================================================================

-- 新司机 UUID 示例：a0000002-...；再加第三个司机可改为 a0000003-0000-4000-8000-000000000003，并改 name、plate_number

-- 1. 插入新司机
INSERT INTO drivers (id, name, plate_number, max_seats, status)
VALUES (
  'a0000002-0000-4000-8000-000000000002',
  '新司机',
  '苏F00002',
  4,
  'online'
)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, plate_number = EXCLUDED.plate_number, status = EXCLUDED.status;

-- 2. 新司机的实时状态
INSERT INTO driver_state (driver_id, current_loc, empty_seats, mode)
VALUES ('a0000002-0000-4000-8000-000000000002', '', 4, 'smart')
ON CONFLICT (driver_id) DO UPDATE SET empty_seats = EXCLUDED.empty_seats, mode = EXCLUDED.mode, updated_at = now();

-- 3. 新司机的模式与参数（默认 mode2，与 021 一致）
INSERT INTO driver_mode_config (driver_id, mode, mode2_detour_min, mode2_detour_max, mode2_high_profit_threshold, mode3_max_minutes_to_pickup, mode3_max_detour_minutes)
VALUES ('a0000002-0000-4000-8000-000000000002', 'mode2', 20, 60, 100, 30, 25)
ON CONFLICT (driver_id) DO UPDATE SET
  mode = EXCLUDED.mode,
  mode2_detour_min = EXCLUDED.mode2_detour_min,
  mode2_detour_max = EXCLUDED.mode2_detour_max,
  mode2_high_profit_threshold = EXCLUDED.mode2_high_profit_threshold,
  mode3_max_minutes_to_pickup = EXCLUDED.mode3_max_minutes_to_pickup,
  mode3_max_detour_minutes = EXCLUDED.mode3_max_detour_minutes,
  updated_at = now();
