-- =============================================================================
-- 多司机/车队顺风车智能调度系统 - Supabase (PostgreSQL) 建表脚本
-- 可直接在 Supabase SQL Editor 中执行
-- =============================================================================

-- 启用 UUID 扩展（Supabase 通常已默认启用）
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -----------------------------------------------------------------------------
-- 1. 车队司机表 (drivers)
-- -----------------------------------------------------------------------------
CREATE TABLE drivers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  plate_number  TEXT NOT NULL,
  max_seats     INTEGER NOT NULL DEFAULT 4 CHECK (max_seats >= 1 AND max_seats <= 9),
  status        TEXT NOT NULL DEFAULT 'offline'
    CHECK (status IN ('online', 'offline', 'banned')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE drivers IS '车队司机表';
COMMENT ON COLUMN drivers.status IS 'online=在线, offline=离线, banned=封车';

CREATE INDEX idx_drivers_status ON drivers (status);

-- -----------------------------------------------------------------------------
-- 2. 司机实时动态表 (driver_state) — 每司机一条，由应用 upsert 更新
-- -----------------------------------------------------------------------------
CREATE TABLE driver_state (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id     UUID NOT NULL REFERENCES drivers (id) ON DELETE CASCADE,
  current_loc   TEXT,
  current_lat   DOUBLE PRECISION,
  current_lng   DOUBLE PRECISION,
  empty_seats   INTEGER NOT NULL DEFAULT 4 CHECK (empty_seats >= 0),
  mode         TEXT NOT NULL DEFAULT 'smart'
    CHECK (mode IN ('all', 'smart', 'pause')),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (driver_id)
);

COMMENT ON TABLE driver_state IS '司机实时动态表，每司机一条记录';
COMMENT ON COLUMN driver_state.mode IS 'all=接收所有单, smart=仅接收顺路单, pause=停止接单';

-- driver_id 已在表内 UNIQUE(driver_id)，自动带唯一索引

-- -----------------------------------------------------------------------------
-- 3. 公共订单池表 (order_pool)
-- -----------------------------------------------------------------------------
CREATE TABLE order_pool (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_hash         VARCHAR(32) NOT NULL,
  pickup             TEXT NOT NULL,
  delivery           TEXT NOT NULL,
  price              NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
  status             TEXT NOT NULL DEFAULT 'pending_match'
    CHECK (status IN ('pending_match', 'assigned', 'rejected')),
  assigned_driver_id UUID REFERENCES drivers (id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_hash)
);

COMMENT ON TABLE order_pool IS '公共订单池，探子抓取的订单';
COMMENT ON COLUMN order_pool.order_hash IS 'MD5(pickup_delivery_price) 防重';
COMMENT ON COLUMN order_pool.status IS 'pending_match=待匹配, assigned=已分配, rejected=已抛弃';

-- order_hash 已在表内 UNIQUE，自动带唯一索引
CREATE INDEX idx_order_pool_status ON order_pool (status);
CREATE INDEX idx_order_pool_assigned_driver_id ON order_pool (assigned_driver_id);
CREATE INDEX idx_order_pool_created_at ON order_pool (created_at DESC);

-- -----------------------------------------------------------------------------
-- 4. 实时行程路线表 (active_trips)
-- -----------------------------------------------------------------------------
CREATE TABLE active_trips (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id       UUID NOT NULL REFERENCES drivers (id) ON DELETE CASCADE,
  route_sequence  JSONB NOT NULL DEFAULT '[]',
  total_profit    NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (total_profit >= 0),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (driver_id)
);

COMMENT ON TABLE active_trips IS '每司机当前一条实时行程，route_sequence 为 OR-Tools 算出的途经点顺序及预计到达时间';

-- driver_id 已在表内 UNIQUE(driver_id)，自动带唯一索引

-- -----------------------------------------------------------------------------
-- 可选：updated_at 自动更新触发器（按需启用）
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_driver_state_updated_at
  BEFORE UPDATE ON driver_state
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

CREATE TRIGGER trigger_active_trips_updated_at
  BEFORE UPDATE ON active_trips
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();
