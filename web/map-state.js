/**
 * 路线地图 - 状态与路线数据（Supabase 读写、本地存储）
 * 依赖：map-config.js
 */
(function () {
  "use strict";
  var M = window.SmartDiaoduMap;
  if (!M) return;

  M.bmap = null;
  M.lastRouteData = null;
  M.useBMapGL = false;
  M.route_addresses = [];
  M.route_coords = [];
  M.point_types = [];
  M.point_labels = [];
  M.route_path = [];
  M.currentStopIndex = 0;
  M.routePolicyKey = "LEAST_TIME";
  M.lastSegmentResults = [];
  M.routeAlternativeIndex = 0;
  M.POLICY_KEYS_ORDER = ["LEAST_TIME", "LEAST_DISTANCE", "LEAST_FEE", "AVOID_CONGESTION"];
  M.POLICY_NAMES = { LEAST_TIME: "用时最短", LEAST_DISTANCE: "距离最短", LEAST_FEE: "费用最省", AVOID_CONGESTION: "躲避拥堵" };
  M.zoomRedrawTimer = null;
  M.lastRedrawZoom = null;

  M.getCurrentState = function () {
    var driver_loc = (typeof localStorage !== "undefined" && localStorage.getItem(M.STORAGE_DRIVER_LOC)) || "";
    var pickups = [], deliveries = [];
    try {
      var p = localStorage.getItem(M.STORAGE_PICKUPS), d = localStorage.getItem(M.STORAGE_DELIVERIES);
      if (p) pickups = JSON.parse(p);
      if (d) deliveries = JSON.parse(d);
    } catch (e) {}
    return { driver_loc: driver_loc || "如东县委党校", pickups: pickups, deliveries: deliveries };
  };

  M.loadStateFromSupabase = function (cb) {
    var sup = M.getSupabaseClient();
    if (!sup) { if (cb) cb(M.getCurrentState()); return; }
    var driverId = M.getDriverId();
    sup.from("driver_state").select("current_loc").eq("driver_id", driverId).maybeSingle()
      .then(function (r) {
        var driver_loc = (r.data && r.data.current_loc) ? String(r.data.current_loc).trim() : "";
        return sup.from("order_pool").select("pickup, delivery").eq("assigned_driver_id", driverId).eq("status", "assigned").order("id")
          .then(function (orders) {
            var pickups = [], deliveries = [];
            if (orders.data && Array.isArray(orders.data)) {
              orders.data.forEach(function (o) {
                pickups.push(o.pickup || "");
                deliveries.push(o.delivery || "");
              });
            }
            var state = { driver_loc: driver_loc || "如东县委党校", pickups: pickups, deliveries: deliveries };
            if (typeof localStorage !== "undefined") {
              localStorage.setItem(M.STORAGE_DRIVER_LOC, state.driver_loc);
              localStorage.setItem(M.STORAGE_PICKUPS, JSON.stringify(state.pickups));
              localStorage.setItem(M.STORAGE_DELIVERIES, JSON.stringify(state.deliveries));
            }
            if (cb) cb(state);
            return state;
          });
      })
      .catch(function () { if (cb) cb(M.getCurrentState()); });
  };

  M.saveStopIndex = function () {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(M.STORAGE_MAP_STOP_INDEX, String(M.currentStopIndex));
      localStorage.setItem(M.STORAGE_MAP_ROUTE_HASH, M.lastRouteData ? (M.route_addresses.join("|") || "") : "");
    }
  };

  M.applyRouteData = function (data) {
    M.route_addresses = data.route_addresses || [];
    M.route_coords = data.route_coords || [];
    M.point_types = data.point_types || [];
    M.point_labels = data.point_labels || [];
    M.route_path = Array.isArray(data.route_path) ? data.route_path : [];
    M.lastRouteData = data;
    var hash = M.route_addresses.join("|");
    var savedHash = typeof localStorage !== "undefined" ? localStorage.getItem(M.STORAGE_MAP_ROUTE_HASH) : "";
    var savedIdx = typeof localStorage !== "undefined" ? parseInt(localStorage.getItem(M.STORAGE_MAP_STOP_INDEX), 10) : 0;
    M.currentStopIndex = (hash === savedHash && !isNaN(savedIdx)) ? Math.max(0, Math.min(savedIdx, M.route_addresses.length - 1)) : 0;
    M.saveStopIndex();
    if (M.initMap) M.initMap();
    if (M.drawRouteFromIndex) M.drawRouteFromIndex(M.currentStopIndex);
    if (M.updateNavPanel) M.updateNavPanel();
    if (M.bmap && typeof M.bmap.invalidateSize === "function") M.bmap.invalidateSize();
  };

  M.saveRouteSnapshot = function (data) {
    var sup = M.getSupabaseClient();
    if (!sup || !data || !(data.route_addresses && data.route_addresses.length)) return;
    var payload = {
      driver_id: M.getDriverId(),
      route_addresses: data.route_addresses,
      route_coords: data.route_coords || [],
      point_types: data.point_types || [],
      point_labels: data.point_labels || [],
      total_time_seconds: Math.max(0, parseInt(data.total_time_seconds, 10) || 0)
    };
    sup.from("driver_route_snapshot").upsert(payload, { onConflict: "driver_id" }).then(function () {});
  };

  M.loadSavedRoute = function (cb) {
    var sup = M.getSupabaseClient();
    if (!sup) { if (cb) cb(null); return; }
    sup.from("driver_route_snapshot").select("route_addresses, route_coords, point_types, point_labels, total_time_seconds")
      .eq("driver_id", M.getDriverId()).maybeSingle()
      .then(function (r) {
        var d = r.data;
        if (d && Array.isArray(d.route_addresses) && d.route_addresses.length > 0 && Array.isArray(d.route_coords) && d.route_coords.length > 0) {
          if (cb) cb({
            route_addresses: d.route_addresses,
            route_coords: d.route_coords,
            point_types: Array.isArray(d.point_types) ? d.point_types : [],
            point_labels: Array.isArray(d.point_labels) ? d.point_labels : [],
            total_time_seconds: d.total_time_seconds || 0
          });
        } else {
          if (cb) cb(null);
        }
      })
      .catch(function () { if (cb) cb(null); });
  };
})();
