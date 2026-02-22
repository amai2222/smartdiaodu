/**
 * 设置页 - 车牌、调度模式、计划、清空途经、绕路/高收益
 * 依赖：index-config.js, index-state.js（共用 C、Supabase、API）
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) {
    window.location.replace("login.html");
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
      var planPanel = document.getElementById("planPanel");
      if (planPanel) planPanel.classList.toggle("hidden", mode !== "mode1");
      if (mode === "mode1") loadPlannedTrip();
    });
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
    if (!confirm("确定清空本车本次计划？将取消数据库内本车所有已分配订单，并清空本地途经点与乘客列表，仅保留司机位置。")) return;
    var sup = C.getSupabaseClient();
    var driverId = C.getDriverId();
    function done() {
      C.passengerRows = [];
      C.pickups = [];
      C.deliveries = [];
      C.waypoints = [];
      C.applyPassengerRows();
      C.saveStateToStorage();
      if (C.renderPassengerList) C.renderPassengerList();
      if (C.updateEntryActions) C.updateEntryActions();
      status("已清空途经与计划，仅保留司机位置。");
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
        var base = C.getApiBase();
        if (!base) return;
        fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: mode }) })
          .then(function () { refreshMode(); });
      };
    });

    var btnAddPlan = document.getElementById("btnAddPlan");
    if (btnAddPlan) {
      btnAddPlan.onclick = function () {
        var base = C.getApiBase();
        if (!base) return;
        var body = { origin: "如东荣生花苑", destination: "上海", departure_time: "06:00", time_window_minutes: 30, min_orders: 2, max_orders: 4 };
        fetch(base + "/planned_trip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
          .then(function () { status("已添加一批，请填写时间与地点后保存"); loadPlannedTrip(); });
      };
    }

    var detourMinus = document.getElementById("detourMinus");
    var detourPlus = document.getElementById("detourPlus");
    var detourVal = document.getElementById("detourVal");
    if (detourMinus) detourMinus.onclick = function () {
      if (!detourVal) return;
      var v = Math.max(0, parseInt(detourVal.textContent, 10) - 5);
      detourVal.textContent = v;
      saveDetour(v);
    };
    if (detourPlus) detourPlus.onclick = function () {
      if (!detourVal) return;
      var v = parseInt(detourVal.textContent, 10) + 5;
      detourVal.textContent = v;
      saveDetour(v);
    };

    var profitMinus = document.getElementById("profitMinus");
    var profitPlus = document.getElementById("profitPlus");
    var profitVal = document.getElementById("profitVal");
    if (profitMinus) profitMinus.onclick = function () {
      if (!profitVal) return;
      var v = Math.max(0, parseInt(profitVal.textContent, 10) - 10);
      profitVal.textContent = v;
      saveProfit(v);
    };
    if (profitPlus) profitPlus.onclick = function () {
      if (!profitVal) return;
      var v = parseInt(profitVal.textContent, 10) + 10;
      profitVal.textContent = v;
      saveProfit(v);
    };

    var btnClear = document.getElementById("btnClearWaypointsAndPlan");
    if (btnClear) {
      btnClear.addEventListener("click", function (e) { e.preventDefault(); runClearWaypointsAndPlan(); });
      btnClear.addEventListener("touchend", function (e) { e.preventDefault(); runClearWaypointsAndPlan(); }, { passive: false });
    }

    refreshMode();
    loadConfig();
  }

  function init() {
    try {
      if (typeof localStorage === "undefined" || !localStorage.getItem(C.STORAGE_TOKEN)) {
        window.location.replace("login.html");
        return;
      }
    } catch (e) {
      window.location.replace("login.html");
      return;
    }
    C.loadAppConfig(function () {
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
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
