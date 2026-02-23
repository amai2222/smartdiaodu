-- 所有模式相关设置按司机（driver_id）进库，循环计划与计划批次跟随司机
-- 1. 调度模式及模式参数表（每司机一行）
CREATE TABLE IF NOT EXISTS driver_mode_config (
  driver_id uuid PRIMARY KEY REFERENCES drivers (id) ON DELETE CASCADE,
  mode text NOT NULL DEFAULT 'mode2' CHECK (mode IN ('mode1', 'mode2', 'mode3', 'pause')),
  mode2_detour_min integer NOT NULL DEFAULT 20 CHECK (mode2_detour_min >= 0),
  mode2_detour_max integer NOT NULL DEFAULT 60 CHECK (mode2_detour_max >= 0),
  mode2_high_profit_threshold numeric(10,2) NOT NULL DEFAULT 100 CHECK (mode2_high_profit_threshold >= 0),
  mode3_max_minutes_to_pickup integer NOT NULL DEFAULT 30 CHECK (mode3_max_minutes_to_pickup >= 1),
  mode3_max_detour_minutes integer NOT NULL DEFAULT 25 CHECK (mode3_max_detour_minutes >= 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE driver_mode_config IS '每司机一行：调度模式及半路吸尘器/附近接力参数，落库跟随用户';
COMMENT ON COLUMN driver_mode_config.mode IS 'mode1=循环计划, mode2=半路吸尘器, mode3=附近接力, pause=停止接单';

ALTER TABLE driver_mode_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_select_driver_mode_config" ON driver_mode_config;
CREATE POLICY "public_select_driver_mode_config" ON driver_mode_config FOR SELECT TO public USING (true);

-- 2. 循环计划配置改为按司机（为 019 已存在表增加 driver_id）
ALTER TABLE planned_trip_cycle_config ADD COLUMN IF NOT EXISTS driver_id uuid REFERENCES drivers (id) ON DELETE CASCADE;
-- 已有单行时：绑定到第一个司机，若无司机则保持 NULL（兼容旧库）
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM planned_trip_cycle_config WHERE driver_id IS NULL LIMIT 1) THEN
    UPDATE planned_trip_cycle_config SET driver_id = (SELECT id FROM drivers ORDER BY id LIMIT 1) WHERE driver_id IS NULL;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS planned_trip_cycle_config_driver_id_key ON planned_trip_cycle_config (driver_id) WHERE driver_id IS NOT NULL;
-- 允许多行：去掉 id=1 唯一约束，id 改为序列自增便于每司机一行
ALTER TABLE planned_trip_cycle_config DROP CONSTRAINT IF EXISTS planned_trip_cycle_config_id_check;
CREATE SEQUENCE IF NOT EXISTS planned_trip_cycle_config_id_seq;
ALTER TABLE planned_trip_cycle_config ALTER COLUMN id SET DEFAULT nextval('planned_trip_cycle_config_id_seq');
SELECT setval('planned_trip_cycle_config_id_seq', (SELECT COALESCE(MAX(id), 1) FROM planned_trip_cycle_config));

COMMENT ON COLUMN planned_trip_cycle_config.driver_id IS '所属司机，NULL 表示兼容旧单行配置';

-- 3. 计划批次改为按司机
ALTER TABLE planned_trip_plans ADD COLUMN IF NOT EXISTS driver_id uuid REFERENCES drivers (id) ON DELETE CASCADE;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM planned_trip_plans WHERE driver_id IS NULL LIMIT 1) THEN
    UPDATE planned_trip_plans SET driver_id = (SELECT id FROM drivers ORDER BY id LIMIT 1) WHERE driver_id IS NULL;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_planned_trip_plans_driver_id ON planned_trip_plans (driver_id);

COMMENT ON COLUMN planned_trip_plans.driver_id IS '所属司机';
