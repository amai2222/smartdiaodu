-- 1. order_pool 增加出发时间字段（可选，用于乘客计划展示/筛选）
ALTER TABLE order_pool
  ADD COLUMN IF NOT EXISTS departure_time text NOT NULL DEFAULT '';

COMMENT ON COLUMN order_pool.departure_time IS '乘客出发时间，如 明天 09:00、08:30';

-- 2. 插入并直接作为当前司机的乘客计划（已分配）
-- 使用与 006 相同的种子司机 id；若你是其他司机，执行后可在控制台用「添加至我的车厢」或改 assigned_driver_id
-- 来源：行程1 南通·老车站螺丝五金店 → 上海·顶程考研；行程2 南通·金水湾花园 → 上海·浦发绿城东区
INSERT INTO order_pool (order_hash, pickup, delivery, price, departure_time, status, assigned_driver_id)
VALUES
  (
    md5('南通市·老车站螺丝五金店(人民南路店)_上海市·顶程考研(奉贤校区)_90.95'),
    '南通市·老车站螺丝五金店(人民南路店)',
    '上海市·顶程考研(奉贤校区)',
    90.95,
    '明天 09:00',
    'assigned',
    'a0000001-0000-4000-8000-000000000001'
  ),
  (
    md5('南通市・金水湾花园-18号楼_上海市·浦发绿城东区-南门_87.55'),
    '南通市・金水湾花园-18号楼',
    '上海市·浦发绿城东区-南门',
    87.55,
    '明天 09:30',
    'assigned',
    'a0000001-0000-4000-8000-000000000001'
  )
ON CONFLICT (order_hash) DO UPDATE SET
  pickup = EXCLUDED.pickup,
  delivery = EXCLUDED.delivery,
  price = EXCLUDED.price,
  departure_time = EXCLUDED.departure_time,
  status = EXCLUDED.status,
  assigned_driver_id = EXCLUDED.assigned_driver_id;

-- 3. 同步该司机的空座数：空座 = max_seats - 当前已分配订单数（不低于 0）
UPDATE driver_state ds
SET empty_seats = GREATEST(0,
  (SELECT d.max_seats FROM drivers d WHERE d.id = ds.driver_id) - 
  (SELECT COUNT(*)::int FROM order_pool o WHERE o.assigned_driver_id = ds.driver_id AND o.status = 'assigned')
),
updated_at = now()
WHERE ds.driver_id = 'a0000001-0000-4000-8000-000000000001';
