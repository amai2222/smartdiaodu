-- 循环计划配置与计划批次落库，重启后端后仍保留
-- 1. 循环计划配置表（单行，id=1）
CREATE TABLE IF NOT EXISTS planned_trip_cycle_config (
  id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  cycle_origin text NOT NULL DEFAULT '',
  cycle_destination text NOT NULL DEFAULT '',
  cycle_departure_time text NOT NULL DEFAULT '06:00',
  cycle_interval_hours integer NOT NULL DEFAULT 12 CHECK (cycle_interval_hours >= 1 AND cycle_interval_hours <= 24),
  cycle_rounds integer NOT NULL DEFAULT 2 CHECK (cycle_rounds >= 1 AND cycle_rounds <= 10),
  cycle_stopped boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE planned_trip_cycle_config IS '循环计划配置：首次起点/终点、去的时间、间隔、找单轮次、是否停止循环';
COMMENT ON COLUMN planned_trip_cycle_config.cycle_rounds IS '找单计划轮次，默认2=当天回程+次日去程';
COMMENT ON COLUMN planned_trip_cycle_config.cycle_stopped IS 'true=不再自动追加计划';

ALTER TABLE planned_trip_cycle_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_select_planned_trip_cycle_config" ON planned_trip_cycle_config;
CREATE POLICY "public_select_planned_trip_cycle_config" ON planned_trip_cycle_config FOR SELECT TO public USING (true);

INSERT INTO planned_trip_cycle_config (id, cycle_origin, cycle_destination, cycle_departure_time, cycle_interval_hours, cycle_rounds, cycle_stopped)
VALUES (1, '', '', '06:00', 12, 2, false)
ON CONFLICT (id) DO NOTHING;

-- 2. 计划批次表（多行，按 sort_order 排序）
CREATE TABLE IF NOT EXISTS planned_trip_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sort_order integer NOT NULL DEFAULT 0,
  origin text NOT NULL DEFAULT '',
  destination text NOT NULL DEFAULT '',
  departure_time text NOT NULL DEFAULT '',
  time_window_minutes integer NOT NULL DEFAULT 30,
  min_orders integer NOT NULL DEFAULT 2,
  max_orders integer NOT NULL DEFAULT 4,
  completed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE planned_trip_plans IS '循环计划批次：每行一批（出发地、目的地、出发时间等），completed=true 表示已结束找单';
CREATE INDEX IF NOT EXISTS idx_planned_trip_plans_sort ON planned_trip_plans (completed, sort_order, departure_time);

ALTER TABLE planned_trip_plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_select_planned_trip_plans" ON planned_trip_plans;
CREATE POLICY "public_select_planned_trip_plans" ON planned_trip_plans FOR SELECT TO public USING (true);
