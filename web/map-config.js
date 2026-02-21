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
  M.STORAGE_SUPABASE_URL = "smartdiaodu_supabase_url";
  M.STORAGE_SUPABASE_ANON = "smartdiaodu_supabase_anon_key";
  M.STORAGE_DRIVER_ID = "smartdiaodu_driver_id";
  M.STORAGE_MAP_STOP_INDEX = "smartdiaodu_map_stop_index";
  M.STORAGE_MAP_ROUTE_HASH = "smartdiaodu_map_route_hash";
  M.DEFAULT_DRIVER_ID = "a0000001-0000-4000-8000-000000000001";

  M.cachedAppConfig = { api_base: "", baidu_map_ak: "", driver_id: "" };

  M.loadAppConfig = function (cb) {
    var sup = M.getSupabaseClient();
    if (!sup) { if (cb) cb(); return; }
    sup.from("app_config").select("key, value").then(function (r) {
      if (r.data && Array.isArray(r.data)) {
        r.data.forEach(function (row) {
          var k = row.key, v = (row.value || "").trim();
          if (k === "api_base") M.cachedAppConfig.api_base = v.replace(/\/$/, "");
          else if (k === "baidu_map_ak") M.cachedAppConfig.baidu_map_ak = v;
          else if (k === "driver_id") M.cachedAppConfig.driver_id = v;
        });
      }
      if (cb) cb();
    }).catch(function () { if (cb) cb(); });
  };

  M.getApiBase = function () { return M.cachedAppConfig.api_base || ""; };
  M.getSupabaseUrl = function () {
    return (typeof localStorage !== "undefined" ? localStorage.getItem(M.STORAGE_SUPABASE_URL) : "") ||
      (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.supabaseUrl) || "";
  };
  M.getSupabaseAnon = function () {
    return (typeof localStorage !== "undefined" ? localStorage.getItem(M.STORAGE_SUPABASE_ANON) : "") ||
      (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.supabaseAnonKey) || "";
  };
  M.getDriverId = function () { return M.cachedAppConfig.driver_id || M.DEFAULT_DRIVER_ID; };
  M._supabaseClient = null;
  M._supabaseClientUrl = "";
  M._supabaseClientAnon = "";
  M.getSupabaseClient = function () {
    var url = M.getSupabaseUrl(), anon = M.getSupabaseAnon();
    if (!url || !anon || !window.supabase) return null;
    if (M._supabaseClient && M._supabaseClientUrl === url && M._supabaseClientAnon === anon) return M._supabaseClient;
    M._supabaseClientUrl = url;
    M._supabaseClientAnon = anon;
    M._supabaseClient = window.supabase.createClient(url, anon);
    return M._supabaseClient;
  };
  M.getBaiduMapAk = function () { return M.cachedAppConfig.baidu_map_ak || ""; };
})();
