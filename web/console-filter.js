/**
 * 过滤控制台中与本站无关的报错（扩展、Cloudflare 统计、百度子域等），减少干扰。
 * 说明：由浏览器直接记录的「网络错误」(如 ERR_ADDRESS_INVALID) 无法从页面内屏蔽。
 */
(function () {
  "use strict";
  var noise = /webextension|cloudflareinsights|beacon\.min\.js|dlswbr\.baidu|reading\s*['"]1['"]/i;

  function isNoise(text) {
    if (typeof text !== "string") return false;
    return noise.test(text);
  }

  function anyNoise(args) {
    for (var i = 0; i < args.length; i++) {
      var a = args[i];
      if (isNoise(String(a))) return true;
      if (a && typeof a === "object" && a.stack && isNoise(a.stack)) return true;
    }
    return false;
  }

  if (typeof window.onerror !== "undefined") {
    var origOnError = window.onerror;
    window.onerror = function (msg, url, line, col, err) {
      var s = (url || "") + " " + (msg || "") + (err && err.stack ? err.stack : "");
      if (noise.test(s)) return true;
      if (typeof origOnError === "function") return origOnError.apply(this, arguments);
      return false;
    };
  }

  if (typeof console !== "undefined") {
    var _error = console.error;
    var _warn = console.warn;
    if (typeof _error === "function") {
      console.error = function () {
        if (anyNoise(arguments)) return;
        _error.apply(console, arguments);
      };
    }
    if (typeof _warn === "function") {
      console.warn = function () {
        if (anyNoise(arguments)) return;
        _warn.apply(console, arguments);
      };
    }
  }
})();
