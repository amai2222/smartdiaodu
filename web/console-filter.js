/**
 * 控制台静默器：清零页面中所有 console 输出。
 */
(function () {
  "use strict";
  if (typeof window === "undefined") return;
  var c = window.console;
  if (!c) return;
  var noop = function () {};
  var methods = ["log", "warn", "error", "info", "debug", "trace"];
  for (var i = 0; i < methods.length; i++) {
    var m = methods[i];
    if (typeof c[m] === "function") c[m] = noop;
  }
})();
