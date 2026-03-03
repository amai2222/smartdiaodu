/**
 * 路线地图 - 配置与 Supabase
 * 依赖：Supabase 已通过 <script> 加载；config.js 可选
 */
(function () {
  "use strict";
  var M = window.SmartDiaoduMap = window.SmartDiaoduMap || {};

  M.STORAGE_API = "smartdiaodu_api_base";
  M.STORAGE_DRIVER_LOC = "smartdiaodu_driver_loc";
  M.STORAGE_PICKUPS = "smartdiaodu_pickups";
  M.STORAGE_DELIVERIES = "smartdiaodu_deliveries";
  M.STORAGE_ONBOARD = "smartdiaodu_onboard";
  M.STORAGE_WAYPOINTS = "smartdiaodu_waypoints";
  M.STORAGE_SUPABASE_URL = "smartdiaodu_supabase_url";
  M.STORAGE_SUPABASE_ANON = "smartdiaodu_supabase_anon_key";
  M.STORAGE_DRIVER_ID = "smartdiaodu_driver_id";
  M.STORAGE_MAP_STOP_INDEX = "smartdiaodu_map_stop_index";
  M.STORAGE_MAP_ROUTE_HASH = "smartdiaodu_map_route_hash";
  M.DEFAULT_DRIVER_ID = "a0000001-0000-4000-8000-000000000001";

  M.cachedAppConfig = { api_base: "", baidu_map_ak: "", driver_id: "" };

  M.loadAppConfig = function (cb) {
    var sup = M.getSupabaseClient();
    if (!sup) {
      try {
        var fromStorage = typeof localStorage !== "undefined" && localStorage.getItem(M.STORAGE_API);
        if (fromStorage && String(fromStorage).trim()) M.cachedAppConfig.api_base = String(fromStorage).trim().replace(/\/$/, "");
        if (typeof window.SMARTDIAODU_CONFIG !== "undefined") {
          if (window.SMARTDIAODU_CONFIG.apiBase && !M.cachedAppConfig.api_base) M.cachedAppConfig.api_base = String(window.SMARTDIAODU_CONFIG.apiBase).trim().replace(/\/$/, "");
          if (window.SMARTDIAODU_CONFIG.driverId && !M.cachedAppConfig.driver_id) M.cachedAppConfig.driver_id = String(window.SMARTDIAODU_CONFIG.driverId).trim();
        }
      } catch (e) {}
      if (cb) cb();
      return;
    }
    sup.from("app_config").select("key, value").then(function (r) {
      if (r.data && Array.isArray(r.data)) {
        r.data.forEach(function (row) {
          var k = row.key, v = (row.value || "").trim();
          if (k === "api_base") M.cachedAppConfig.api_base = v.replace(/\/$/, "");
          else if (k === "baidu_map_ak") M.cachedAppConfig.baidu_map_ak = v;
          else if (k === "driver_id") M.cachedAppConfig.driver_id = v;
        });
      }
      try {
        var fromStorage = typeof localStorage !== "undefined" && localStorage.getItem(M.STORAGE_API);
        if (fromStorage && String(fromStorage).trim() && !M.cachedAppConfig.api_base) M.cachedAppConfig.api_base = String(fromStorage).trim().replace(/\/$/, "");
      } catch (e) {}
      if (cb) cb();
    }).catch(function () { if (cb) cb(); });
  };

  M.getApiBase = function () {
    var v = M.cachedAppConfig.api_base || "";
    if (v) return v;
    try { v = typeof localStorage !== "undefined" && localStorage.getItem(M.STORAGE_API); if (v && String(v).trim()) return String(v).trim().replace(/\/$/, ""); } catch (e) {}
    if (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.apiBase) {
      v = String(window.SMARTDIAODU_CONFIG.apiBase).trim().replace(/\/$/, "");
      if (v) return v;
    }
    return "";
  };
  M.getSupabaseUrl = function () {
    return (typeof localStorage !== "undefined" ? localStorage.getItem(M.STORAGE_SUPABASE_URL) : "") ||
      (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.supabaseUrl) || "";
  };
  M.getSupabaseAnon = function () {
    return (typeof localStorage !== "undefined" ? localStorage.getItem(M.STORAGE_SUPABASE_ANON) : "") ||
      (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.supabaseAnonKey) || "";
  };
  /** 与首页一致：优先用登录绑定司机（localStorage），再 app_config，再默认。这样地图与首页用同一司机，路线/订单一致。 */
  M.getDriverId = function () {
    try {
      var fromStorage = typeof localStorage !== "undefined" && localStorage.getItem(M.STORAGE_DRIVER_ID);
      if (fromStorage && String(fromStorage).trim()) return String(fromStorage).trim();
    } catch (e) {}
    return M.cachedAppConfig.driver_id || M.DEFAULT_DRIVER_ID;
  };
  M._supabaseClient = null;
  M._supabaseClientUrl = "";
  M._supabaseClientAnon = "";
  M.getSupabaseClient = function () {
    var url = M.getSupabaseUrl(), anon = M.getSupabaseAnon();
    if (!url || !anon || !window.supabase) return null;
    if (M._supabaseClient && M._supabaseClientUrl === url && M._supabaseClientAnon === anon) return M._supabaseClient;
    M._supabaseClientUrl = url;
    M._supabaseClientAnon = anon;
    var opts = {};
    try {
      if ((localStorage.getItem("smartdiaodu_token_source") || "") === "backend") {
        opts.auth = { autoRefreshToken: false, persistSession: false };
      }
    } catch (e) {}
    M._supabaseClient = window.supabase.createClient(url, anon, opts);
    return M._supabaseClient;
  };
  M.getBaiduMapAk = function () { return M.cachedAppConfig.baidu_map_ak || ""; };
  /** 请求大脑时带上登录 token（与首页一致），避免后端鉴权时 401 */
  M.getAuthHeaders = function () {
    try {
      var t = typeof localStorage !== "undefined" && localStorage.getItem("smartdiaodu_token");
      if (t && String(t).trim()) return { "Authorization": "Bearer " + String(t).trim() };
    } catch (e) {}
    return {};
  };
})();
