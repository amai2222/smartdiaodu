/**
 * 路线地图 - UI 与事件（导航面板、策略、按钮、入口）
 * 依赖：map-config.js, map-state.js, map-init.js, map-route.js
 */
(function () {
  "use strict";
  if (!document.getElementById("map")) return;
  var M = window.SmartDiaoduMap;
  if (!M) return;

  var debugEl = document.getElementById("mapDebugInfo");
  M._debugState = M._debugState || {};
  function updateDebug(patch) {
    if (!debugEl) return;
    try {
      for (var k in patch) {
        if (Object.prototype.hasOwnProperty.call(patch, k)) {
          M._debugState[k] = patch[k];
        }
      }
      debugEl.textContent = "mapDebug " + JSON.stringify(M._debugState);
      if (window.console && console.debug) console.debug("mapDebug", M._debugState);
    } catch (e) {}
  }

  // 防抖 + 并发锁：避免多个入口（onLoad/visibility/message/按钮）在短时间内重复请求大脑。
  M._routeReqInFlight = false;
  M._routeReqLastAt = 0;

  /** 二次数据库采集：发给大脑前再按 driver_id 从 DB 拉一次，确保司机位置与乘客起终点完整。 */
  function collectDbStateForPlanning(seedState, cb) {
    var state = seedState || {};
    var sup = M.getSupabaseClient && M.getSupabaseClient();
    var driverId = (M.getDriverId && M.getDriverId()) || state.driver_id || "";
    if (!sup || !driverId) { cb(state); return; }
    sup.from("driver_state").select("current_loc").eq("driver_id", driverId).maybeSingle()
      .then(function (r1) {
        var driverLoc = (r1.data && r1.data.current_loc) ? String(r1.data.current_loc).trim() : "";
        return sup.from("order_pool").select("pickup, delivery").eq("assigned_driver_id", driverId).eq("status", "assigned").order("id")
          .then(function (r2) {
            var pickups = [], deliveries = [];
            if (r2.data && Array.isArray(r2.data)) {
              r2.data.forEach(function (row) {
                pickups.push((row.pickup || "").trim());
                deliveries.push((row.delivery || "").trim());
              });
            }
            state.driver_loc = driverLoc || state.driver_loc || "";
            state.pickups = pickups;
            state.deliveries = deliveries;
            state.driver_id = driverId;
            updateDebug({ dbSecondPassPickups: pickups.length, dbSecondPassDriverLoc: state.driver_loc || "" });
            cb(state);
          });
      })
      .catch(function () {
        updateDebug({ dbSecondPassError: "order_pool_or_driver_state_failed" });
        cb(state);
      });
  }

  /** 预计用时文案：统一为「x小时x分钟」（不足 1 小时为 0小时x分钟）。暴露给 map-route 等使用。 */
  function formatDurationFromSeconds(seconds) {
    var mins = Math.round((seconds || 0) / 60);
    var h = Math.floor(mins / 60);
    var m = mins % 60;
    if (h === 0) return "0小时" + m + "分钟";
    return m === 0 ? (h + "小时0分钟") : (h + "小时" + m + "分钟");
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
    var totalStops = (M.route_addresses && M.route_addresses.length) || 0;
    // 若只有司机一个点，则不显示「全部送达」面板，只隐藏导航面板，避免误导。
    if (totalStops <= 1) {
      if (navPanel) navPanel.style.display = "none";
      if (allDonePanel) allDonePanel.style.display = "none";
      return;
    }
    if (nextIdx >= totalStops) {
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

  /** 统一从数据库重算路线（不走 localStorage），避免出现本地缓存与数据库不一致。 */
  M.refreshRouteFromStorage = function () {
    if (M.loadAndDraw) M.loadAndDraw();
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
      state = state || {};
      // 只信数据库：请求时明确携带 driver_id，后端可据此二次按库兜底查询。
      state.driver_id = (M.getDriverId && M.getDriverId()) || "";
      collectDbStateForPlanning(state, function (planningState) {
        var state2 = planningState || {};
        updateDebug({
          dbDriverLoc: state2.driver_loc || "",
          dbPickupCount: (state2.pickups && state2.pickups.length) || 0,
          localPickupCount: 0
        });
        var driverLoc = (state2.driver_loc && String(state2.driver_loc).trim()) || "";
        if (!driverLoc && state2.pickups && state2.pickups.length) {
          var first = state2.pickups[0] && String(state2.pickups[0]).trim();
          if (first) { state2.driver_loc = first; driverLoc = first; }
        }
        if (!driverLoc) {
          statusEl.textContent = "请先在控制台设置当前位置（刷新 GPS 或输入地址）后点「更新路线」";
          M.initMap();
          updateDebug({ error: "no_driver_loc" });
          return;
        }
        if (!state2.pickups || !state2.pickups.length || !state2.deliveries || state2.pickups.length !== state2.deliveries.length) {
          statusEl.textContent = "数据库中当前司机的乘客计划为空或不完整（order_pool）";
          M.initMap();
          updateDebug({ error: "no_pickups_or_mismatch" });
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
        var headers = Object.assign({ "Content-Type": "application/json" }, (M.getAuthHeaders && M.getAuthHeaders()) || {});
        updateDebug({ planningWithPickups: state2.pickups.length, planningDriverLoc: driverLoc });
        var now = Date.now();
        if (M._routeReqInFlight) {
          updateDebug({ requestSkipped: "in_flight" });
          return;
        }
        if (M._routeReqLastAt && now - M._routeReqLastAt < 1200) {
          updateDebug({ requestSkipped: "cooldown" });
          return;
        }
        M._routeReqInFlight = true;
        M._routeReqLastAt = now;
        fetch(base + "/current_route_preview", {
          method: "POST",
          headers: headers,
          body: JSON.stringify({ current_state: state2, tactics: currentTactics })
        })
      .then(function (r) {
        var status = r.status;
        if (!r.ok) {
          return r.json().then(function (d) {
            var msg = (d && d.detail) || r.statusText || String(status);
            updateDebug({ routeStatus: status, routeError: msg });
            throw new Error(msg);
          });
        }
        updateDebug({ routeStatus: status });
        return r.json();
      })
      .then(function (data) {
        M.applyRouteData(data);
        M.saveRouteSnapshot(data);
        updateDebug({ routeAddrCount: (data.route_addresses && data.route_addresses.length) || 0 });
        var routeInfoEl = document.getElementById("routeInfo");
        if (routeInfoEl) routeInfoEl.textContent = M.route_addresses.length <= 1 ? "司机位置（已入库）" : "剩余 " + (M.route_addresses.length - 1) + " 站，预计 " + formatDurationFromSeconds(data.total_time_seconds) + "！（已入库）";
      })
      .catch(function (e) {
        updateDebug({ routeFetchError: (e && e.message) || String(e) });
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
      })
      .then(function () {
        M._routeReqInFlight = false;
      });
      });
    });
  };

  var btnArrived = document.getElementById("btnArrived");
  if (btnArrived) btnArrived.onclick = M.markArrived;

  function bindTap(el, fn) {
    if (!el || !fn) return;
    var touchHandled = false;
    el.addEventListener("click", function (e) {
      if (touchHandled) { touchHandled = false; e.preventDefault(); return; }
      fn(e);
    });
    el.addEventListener("touchstart", function (e) {
      touchHandled = true;
      e.preventDefault();
      fn(e);
      setTimeout(function () { touchHandled = false; }, 400);
    }, { passive: false });
  }
  var btnCollapse = document.getElementById("btnCollapse");
  if (btnCollapse) bindTap(btnCollapse, function () {
    document.body.classList.add("toolbar-hidden");
    var t = document.getElementById("btnToggleUI");
    if (t) t.classList.add("show");
    var p = document.getElementById("routeStrategyPanel");
    if (p) p.classList.remove("show");
  });
  var btnToggleUI = document.getElementById("btnToggleUI");
  if (btnToggleUI) bindTap(btnToggleUI, function () {
    document.body.classList.remove("toolbar-hidden");
    if (btnToggleUI) btnToggleUI.classList.remove("show");
    var p = document.getElementById("routeStrategyPanel");
    if (p) p.classList.remove("show");
    if (M.updateNavPanel) M.updateNavPanel();
  });

  var btnStrategy = document.getElementById("btnStrategy");
  if (btnStrategy) bindTap(btnStrategy, function (e) {
    if (e) e.stopPropagation();
    var otherPanel = document.getElementById("otherRoutesPanel");
    if (otherPanel) otherPanel.style.display = "none";
    var panel = document.getElementById("routeStrategyPanel");
    if (panel) panel.classList.toggle("show");
    if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();
  });

  (function () {
    var strategyPanel = document.getElementById("routeStrategyPanel");
    if (!strategyPanel) return;
    var strategyBtns = strategyPanel.querySelectorAll("button[data-policy]");
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
    var p = document.getElementById("routeStrategyPanel");
    if (p) p.classList.remove("show");
  });
  var routeStrategyPanel = document.getElementById("routeStrategyPanel");
  if (routeStrategyPanel) routeStrategyPanel.addEventListener("click", function (e) {
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

  var btnRefresh = document.getElementById("btnRefresh");
  if (btnRefresh) btnRefresh.onclick = function () {
    var dd = document.getElementById("toolbarRouteDropdown");
    if (dd) dd.classList.remove("show");
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(M.STORAGE_MAP_STOP_INDEX);
      localStorage.removeItem(M.STORAGE_MAP_ROUTE_HASH);
    }
    M.currentStopIndex = 0;
    if (M.loadAndDraw) M.loadAndDraw();
  };

  var btnRestore = document.getElementById("btnRestore");
  if (btnRestore) btnRestore.onclick = function () {
    var dd = document.getElementById("toolbarRouteDropdown");
    if (dd) dd.classList.remove("show");
    var statusEl = document.getElementById("routeInfo");
    if (statusEl) statusEl.textContent = "加载中…";
    M.loadSavedRoute(function (data) {
      if (!statusEl) return;
      if (data) {
        M.applyRouteData(data);
        statusEl.textContent = "已恢复上次线路（剩余 " + (M.route_addresses.length - 1) + " 站，预计 " + formatDurationFromSeconds(data.total_time_seconds) + "！）";
      } else {
        statusEl.textContent = "无已保存线路，请先点「更新路线」规划并入库";
        if (M.bmap) M.clearMapOverlays();
      }
    });
  };

  /** 打开地图时自动按默认策略规划一次；之后不自动刷新。 */
  (function onLoad() {
    var statusEl = document.getElementById("routeInfo");
    var mapEl = document.getElementById("map");
    if (!mapEl) return;
    if (statusEl) statusEl.textContent = "加载配置…";
    updateDebug({
      supabaseUrl: M.getSupabaseUrl && M.getSupabaseUrl(),
      supabaseAnon: M.getSupabaseAnon && (M.getSupabaseAnon() ? "OK" : ""),
      driverId: M.getDriverId && M.getDriverId()
    });
    M.loadAppConfig(function () {
      if (statusEl) statusEl.textContent = "加载中…";
       updateDebug({
         apiBase: M.getApiBase && M.getApiBase(),
         baiduAk: M.getBaiduMapAk && (M.getBaiduMapAk() ? "OK" : "")
       });
      M.initMap();
      // 页面首次打开：固定默认策略自动规划一次。
      M.routePolicyKey = "DEFAULT";
      M.routeAlternativeIndex = 0;
      if (M.loadAndDraw) M.loadAndDraw();
    });
  })();

  // 按用户要求：取消自动重算触发（visibility / postMessage）。
  // 仅在手动点击「更新路线」或切换策略时请求后端。
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
