-- =============================================================================
-- 诊断并修复：当前司机应有 4 个乘客，空座应为 0
-- 在 Supabase SQL Editor 中执行（driver_id 与 config.js / seed 一致）
-- =============================================================================

-- 1. 诊断：查看该司机的 driver_state
SELECT 'driver_state' AS tbl, driver_id, current_loc, empty_seats, mode, updated_at
FROM driver_state
WHERE driver_id = 'a0000001-0000-4000-8000-000000000001';

-- 2. 诊断：查看分配给该司机且状态为 assigned 的订单数量
SELECT 'order_pool (assigned)' AS tbl, COUNT(*) AS cnt
FROM order_pool
WHERE assigned_driver_id = 'a0000001-0000-4000-8000-000000000001'
  AND status = 'assigned';

-- 3. 诊断：列出这 4 条订单（若有）
SELECT id, pickup, delivery, status, assigned_driver_id
FROM order_pool
WHERE assigned_driver_id = 'a0000001-0000-4000-8000-000000000001'
ORDER BY created_at;

-- 4. 修复：把该司机的空座改为 0（与 4 个乘客一致）
UPDATE driver_state
SET empty_seats = 0, updated_at = now()
WHERE driver_id = 'a0000001-0000-4000-8000-000000000001';

-- 5. 修复：确保分配给该司机的订单状态为 assigned（若有被误改为 completed 的可改回）
UPDATE order_pool
SET status = 'assigned', assigned_driver_id = 'a0000001-0000-4000-8000-000000000001'
WHERE assigned_driver_id = 'a0000001-0000-4000-8000-000000000001'
  AND status <> 'assigned';

-- 若上面只影响 0 行，说明可能订单被清空或 assigned_driver_id 被置空，需要重新跑种子
-- 重新插入 4 个乘客并分配给该司机（与 006 一致）：
INSERT INTO order_pool (order_hash, pickup, delivery, price, status, assigned_driver_id)
VALUES
  (md5('江苏省南通市如东县长沙镇黄海大桥北首_上海市宝山区富锦路885号_80'), '江苏省南通市如东县长沙镇黄海大桥北首', '上海市宝山区富锦路885号', 80.00, 'assigned', 'a0000001-0000-4000-8000-000000000001'),
  (md5('江苏省南通市如东县苴镇刘埠村_上海市浦东新区港建路889号_85'), '江苏省南通市如东县苴镇刘埠村', '上海市浦东新区港建路889号', 85.00, 'assigned', 'a0000001-0000-4000-8000-000000000001'),
  (md5('江苏省南通市如东县城区如东汽车客运站_上海虹桥综合交通枢纽（上海虹桥站_90'), '江苏省南通市如东县城区如东汽车客运站', '上海虹桥综合交通枢纽（上海虹桥站）', 90.00, 'assigned', 'a0000001-0000-4000-8000-000000000001'),
  (md5('江苏省南通市如东县掘港镇富春江中路1号_上海市黄浦区人民大道185号人民广场_95'), '江苏省南通市如东县掘港镇富春江中路1号', '上海市黄浦区人民大道185号人民广场', 95.00, 'assigned', 'a0000001-0000-4000-8000-000000000001')
ON CONFLICT (order_hash) DO UPDATE SET
  status = 'assigned',
  assigned_driver_id = 'a0000001-0000-4000-8000-000000000001';
