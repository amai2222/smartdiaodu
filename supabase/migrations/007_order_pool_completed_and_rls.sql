-- =============================================================================
-- order_pool 增加 status = 'completed'（已送达）；driver_state/order_pool 允许 anon 读写
-- =============================================================================

-- 1. 允许订单状态为 completed（乘客已下车/已送达）
ALTER TABLE order_pool DROP CONSTRAINT IF EXISTS order_pool_status_check;
ALTER TABLE order_pool ADD CONSTRAINT order_pool_status_check
  CHECK (status IN ('pending_match', 'assigned', 'rejected', 'completed'));

COMMENT ON COLUMN order_pool.status IS 'pending_match=待匹配, assigned=已分配, rejected=已抛弃, completed=已送达';

-- 2. 启用 RLS 并允许 anon 读写 driver_state、order_pool（控制台需读写）
ALTER TABLE driver_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_pool ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_all_driver_state" ON driver_state FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_order_pool" ON order_pool FOR ALL TO anon USING (true) WITH CHECK (true);
