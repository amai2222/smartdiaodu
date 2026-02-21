-- =============================================================================
-- 模拟数据：4 名乘客订单 + 1 名司机（起点荣生花苑）
-- 在 Supabase SQL Editor 中执行，或通过 supabase db push 应用
-- =============================================================================

-- 1. 插入一名模拟司机（固定 UUID，重复执行不会重复插入）
INSERT INTO drivers (id, name, plate_number, max_seats, status)
VALUES (
  'a0000001-0000-4000-8000-000000000001',
  '模拟司机',
  '苏F00001',
  4,
  'online'
)
ON CONFLICT (id) DO NOTHING;

-- 2. 为该司机写入/更新实时位置（起点：荣生花苑）
INSERT INTO driver_state (driver_id, current_loc, empty_seats, mode)
VALUES (
  'a0000001-0000-4000-8000-000000000001',
  '荣生花苑',
  4,
  'smart'
)
ON CONFLICT (driver_id) DO UPDATE SET
  current_loc = EXCLUDED.current_loc,
  empty_seats = EXCLUDED.empty_seats,
  mode = EXCLUDED.mode,
  updated_at = now();

-- 3. 插入 4 个乘客订单（待匹配）
INSERT INTO order_pool (order_hash, pickup, delivery, price, status)
VALUES
  (
    md5('江苏省南通市如东县长沙镇黄海大桥北首_上海市宝山区富锦路885号_80'),
    '江苏省南通市如东县长沙镇黄海大桥北首',
    '上海市宝山区富锦路885号',
    80.00,
    'pending_match'
  ),
  (
    md5('江苏省南通市如东县苴镇刘埠村_上海市浦东新区港建路889号_85'),
    '江苏省南通市如东县苴镇刘埠村',
    '上海市浦东新区港建路889号',
    85.00,
    'pending_match'
  ),
  (
    md5('江苏省南通市如东县城区如东汽车客运站_上海虹桥综合交通枢纽（上海虹桥站_90'),
    '江苏省南通市如东县城区如东汽车客运站',
    '上海虹桥综合交通枢纽（上海虹桥站）',
    90.00,
    'pending_match'
  ),
  (
    md5('江苏省南通市如东县掘港镇富春江中路1号_上海市黄浦区人民大道185号人民广场_95'),
    '江苏省南通市如东县掘港镇富春江中路1号',
    '上海市黄浦区人民大道185号人民广场',
    95.00,
    'pending_match'
  )
ON CONFLICT (order_hash) DO NOTHING;
