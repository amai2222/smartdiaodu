-- =============================================================================
-- 规划线路入库：每司机保留一份「上次规划结果」快照，供地图恢复上次线路
-- =============================================================================

CREATE TABLE driver_route_snapshot (
  driver_id           UUID NOT NULL PRIMARY KEY REFERENCES drivers (id) ON DELETE CASCADE,
  route_addresses      JSONB NOT NULL DEFAULT '[]',
  route_coords         JSONB NOT NULL DEFAULT '[]',
  point_types          JSONB NOT NULL DEFAULT '[]',
  point_labels         JSONB NOT NULL DEFAULT '[]',
  total_time_seconds   INTEGER NOT NULL DEFAULT 0 CHECK (total_time_seconds >= 0),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE driver_route_snapshot IS '每司机一条：上次规划线路快照（途经点地址、经纬度、类型、标签、总耗时），地图页可恢复显示';

ALTER TABLE driver_route_snapshot ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_all_driver_route_snapshot" ON driver_route_snapshot FOR ALL TO anon USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION set_driver_route_snapshot_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trigger_driver_route_snapshot_updated_at
  BEFORE UPDATE ON driver_route_snapshot
  FOR EACH ROW EXECUTE PROCEDURE set_driver_route_snapshot_updated_at();
