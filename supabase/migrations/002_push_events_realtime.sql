-- =============================================================================
-- 推送事件表：供网页通过 Supabase Realtime 订阅，与 Bark 同时展示顺路单推送
-- 执行后需在 Supabase Dashboard → Database → Realtime 中确认 push_events 已启用
-- =============================================================================

CREATE TABLE push_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fingerprint     VARCHAR(32) NOT NULL,
  pickup          TEXT NOT NULL,
  delivery        TEXT NOT NULL,
  price           TEXT NOT NULL,
  extra_mins      DOUBLE PRECISION NOT NULL,
  response_url    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE push_events IS '顺路单推送事件，Bark 推送时同步写入，网页通过 Realtime 订阅展示';

CREATE INDEX idx_push_events_created_at ON push_events (created_at DESC);

-- RLS：服务端用 SERVICE_ROLE 写入（绕过 RLS），anon 需能 SELECT 才能收到 Realtime 推送
ALTER TABLE push_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_select_push_events"
  ON push_events FOR SELECT TO anon USING (true);

-- 纳入 Realtime 发布，网页可订阅 INSERT 事件
ALTER PUBLICATION supabase_realtime ADD TABLE push_events;
