-- =============================================================================
-- 数据库检查命令（只读，不修改数据）
-- 在 Supabase Dashboard → SQL Editor 中一次性执行，得到一张结果表。
--
-- 【本仓库 SQL 规范】Supabase SQL Editor 不支持分段显示多个结果集，
-- 因此「检查 / 诊断」类 SQL 必须用一条语句输出所有检查项（同一张表、多行），
-- 便于一次执行、一次查看。
-- =============================================================================
-- 控制台使用的司机 ID（与 config.js 一致）：a0000001-0000-4000-8000-000000000001

SELECT 检查项, 结果
FROM (
  SELECT 1 AS ord, '1.driver_state' AS 检查项,
    COALESCE(
      (SELECT '有1条 | 位置=' || COALESCE(current_loc,'') || ' | 空座=' || COALESCE(empty_seats::text,'') || ' | 模式=' || COALESCE(mode,'')
       FROM driver_state WHERE driver_id = 'a0000001-0000-4000-8000-000000000001' LIMIT 1),
      '无记录，需执行 006 种子'
    ) AS 结果
  UNION ALL
  SELECT 2, '2.order_pool按status',
    COALESCE(
      (SELECT string_agg(status || ':' || cnt::text, '； ')
       FROM (SELECT status, COUNT(*) AS cnt FROM order_pool WHERE assigned_driver_id = 'a0000001-0000-4000-8000-000000000001' GROUP BY status) t),
      '无订单分配给该司机'
    )
  UNION ALL
  SELECT 3 + sub.row_num::int, '3.订单' || sub.row_num, LEFT(sub.pickup,22) || '→' || LEFT(sub.delivery,22) || ' | ' || sub.status
  FROM (
    SELECT ROW_NUMBER() OVER (ORDER BY created_at) AS row_num, pickup, delivery, status
    FROM order_pool
    WHERE assigned_driver_id = 'a0000001-0000-4000-8000-000000000001'
  ) sub
  UNION ALL
  SELECT 100 + sub2.row_num::int, '4.全表-' || sub2.row_num, LEFT(sub2.pickup,18) || ' | ' || sub2.status || ' | ' || COALESCE(sub2.assigned_driver_id::text,'NULL')
  FROM (
    SELECT ROW_NUMBER() OVER (ORDER BY created_at) AS row_num, pickup, status, assigned_driver_id
    FROM order_pool
    ORDER BY created_at
    LIMIT 5
  ) sub2
) u
ORDER BY ord;
