/**
 * 路线地图 - UI 与事件（导航面板、策略、按钮、入口）
 * 依赖：map-config.js, map-state.js, map-init.js, map-route.js
 */
(function () {
  "use strict";
  var M = window.SmartDiaoduMap;
  if (!M) return;

  /** 预计用时文案：≥1 小时为「x小时x分钟」，否则「x分钟」。暴露给 map-route 等使用。 */
  function formatDurationFromSeconds(seconds) {
    var mins = Math.round((seconds || 0) / 60);
    if (mins >= 60) {
      var h = Math.floor(mins / 60);
      var m = mins % 60;
      return m === 0 ? (h + "小时") : (h + "小时" + m + "分钟");
    }
    return mins + "分钟";
  }
  M.formatDurationFromSeconds = formatDurationFromSeconds;

  M.updateNavPanel = function () {
    var baiduLink = document.getElementById("btnOpenBaiduNav");
    if (baiduLink) {
      var navUrl = (M.route_addresses && M.route_addresses.length >= 2 && M.getNavUrlWithWaypoints) ? M.getNavUrlWithWaypoints() : "#";
      baiduLink.href = navUrl;
      baiduLink.style.display = navUrl === "#" ? "none" : "";
    }
    var nextIdx = M.currentStopIndex + 1;
    var navPanel = document.getElementById("navPanel");
    var allDonePanel = document.getElementById("allDonePanel");
    if (nextIdx >= M.route_addresses.length) {
      navPanel.style.display = "none";
      allDonePanel.style.display = "block";
      return;
    }
    allDonePanel.style.display = "none";
    navPanel.style.display = "block";
    var label = M.point_labels[nextIdx] || M.point_types[nextIdx] || ("第" + (nextIdx + 1) + "站");
    var addr = M.route_addresses[nextIdx] || "";
    document.getElementById("nextStopText").textContent = "下一站: " + label + " " + (addr.length > 18 ? addr.slice(0, 18) + "…" : addr);
  };

  M.markArrived = function () {
    M.currentStopIndex++;
    var addr = M.route_addresses[M.currentStopIndex];
    var typ = M.point_types[M.currentStopIndex];
    if (addr && typeof localStorage !== "undefined") localStorage.setItem(M.STORAGE_DRIVER_LOC, addr);
    var sup = M.getSupabaseClient();
    if (sup) {
      sup.from("driver_state").update({ current_loc: addr || "" }).eq("driver_id", M.getDriverId()).then(function () {});
      if (typ === "delivery" && addr) {
        sup.from("order_pool").select("id").eq("delivery", addr).eq("assigned_driver_id", M.getDriverId()).eq("status", "assigned").limit(1)
          .then(function (r) {
            var row = r.data && r.data[0];
            if (row && row.id) {
              sup.from("order_pool").update({ status: "completed", assigned_driver_id: null }).eq("id", row.id).then(function () {});
              sup.from("driver_state").select("empty_seats").eq("driver_id", M.getDriverId()).maybeSingle().then(function (rr) {
                var next = (rr.data && rr.data.empty_seats != null) ? Math.min(4, rr.data.empty_seats + 1) : 1;
                sup.from("driver_state").update({ empty_seats: next }).eq("driver_id", M.getDriverId()).then(function () {});
              });
            }
          });
      }
    }
    M.saveStopIndex();
    M.drawRouteFromIndex(M.currentStopIndex);
    M.updateNavPanel();
  };

  M.updateStrategyPanelActive = function () {
    var panel = document.getElementById("routeStrategyPanel");
    if (!panel) return;
    var btns = panel.querySelectorAll("button[data-policy]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("active", (btns[i].getAttribute("data-policy") || "").toUpperCase() === (M.routePolicyKey || "DEFAULT").toUpperCase());
    }
  };

  M.redrawRouteOnZoomChange = function () {
    if (!M.bmap || !M.lastRouteData) return;
    M.lastRedrawZoom = typeof M.bmap.getZoom === "function" ? M.bmap.getZoom() : null;
    /* 仅重绘路线与标注，不改变中心/缩放，避免用户缩放后被 setViewport 拉回 */
    if (M.lastSegmentResults && M.lastSegmentResults.length > 0 && M.routeAlternativeIndex > 0) {
      M.redrawFromStoredSegments(true);
    } else {
      M.drawRouteFromIndex(M.currentStopIndex, true);
    }
  };

  /** 用当前 localStorage 状态重新请求路线并重绘（切回地图页时与控制台保持一致，如乘客全下车后路线会清空） */
  M.refreshRouteFromStorage = function () {
    var base = M.getApiBase();
    var statusEl = document.getElementById("routeInfo");
    if (!base) return;
    var state = M.getCurrentState();
    var driverLoc = (state && state.driver_loc) ? String(state.driver_loc).trim() : "";
    if (!driverLoc) {
      if (statusEl) statusEl.textContent = "请先在控制台设置当前位置后点「更新路线」";
      M.initMap();
      return;
    }
    var tacticsMap = { "DEFAULT": 0, "LEAST_TIME": 13, "LEAST_DISTANCE": 12, "AVOID_CONGESTION": 5, "LEAST_FEE": 6, "AVOID_HIGHWAY": 3 };
    var currentTactics = tacticsMap[M.routePolicyKey || "DEFAULT"] || 0;
    if (statusEl) statusEl.textContent = "同步路线中…";
    fetch(base + "/current_route_preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_state: state, tactics: currentTactics })
    })
    .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); }); return r.json(); })
    .then(function (data) {
      M.applyRouteData(data);
      M.saveRouteSnapshot(data);
      if (statusEl) statusEl.textContent = M.route_addresses.length <= 1 ? "司机位置（已与控制台同步）" : "剩余 " + (M.route_addresses.length - 1) + " 站，预计 " + formatDurationFromSeconds(data.total_time_seconds) + "！（已与控制台同步）";
    })
    .catch(function () {
      if (statusEl) statusEl.textContent = "同步路线失败，请点「更新路线」重试";
    });
  };

  M.loadAndDraw = function () {
    var base = M.getApiBase();
    var statusEl = document.getElementById("routeInfo");
    if (!base) {
      M.initMap();
      M.loadSavedRoute(function (data) {
        if (data) {
          M.applyRouteData(data);
          statusEl.textContent = "已恢复上次线路（剩余 " + (M.route_addresses.length - 1) + " 站）；未配置 apiBase 无法重新规划";
        } else {
          statusEl.textContent = "未配置后端（请在 Supabase 表 app_config 中设置 key=api_base）";
        }
      });
      return;
    }
    statusEl.textContent = "从数据库加载计划…";
    M.loadStateFromSupabase(function (state) {
      var driverLoc = (state && state.driver_loc) ? String(state.driver_loc).trim() : "";
      if (!driverLoc) {
        statusEl.textContent = "请先在控制台设置当前位置（刷新 GPS 或输入地址）后点「更新路线」";
        M.initMap();
        return;
      }
      var tacticsMap = {
        "DEFAULT": 0,
        "LEAST_TIME": 13,
        "LEAST_DISTANCE": 12,
        "AVOID_CONGESTION": 5,
        "LEAST_FEE": 6,
        "AVOID_HIGHWAY": 3
      };
      var currentTactics = tacticsMap[M.routePolicyKey || "DEFAULT"] || 0;
      statusEl.textContent = "规划路线中…";
      fetch(base + "/current_route_preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_state: state, tactics: currentTactics })
      })
      .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); }); return r.json(); })
      .then(function (data) {
        M.applyRouteData(data);
        M.saveRouteSnapshot(data);
        var routeInfoEl = document.getElementById("routeInfo");
        if (routeInfoEl) routeInfoEl.textContent = M.route_addresses.length <= 1 ? "司机位置（已入库）" : "剩余 " + (M.route_addresses.length - 1) + " 站，预计 " + formatDurationFromSeconds(data.total_time_seconds) + "！（已入库）";
      })
      .catch(function (e) {
        document.getElementById("navPanel").style.display = "none";
        var restrictionEl = document.getElementById("restrictionHint");
        if (restrictionEl) restrictionEl.style.display = "none";
        M.initMap();
        var msg = e.message || String(e);
        var hint = "";
        if (/failed to fetch|networkerror|load failed/i.test(msg) && window.location.protocol === "https:") {
          hint = "（HTTPS 页面请求 HTTP 后端可能被浏览器拦截，请将后端改为 HTTPS 或在本机用 HTTP 打开页面）";
        } else if (/地址无法解析|地理编码|地址.*解析/i.test(msg)) {
          hint = "。请到控制台修改「我的位置」或乘客起终点为更详细地址（如带区县、街道）后重试「更新路线」";
        }
        document.getElementById("routeInfo").textContent = "路线加载失败：" + msg + hint + "，仅显示地图";
      });
    });
  };

  var btnArrived = document.getElementById("btnArrived");
  if (btnArrived) btnArrived.onclick = M.markArrived;

  document.getElementById("btnCollapse").onclick = function () {
    document.body.classList.add("toolbar-hidden");
    document.getElementById("btnToggleUI").classList.add("show");
    document.getElementById("routeStrategyPanel").classList.remove("show");
  };
  document.getElementById("btnToggleUI").onclick = function () {
    document.body.classList.remove("toolbar-hidden");
    document.getElementById("btnToggleUI").classList.remove("show");
    document.getElementById("routeStrategyPanel").classList.remove("show");
    M.updateNavPanel();
  };

  document.getElementById("btnStrategy").onclick = function (e) {
    e.stopPropagation();
    var otherPanel = document.getElementById("otherRoutesPanel");
    if (otherPanel) otherPanel.style.display = "none";
    var panel = document.getElementById("routeStrategyPanel");
    panel.classList.toggle("show");
    M.updateStrategyPanelActive();
  };

  (function () {
    var strategyBtns = document.getElementById("routeStrategyPanel").querySelectorAll("button[data-policy]");
    for (var i = 0; i < strategyBtns.length; i++) {
      (function (btn) {
        btn.onclick = function () {
          var key = (btn.getAttribute("data-policy") || "DEFAULT").toUpperCase();
          M.routePolicyKey = key;
          // 💡 核心修复：无论切什么策略，必须把选中序号重置为 0！避免越界触发龟速重算！
          M.routeAlternativeIndex = 0;
          document.getElementById("routeStrategyPanel").classList.remove("show");
          M.updateStrategyPanelActive();
          document.getElementById("routeInfo").textContent = "正在按「" + (btn.textContent || key) + "」重新规划…";
          M.loadAndDraw();
        };
      })(strategyBtns[i]);
    }
    var btnOther = document.getElementById("btnOtherRoute");
    if (btnOther) {
      btnOther.onclick = function () {
        document.getElementById("routeStrategyPanel").classList.remove("show");

        var n = (M.route_paths && M.route_paths.length) ? M.route_paths.length : 1;
        if (n <= 1) {
          document.getElementById("routeInfo").textContent = "当前策略下无其他备选线路";
          return;
        }

        M.routeAlternativeIndex = (M.routeAlternativeIndex + 1) % n;

        if (M.drawRouteFromIndex) M.drawRouteFromIndex(M.currentStopIndex, true);
        if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();

        var durStr = "";
        if (M.route_durations && M.route_durations[M.routeAlternativeIndex]) {
          durStr = " (约 " + formatDurationFromSeconds(M.route_durations[M.routeAlternativeIndex]) + ")";
        }
        document.getElementById("routeInfo").textContent = "已切换至方案 " + (M.routeAlternativeIndex + 1) + durStr;
      };
    }
  })();

  document.addEventListener("click", function () {
    document.getElementById("routeStrategyPanel").classList.remove("show");
  });
  document.getElementById("routeStrategyPanel").addEventListener("click", function (e) {
    e.stopPropagation();
  });

  (function () {
    var btnMenu = document.getElementById("btnRouteMenu");
    var dropdown = document.getElementById("toolbarRouteDropdown");
    if (btnMenu && dropdown) {
      btnMenu.onclick = function (e) {
        e.stopPropagation();
        document.getElementById("routeStrategyPanel").classList.remove("show");
        dropdown.classList.toggle("show");
      };
      dropdown.onclick = function (e) { e.stopPropagation(); };
      document.addEventListener("click", function () { dropdown.classList.remove("show"); });
    }
  })();

  document.getElementById("btnRefresh").onclick = function () {
    document.getElementById("toolbarRouteDropdown").classList.remove("show");
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(M.STORAGE_MAP_STOP_INDEX);
      localStorage.removeItem(M.STORAGE_MAP_ROUTE_HASH);
    }
    M.currentStopIndex = 0;
    M.loadAndDraw();
  };

  document.getElementById("btnRestore").onclick = function () {
    document.getElementById("toolbarRouteDropdown").classList.remove("show");
    var statusEl = document.getElementById("routeInfo");
    statusEl.textContent = "加载中…";
    M.loadSavedRoute(function (data) {
      if (data) {
        M.applyRouteData(data);
        statusEl.textContent = "已恢复上次线路（剩余 " + (M.route_addresses.length - 1) + " 站，预计 " + formatDurationFromSeconds(data.total_time_seconds) + "！）";
      } else {
        statusEl.textContent = "无已保存线路，请先点「更新路线」规划并入库";
        if (M.bmap) M.clearMapOverlays();
      }
    });
  };

  (function onLoad() {
    var statusEl = document.getElementById("routeInfo");
    statusEl.textContent = "加载配置…";
    M.loadAppConfig(function () {
      statusEl.textContent = "加载中…";
      M.initMap();
      M.loadSavedRoute(function (data) {
        if (data) {
          M.applyRouteData(data);
          statusEl.textContent = "已恢复上次线路（剩余 " + (M.route_addresses.length - 1) + " 站，预计 " + formatDurationFromSeconds(data.total_time_seconds) + "！）";
        } else {
          M.loadAndDraw();
        }
      });
    });
  })();

  /** 切回地图页时用控制台最新状态刷新路线（如乘客全下车后不再显示旧站点）；仅从「隐藏」切回时刷新，避免首屏重复请求 */
  (function () {
    var hadBeenHidden = false;
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        hadBeenHidden = true;
      } else if (document.visibilityState === "visible" && hadBeenHidden && M.getApiBase()) {
        hadBeenHidden = false;
        M.refreshRouteFromStorage();
      }
    });
  })();
})();

/** 返回控制台：不依赖 M，在 iframe 内时「返回」「返回控制台」立即通知父页切回首页。touchstart 即发 postMessage，避免 iOS 上 touchend/click 不触发导致无反应。 */
(function () {
  if (window === window.top) return;
  function postBack() {
    try { window.parent.postMessage({ type: "smartdiaodu_map_back" }, "*"); } catch (err) {}
  }
  function bindBackLink(el) {
    if (!el) return;
    el.addEventListener("touchstart", function (e) {
      e.preventDefault();
      postBack();
    }, { passive: false });
    el.addEventListener("touchend", function (e) { e.preventDefault(); }, { passive: false });
    el.addEventListener("click", function (e) {
      e.preventDefault();
      postBack();
    });
  }
  bindBackLink(document.getElementById("btnBackToConsole"));
  bindBackLink(document.getElementById("btnBackToConsoleFromAllDone"));
})();
