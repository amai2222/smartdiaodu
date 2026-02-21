-- 允许控制台读取司机姓名/车牌并更新车牌（用户名绑定车牌）
ALTER TABLE drivers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_select_drivers" ON drivers;
CREATE POLICY "public_select_drivers" ON drivers FOR SELECT TO public USING (true);

DROP POLICY IF EXISTS "public_update_drivers_plate" ON drivers;
CREATE POLICY "public_update_drivers_plate" ON drivers FOR UPDATE TO public USING (true) WITH CHECK (true);

COMMENT ON COLUMN drivers.plate_number IS '车牌号，用于路线规划/接单评估时规避限行';
