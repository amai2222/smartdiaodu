/**
 * 控制台 - 配置与 Supabase 连接
 * 依赖：Supabase 已通过 <script> 加载；config.js 可选
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole = window.SmartDiaoduConsole || {};

  C.STORAGE_API = "smartdiaodu_api_base";
  C.STORAGE_TOKEN = "smartdiaodu_token";
  C.STORAGE_USERNAME = "smartdiaodu_username";
  C.STORAGE_SUPABASE_URL = "smartdiaodu_supabase_url";
  C.STORAGE_SUPABASE_ANON = "smartdiaodu_supabase_anon_key";
  C.STORAGE_DRIVER_LOC = "smartdiaodu_driver_loc";
  C.STORAGE_PICKUPS = "smartdiaodu_pickups";
  C.STORAGE_DELIVERIES = "smartdiaodu_deliveries";
  C.STORAGE_DRIVER_ID = "smartdiaodu_driver_id";
  C.DEFAULT_DRIVER_ID = "a0000001-0000-4000-8000-000000000001";

  C.cachedAppConfig = { api_base: "", driver_id: "" };

  C.loadAppConfig = function (cb) {
    var sup = C.getSupabaseClient();
    if (!sup) { if (cb) cb(); return; }
    sup.from("app_config").select("key, value").then(function (r) {
      if (r.data && Array.isArray(r.data)) {
        r.data.forEach(function (row) {
          var k = row.key, v = (row.value || "").trim();
          if (k === "api_base") C.cachedAppConfig.api_base = v.replace(/\/$/, "");
          else if (k === "driver_id") C.cachedAppConfig.driver_id = v;
        });
      }
      if (cb) cb();
    }).catch(function () { if (cb) cb(); });
  };

  C.getDriverId = function () { return C.cachedAppConfig.driver_id || C.DEFAULT_DRIVER_ID; };
  C.getSupabaseClient = function () {
    var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
    if (!url || !anon || !window.supabase) return null;
    return window.supabase.createClient(url, anon);
  };
  C.loadSupabaseScriptThenRetry = function (cb) {
    if (window.supabase) { if (cb) cb(); return; }
    var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
    if (!url || !anon) { if (cb) cb(); return; }
    var script = document.createElement("script");
    script.src = "https://unpkg.com/@supabase/supabase-js@2";
    script.onload = function () { if (cb) cb(); };
    script.onerror = function () { if (cb) cb(); };
    document.head.appendChild(script);
  };
  C.getApiBase = function () { return C.cachedAppConfig.api_base || ""; };
  C.getSupabaseUrl = function () {
    try {
      var v = (typeof localStorage !== "undefined" && localStorage.getItem(C.STORAGE_SUPABASE_URL)) || "";
      if (v) return v;
    } catch (e) {}
    return (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.supabaseUrl) || "";
  };
  C.getSupabaseAnon = function () {
    try {
      var v = (typeof localStorage !== "undefined" && localStorage.getItem(C.STORAGE_SUPABASE_ANON)) || "";
      if (v) return v;
    } catch (e) {}
    return (typeof window.SMARTDIAODU_CONFIG !== "undefined" && window.SMARTDIAODU_CONFIG.supabaseAnonKey) || "";
  };
})();
