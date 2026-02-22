-- =============================================================================
-- 踢出用户登录：使指定用户所有会话失效，下次刷新 token 或校验 session 时会要求重新登录
-- 执行方式：在 Supabase Dashboard → SQL Editor 中执行，或通过 migration 应用
--
-- 说明：
-- - 删除 auth.sessions 后，该用户无法再刷新 token，前端 getSession()/刷新时会被要求重新登录。
--   （当前 access_token 在过期前仍可用，通常约 1 小时内失效。）
-- - 按邮箱踢出：把下面 'admin@test.com' 改成目标邮箱后执行。
-- - 若报错 auth.refresh_tokens 无 user_id：只执行对 auth.sessions 的 DELETE 即可，效果相同。
-- =============================================================================

-- 按邮箱踢出（常用）：先删 refresh_tokens，再删 sessions
DELETE FROM auth.refresh_tokens
WHERE user_id = (SELECT id FROM auth.users WHERE email = 'admin@test.com');

DELETE FROM auth.sessions
WHERE user_id = (SELECT id FROM auth.users WHERE email = 'admin@test.com');

-- 按 user_id 踢出（已知 auth.users.id 时）
-- DELETE FROM auth.refresh_tokens WHERE user_id = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx';
-- DELETE FROM auth.sessions WHERE user_id = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx';

-- 踢出所有用户（慎用，仅维护时清空所有会话）
-- DELETE FROM auth.refresh_tokens;
-- DELETE FROM auth.sessions;
