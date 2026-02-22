/**
 * 设置页 - 车牌、调度模式、计划、清空途经、绕路/高收益
 * 依赖：index-config.js, index-state.js, auth.js（统一鉴权）
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) {
    if (window.SmartDiaoduAuth) window.SmartDiaoduAuth.redirectToLogin();
    else window.location.replace("login.html");
    return;
  }

  function status(msg) {
    var el = document.getElementById("setupStatus");
    if (el) el.textContent = msg || "";
  }

  function refreshMode() {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/driver_mode").then(function (r) { return r.json(); }).then(function (d) {
      var mode = d.mode || "mode2";
      document.querySelectorAll(".mode-btn").forEach(function (btn) {
        btn.classList.remove("border-accent", "bg-accent/20");
        if (btn.getAttribute("data-mode") === mode) btn.classList.add("border-accent", "bg-accent/20");
      });
    });
  }

  var modeModalOverlay = document.getElementById("modeModalOverlay");
  var modeModal = document.getElementById("modeModal");
  var modeModalTitle = document.getElementById("modeModalTitle");
  var modeModalBody = document.getElementById("modeModalBody");
  var modeModalClose = document.getElementById("modeModalClose");

  function openModal(title, bodyHTML) {
    if (modeModalTitle) modeModalTitle.textContent = title || "";
    if (modeModalBody) modeModalBody.innerHTML = bodyHTML || "";
    if (modeModalOverlay) {
      modeModalOverlay.classList.remove("hidden");
      modeModalOverlay.setAttribute("aria-hidden", "false");
    }
  }

  function closeModal() {
    if (modeModalOverlay) {
      modeModalOverlay.classList.add("hidden");
      modeModalOverlay.setAttribute("aria-hidden", "true");
    }
  }

  function openMode1Modal() {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "mode1" }) })
      .then(function () { refreshMode(); });
    openModal("下次计划",
      "<div id=\"planList\" class=\"space-y-4 mb-4\"></div>" +
      "<button type=\"button\" id=\"btnAddPlan\" class=\"w-full py-3 rounded-xl border border-dashed border-border text-muted font-medium mb-3\">＋ 添加下一批计划</button>" +
      "<p class=\"text-sm text-muted\">按时间排序，优先第 1 批找单。计划不删；当前批跑完后点「结束找单」即可进入下一批。</p>");
    loadPlannedTrip();
    var btnAddPlan = document.getElementById("btnAddPlan");
    if (btnAddPlan) {
      btnAddPlan.onclick = function () {
        var body = { origin: "如东荣生花苑", destination: "上海", departure_time: "06:00", time_window_minutes: 30, min_orders: 2, max_orders: 4 };
        fetch(base + "/planned_trip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
          .then(function () { status("已添加一批，请填写时间与地点后保存"); loadPlannedTrip(); });
      };
    }
  }

  function openMode2Modal() {
    var base = C.getApiBase();
    if (!base) return;
    openModal("半路吸尘器",
      "<p class=\"text-muted text-sm mb-3\">绕路容忍度（分钟）</p>" +
      "<div class=\"flex items-center gap-4 mb-4\">" +
      "<button type=\"button\" id=\"detourMinus\" class=\"btn-touch w-12 h-12 rounded-xl bg-[#0c0c0f] border border-border text-xl font-bold hover:bg-border\">−</button>" +
      "<span id=\"detourVal\" class=\"text-big font-semibold min-w-[3rem] text-center\">15</span>" +
      "<button type=\"button\" id=\"detourPlus\" class=\"btn-touch w-12 h-12 rounded-xl bg-[#0c0c0f] border border-border text-xl font-bold hover:bg-border\">+</button>" +
      "</div>" +
      "<p class=\"text-muted text-sm mb-3\">高收益门槛（元）</p>" +
      "<div class=\"flex items-center gap-4 mb-4\">" +
      "<button type=\"button\" id=\"profitMinus\" class=\"btn-touch w-12 h-12 rounded-xl bg-[#0c0c0f] border border-border text-xl font-bold hover:bg-border\">−</button>" +
      "<span id=\"profitVal\" class=\"text-big font-semibold min-w-[3rem] text-center\">100</span>" +
      "<button type=\"button\" id=\"profitPlus\" class=\"btn-touch w-12 h-12 rounded-xl bg-[#0c0c0f] border border-border text-xl font-bold hover:bg-border\">+</button>" +
      "</div>" +
      "<button type=\"button\" id=\"mode2Confirm\" class=\"w-full py-3 rounded-xl bg-accent text-white font-medium\">使用此模式</button>");
    fetch(base + "/driver_mode_config").then(function (r) { return r.json(); }).then(function (c) {
      var dv = document.getElementById("detourVal");
      var pv = document.getElementById("profitVal");
      if (dv) dv.textContent = c.mode2_detour_max != null ? c.mode2_detour_max : 15;
      if (pv) pv.textContent = c.mode2_high_profit_threshold != null ? c.mode2_high_profit_threshold : 100;
    });
    var detourVal = document.getElementById("detourVal");
    var profitVal = document.getElementById("profitVal");
    document.getElementById("detourMinus").onclick = function () {
      var v = Math.max(0, parseInt(detourVal.textContent, 10) - 5);
      detourVal.textContent = v;
      saveDetour(v);
    };
    document.getElementById("detourPlus").onclick = function () {
      var v = parseInt(detourVal.textContent, 10) + 5;
      detourVal.textContent = v;
      saveDetour(v);
    };
    document.getElementById("profitMinus").onclick = function () {
      var v = Math.max(0, parseInt(profitVal.textContent, 10) - 10);
      profitVal.textContent = v;
      saveProfit(v);
    };
    document.getElementById("profitPlus").onclick = function () {
      var v = parseInt(profitVal.textContent, 10) + 10;
      profitVal.textContent = v;
      saveProfit(v);
    };
    document.getElementById("mode2Confirm").onclick = function () {
      fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "mode2" }) })
        .then(function () { refreshMode(); closeModal(); status("已切换为半路吸尘器"); });
    };
  }

  function openMode3Modal() {
    var base = C.getApiBase();
    if (!base) return;
    openModal("附近接力",
      "<p class=\"text-muted text-sm mb-4\">送完本单后，在目的地附近继续接单。</p>" +
      "<button type=\"button\" id=\"mode3Confirm\" class=\"w-full py-3 rounded-xl bg-accent text-white font-medium\">使用此模式</button>");
    document.getElementById("mode3Confirm").onclick = function () {
      fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "mode3" }) })
        .then(function () { refreshMode(); closeModal(); status("已切换为附近接力"); });
    };
  }

  function openPauseModal() {
    var base = C.getApiBase();
    if (!base) return;
    openModal("停止接单",
      "<p class=\"text-muted text-sm mb-4\">暂停接单，不再推送新订单。</p>" +
      "<button type=\"button\" id=\"pauseConfirm\" class=\"w-full py-3 rounded-xl bg-accent text-white font-medium\">确定</button>");
    document.getElementById("pauseConfirm").onclick = function () {
      fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "pause" }) })
        .then(function () { refreshMode(); closeModal(); status("已停止接单"); });
    };
  }

  function loadPlannedTrip() {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/planned_trip").then(function (r) { return r.json(); }).then(function (d) {
      var plans = d.plans || [];
      var list = document.getElementById("planList");
      if (!list) return;
      list.innerHTML = "";
      plans.forEach(function (p, idx) {
        var completed = p.completed === true;
        var card = document.createElement("div");
        card.className = "p-4 rounded-xl bg-panel border border-border" + (completed ? " opacity-75" : "");
        card.setAttribute("data-index", String(idx));
        var header = "第 " + (idx + 1) + " 批";
        if (idx === 0 && !completed) header += "（优先找单）";
        if (completed) header += " · 已结束找单";
        card.innerHTML =
          "<div class=\"text-muted text-sm font-medium mb-2\">" + header + "</div>" +
          "<label class=\"block text-muted text-xs mb-1\">出发时间</label>" +
          "<input type=\"text\" class=\"plan-time w-full bg-[#0c0c0f] border border-border rounded-lg px-3 py-2 text-console mb-2\" placeholder=\"06:00 或 2025-02-22 06:00\" value=\"" + (p.departure_time || "").replace(/"/g, "&quot;") + "\" " + (completed ? "readonly" : "") + " />" +
          "<label class=\"block text-muted text-xs mb-1\">出发地</label>" +
          "<input type=\"text\" class=\"plan-origin w-full bg-[#0c0c0f] border border-border rounded-lg px-3 py-2 text-console mb-2\" placeholder=\"如东荣生花苑\" value=\"" + (p.origin || "").replace(/"/g, "&quot;") + "\" " + (completed ? "readonly" : "") + " />" +
          "<label class=\"block text-muted text-xs mb-1\">目的地</label>" +
          "<input type=\"text\" class=\"plan-dest w-full bg-[#0c0c0f] border border-border rounded-lg px-3 py-2 text-console mb-3\" placeholder=\"上海\" value=\"" + (p.destination || "").replace(/"/g, "&quot;") + "\" " + (completed ? "readonly" : "") + " />" +
          "<div class=\"flex gap-2\">" +
          (completed ? "" : "<button type=\"button\" class=\"plan-save px-3 py-2 rounded-lg bg-accent text-white text-sm\">保存</button><button type=\"button\" class=\"plan-complete px-3 py-2 rounded-lg border border-muted text-muted text-sm\">结束找单</button>") +
          "</div>";
        if (!completed) {
          card.querySelector(".plan-save").onclick = function () { savePlanAt(idx); };
          card.querySelector(".plan-complete").onclick = function () { completePlanAt(idx); };
        }
        list.appendChild(card);
      });
    });
  }

  function completePlanAt(idx) {
    var base = C.getApiBase();
    if (!base) return;
    if (!confirm("本批找单任务结束？计划保留，下一批将自动接上。")) return;
    fetch(base + "/planned_trip/complete?index=" + idx, { method: "POST" })
      .then(function () { status("已结束找单，下一批接上"); loadPlannedTrip(); });
  }

  function savePlanAt(idx) {
    var base = C.getApiBase();
    if (!base) return;
    var card = document.querySelector("#planList [data-index=\"" + idx + "\"]");
    if (!card) return;
    var body = {
      index: idx,
      origin: (card.querySelector(".plan-origin").value || "").trim() || "如东荣生花苑",
      destination: (card.querySelector(".plan-dest").value || "").trim() || "上海",
      departure_time: (card.querySelector(".plan-time").value || "").trim() || "06:00",
      time_window_minutes: 30,
      min_orders: 2,
      max_orders: 4
    };
    fetch(base + "/planned_trip", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function () { status("第 " + (idx + 1) + " 批计划已保存"); loadPlannedTrip(); });
  }

  function loadConfig() {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/driver_mode_config").then(function (r) { return r.json(); }).then(function (c) {
      var dv = document.getElementById("detourVal");
      var pv = document.getElementById("profitVal");
      if (dv) dv.textContent = c.mode2_detour_max != null ? c.mode2_detour_max : 15;
      if (pv) pv.textContent = c.mode2_high_profit_threshold != null ? c.mode2_high_profit_threshold : 100;
    });
  }

  function saveDetour(v) {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/driver_mode_config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode2_detour_max: v }) });
  }

  function saveProfit(v) {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/driver_mode_config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode2_high_profit_threshold: v }) });
  }

  function runClearWaypointsAndPlan() {
    if (!confirm("确定清空本车本次计划？将取消数据库内本车所有已分配订单，并清空本地乘客起终点与途经点，仅保留司机位置。")) return;
    try {
      var sup = C.getSupabaseClient();
      var driverId = C.getDriverId();
      function done() {
        try {
          C.passengerRows = [];
          C.pickups = [];
          C.deliveries = [];
          C.waypoints = [];
          C.applyPassengerRows();
          C.saveStateToStorage();
          if (typeof C.renderPassengerList === "function") C.renderPassengerList();
          if (typeof C.updateEntryActions === "function") C.updateEntryActions();
        } catch (e) {
          status("清空时出错: " + (e.message || String(e)).slice(0, 60));
          return;
        }
        status("已清空所有乘客起终点与途经点，仅保留司机位置。返回首页可见空列表；若首页已打开请刷新一次。");
      }
      if (sup && driverId) {
        sup.from("order_pool").update({ assigned_driver_id: null, status: "pending_match" }).eq("assigned_driver_id", driverId).eq("status", "assigned")
          .then(function () { return sup.from("driver_state").update({ empty_seats: 4 }).eq("driver_id", driverId); })
          .then(function () { done(); })
          .catch(function (e) {
            done();
            status("本地已清空；数据库操作失败: " + (e.message || "").slice(0, 40));
          });
      } else {
        done();
      }
    } catch (err) {
      status("操作失败: " + (err.message || String(err)).slice(0, 80));
    }
  }

  function run() {
    var driverPlate = document.getElementById("driverPlate");
    if (driverPlate) {
      driverPlate.value = C.driverPlateNumber || "";
      driverPlate.addEventListener("blur", function () {
        var v = (driverPlate.value || "").trim();
        C.driverPlateNumber = v;
        var sup = C.getSupabaseClient();
        var driverId = C.getDriverId();
        if (sup && driverId) {
          sup.from("drivers").update({ plate_number: v }).eq("id", driverId).then(function () { status("车牌已保存"); });
        }
      });
    }

    document.querySelectorAll(".mode-btn").forEach(function (btn) {
      btn.onclick = function () {
        var mode = this.getAttribute("data-mode");
        if (mode === "mode1") openMode1Modal();
        else if (mode === "mode2") openMode2Modal();
        else if (mode === "mode3") openMode3Modal();
        else if (mode === "pause") openPauseModal();
      };
    });

    if (modeModalClose) modeModalClose.onclick = closeModal;
    if (modeModalOverlay) {
      modeModalOverlay.onclick = function (e) {
        if (e.target === modeModalOverlay) closeModal();
      };
    }
    if (modeModal) modeModal.onclick = function (e) { e.stopPropagation(); };

    refreshMode();
  }

  function loadDriverPlateThenRun() {
    var sup = C.getSupabaseClient();
    var driverId = C.getDriverId();
    if (sup && driverId) {
      sup.from("drivers").select("plate_number").eq("id", driverId).maybeSingle()
        .then(function (r) {
          if (r && r.data && (r.data.plate_number || "").trim()) {
            C.driverPlateNumber = (r.data.plate_number || "").trim();
            var pe = document.getElementById("driverPlate");
            if (pe) pe.value = C.driverPlateNumber;
          }
          run();
        })
        .catch(function () { run(); });
    } else {
      run();
    }
  }

  function boot() {
    if (window.SmartDiaoduAuth && typeof window.SmartDiaoduAuth.requireAuth === "function") {
      window.SmartDiaoduAuth.requireAuth(loadDriverPlateThenRun);
    } else {
      C.loadAppConfig(loadDriverPlateThenRun);
    }
  }

  function bindClearButton() {
    var btn = document.getElementById("btnClearWaypointsAndPlan");
    if (!btn || btn._clearBound) return;
    btn._clearBound = true;
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      runClearWaypointsAndPlan();
    });
    btn.addEventListener("touchend", function (e) {
      e.preventDefault();
      runClearWaypointsAndPlan();
    }, { passive: false });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindClearButton();
      boot();
    });
  } else {
    bindClearButton();
    boot();
  }
})();
