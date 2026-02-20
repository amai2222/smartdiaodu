-- =============================================================================
-- 按邮箱删除 Auth 用户（控制台删不掉“SQL 创建的用户”时，在 SQL Editor 执行）
-- 用法：把下面的 'admin@test.com' 改成要删的邮箱，或直接执行删除该账号
-- =============================================================================

DELETE FROM auth.identities
WHERE user_id IN (SELECT id FROM auth.users WHERE email = 'admin@test.com');

DELETE FROM auth.users
WHERE email = 'admin@test.com';
