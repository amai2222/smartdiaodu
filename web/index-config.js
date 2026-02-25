/**
 * 控制台 - 配置与 Supabase 连接
 * 依赖：Supabase 已通过 <script> 加载；config.js 可选
 * 鉴权：需登录页面请引入 auth.js 并调用 SmartDiaoduAuth.requireAuth(callback)，见 web/PAGES.md
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
  C.STORAGE_ONBOARD = "smartdiaodu_onboard";
  C.STORAGE_WAYPOINTS = "smartdiaodu_waypoints";
  C.STORAGE_DRIVER_ID = "smartdiaodu_driver_id";
  C.STORAGE_TOKEN_SOURCE = "smartdiaodu_token_source";
  C.DEFAULT_DRIVER_ID = "a0000001-0000-4000-8000-000000000001";

  C.cachedAppConfig = { api_base: "", driver_id: "" };

  C.loadAppConfig = function (cb) {
    var sup = C.getSupabaseClient();
    if (!sup) { if (cb) cb(); return; }
    sup.from("app_config").select("key, value").then(function (r) {
      if (r.data && Array.isArray(r.data)) {
        r.data.forEach(function (row) {
          var k = row.key, v = (row.value || "").trim();
          if (k === "api_base") {
            C.cachedAppConfig.api_base = v.replace(/\/$/, "");
            try { localStorage.setItem(C.STORAGE_API, C.cachedAppConfig.api_base); } catch (e) {}
          } else if (k === "driver_id") C.cachedAppConfig.driver_id = v;
        });
      }
      var base = C.cachedAppConfig.api_base;
      var token = null;
      var tokenSource = "";
      try { token = localStorage.getItem(C.STORAGE_TOKEN); tokenSource = localStorage.getItem(C.STORAGE_TOKEN_SOURCE) || ""; } catch (e) {}
      if (base && token && tokenSource === "backend" && typeof fetch === "function") {
        fetch(base + "/auth/me", { headers: { "Authorization": "Bearer " + token } })
          .then(function (res) { return res.ok ? res.json() : null; })
          .then(function (data) {
            if (data && data.driver_id) {
              C.cachedAppConfig.driver_id = data.driver_id;
              try { localStorage.setItem(C.STORAGE_DRIVER_ID, data.driver_id); } catch (e) {}
            }
          })
          .catch(function () {})
          .then(function () { if (cb) cb(); });
      } else {
        if (cb) cb();
      }
    }).catch(function () { if (cb) cb(); });
  };

  /** 当前司机 id：优先登录绑定（localStorage）→ app_config → 默认；多司机各自登录后各自用自己 id */
  C.getDriverId = function () {
    try {
      var fromStorage = localStorage.getItem(C.STORAGE_DRIVER_ID);
      if (fromStorage && fromStorage.trim()) return fromStorage.trim();
    } catch (e) {}
    return C.cachedAppConfig.driver_id || C.DEFAULT_DRIVER_ID;
  };
  C._supabaseClient = null;
  C._supabaseClientUrl = "";
  C._supabaseClientAnon = "";
  C.getSupabaseClient = function () {
    var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
    if (!url || !anon || !window.supabase) return null;
    if (C._supabaseClient && C._supabaseClientUrl === url && C._supabaseClientAnon === anon) return C._supabaseClient;
    C._supabaseClientUrl = url;
    C._supabaseClientAnon = anon;
    var opts = {};
    try {
      if ((localStorage.getItem(C.STORAGE_TOKEN_SOURCE) || "") === "backend") {
        opts.auth = { autoRefreshToken: false, persistSession: false };
      }
    } catch (e) {}
    C._supabaseClient = window.supabase.createClient(url, anon, opts);
    return C._supabaseClient;
  };
  C.loadSupabaseScriptThenRetry = function (cb) {
    if (window.supabase) { if (cb) cb(); return; }
    var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
    if (!url || !anon) { if (cb) cb(); return; }
    var script = document.createElement("script");
    script.src = "vendor/supabase.js";
    script.onload = function () { if (cb) cb(); };
    script.onerror = function () { if (cb) cb(); };
    document.head.appendChild(script);
  };
  C.getApiBase = function () {
    var v = C.cachedAppConfig.api_base || "";
    if (v) return v;
    try { v = localStorage.getItem(C.STORAGE_API); if (v && String(v).trim()) return String(v).trim().replace(/\/$/, ""); } catch (e) {}
    return "";
  };
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
