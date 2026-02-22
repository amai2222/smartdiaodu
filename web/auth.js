/**
 * 统一鉴权 - 所有需登录页面的入口
 * 依赖：index-config.js（Supabase 已通过页面 script 加载）
 *
 * 用法（任意需登录页面）：
 *   1. 页面引入：config.js → Supabase → index-config.js → [index-state.js 按需] → auth.js → 业务脚本
 *   2. 业务里调用：SmartDiaoduAuth.requireAuth(function () { /* 已登录，拉配置后执行 */ });
 *
 * 登录页需在登录成功后写入：localStorage.setItem(C.STORAGE_TOKEN, access_token 或 "1")
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) {
    window.SmartDiaoduAuth = {
      requireAuth: function () { window.location.replace("login.html"); },
      redirectToLogin: function () { window.location.replace("login.html"); },
      isAuthenticated: function () { return false; }
    };
    return;
  }

  var DEFAULT_LOGIN_URL = "login.html";

  function redirectToLogin(url) {
    window.location.replace(url || DEFAULT_LOGIN_URL);
  }

  function setTokenFromSession(session) {
    try {
      if (session && session.access_token) {
        localStorage.setItem(C.STORAGE_TOKEN, session.access_token);
      } else {
        localStorage.setItem(C.STORAGE_TOKEN, "1");
      }
    } catch (e) {}
  }

  /**
   * 判断当前是否已认证（有 token 或可恢复的 session）
   * 仅同步检查 token，不发起 getSession。
   */
  function hasToken() {
    try {
      return typeof localStorage !== "undefined" && !!localStorage.getItem(C.STORAGE_TOKEN);
    } catch (e) {
      return false;
    }
  }

  /**
   * 要求已登录后才执行 callback，否则跳转登录页。
   * @param {function} callback - 已登录且 loadAppConfig 完成后调用，无参
   * @param {object} options - 可选
   * @param {string} options.loginUrl - 登录页地址，默认 "login.html"
   * @param {function} options.onBlocked - getSession 失败（如被跟踪防护拦截）时调用，可展示提示后仍执行 callback
   */
  function requireAuth(callback, options) {
    var opt = options || {};
    var loginUrl = opt.loginUrl || DEFAULT_LOGIN_URL;

    try {
      if (typeof localStorage === "undefined") {
        redirectToLogin(loginUrl);
        return;
      }
      if (hasToken()) {
        C.loadAppConfig(callback);
        return;
      }
      var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
      if (!url || !anon || !window.supabase) {
        redirectToLogin(loginUrl);
        return;
      }
      var sup = C.getSupabaseClient();
      if (!sup) {
        redirectToLogin(loginUrl);
        return;
      }
      sup.auth.getSession()
        .then(function (r) {
          if (r.data && r.data.session) {
            setTokenFromSession(r.data.session);
            C.loadAppConfig(callback);
          } else {
            redirectToLogin(loginUrl);
          }
        })
        .catch(function () {
          if (typeof opt.onBlocked === "function") {
            opt.onBlocked();
          }
          C.loadAppConfig(function () { callback(); });
        });
    } catch (e) {
      if (typeof opt.onBlocked === "function") {
        opt.onBlocked();
      }
      C.loadAppConfig(function () { callback(); });
    }
  }

  window.SmartDiaoduAuth = {
    requireAuth: requireAuth,
    redirectToLogin: redirectToLogin,
    isAuthenticated: hasToken,
    setTokenFromSession: setTokenFromSession
  };
})();
