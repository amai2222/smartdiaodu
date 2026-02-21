-- 修复「登录后连不上数据库」：原策略只允许 anon，登录后变为 authenticated 被拒。
-- 改为 TO public，使匿名与已登录用户均可访问。

-- 1. driver_state
DROP POLICY IF EXISTS "anon_all_driver_state" ON driver_state;
CREATE POLICY "public_all_driver_state" ON driver_state FOR ALL TO public USING (true) WITH CHECK (true);

-- 2. order_pool
DROP POLICY IF EXISTS "anon_all_order_pool" ON order_pool;
CREATE POLICY "public_all_order_pool" ON order_pool FOR ALL TO public USING (true) WITH CHECK (true);

-- 3. push_events（网页内实时推送）
DROP POLICY IF EXISTS "anon_select_push_events" ON push_events;
CREATE POLICY "public_select_push_events" ON push_events FOR SELECT TO public USING (true);

-- 4. driver_route_snapshot（地图上次路线）
DROP POLICY IF EXISTS "anon_all_driver_route_snapshot" ON driver_route_snapshot;
CREATE POLICY "public_all_driver_route_snapshot" ON driver_route_snapshot FOR ALL TO public USING (true) WITH CHECK (true);
