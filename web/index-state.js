/**
 * 控制台 - 状态与数据（乘客列表、加载/保存、限行提示）
 * 依赖：index-config.js
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) return;

  C.pickups = [];
  C.deliveries = [];
  C.passengerRows = [];
  C.editingPassengerIdx = -1;
  C.driverPlateNumber = "";

  C.applyPassengerRows = function () {
    C.pickups = C.passengerRows.map(function (r) { return r.pickup; });
    C.deliveries = C.passengerRows.map(function (r) { return r.delivery; });
  };

  C.saveStateToStorage = function () {
    if (typeof localStorage === "undefined") return;
    var loc = document.getElementById("driverLoc");
    if (loc) localStorage.setItem(C.STORAGE_DRIVER_LOC, loc.value.trim());
    localStorage.setItem(C.STORAGE_PICKUPS, JSON.stringify(C.pickups));
    localStorage.setItem(C.STORAGE_DELIVERIES, JSON.stringify(C.deliveries));
  };

  C.getCurrentState = function () {
    var plateEl = document.getElementById("driverPlate");
    var plate = (plateEl && plateEl.value.trim()) || C.driverPlateNumber || "";
    var locEl = document.getElementById("driverLoc");
    var driver_loc = (locEl && locEl.value.trim()) || "";
    var out = {
      driver_loc: driver_loc,
      pickups: C.pickups.slice(),
      deliveries: C.deliveries.slice()
    };
    if (plate) out.plate_number = plate;
    return out;
  };

  C.isInRestrictionArea = function (addr) {
    if (!addr || typeof addr !== "string") return false;
    var a = String(addr).trim();
    return a.indexOf("上海") !== -1 || a.indexOf("北京市") !== -1 || a.indexOf("北京 ") !== -1;
  };

  C.updateRestrictionHint = function () {
    var el = document.getElementById("restrictionHintIndex");
    if (!el) return;
    var addr = (document.getElementById("driverLoc") && document.getElementById("driverLoc").value) || "";
    if (C.isInRestrictionArea(addr)) {
      el.textContent = "当前位于限行区域，请留意当地限行规定与时段。";
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  };

  C.showDbErrorBanner = function (errMsg) {
    if (document.getElementById("dbErrorBanner")) return;
    var banner = document.createElement("div");
    banner.id = "dbErrorBanner";
    banner.className = "mx-4 mt-2 p-4 rounded-xl bg-red-900/50 border border-red-500/60 text-red-100 text-sm";
    var origin = window.location.origin || "";
    banner.innerHTML =
      "<strong>数据库请求失败，乘客/空座未加载</strong><br>" +
      "可能原因：CORS 未放行、网络被拦截、或 Anon Key 错误。<br>" +
      "请到 <b>Supabase Dashboard → Project Settings → API</b>，在 CORS 允许列表中添加：<br><code class=\"bg-black/30 px-1 rounded\">" + (origin || "你的网站完整地址") + "</code><br>" +
      "保存后 <button type=\"button\" id=\"dbErrorRetry\" class=\"mt-2 px-3 py-1 rounded bg-red-700 text-white\">重试加载</button>";
    var header = document.querySelector("header");
    if (header) header.insertAdjacentElement("afterend", banner);
    var retryBtn = document.getElementById("dbErrorRetry");
    if (retryBtn) retryBtn.onclick = function () { banner.remove(); var s = document.getElementById("gpsStatus"); if (s) s.textContent = "加载中…"; C.loadFromDb(function () {}); };
  };

  C.updateEntryActions = function () {
    var seatsEl = document.getElementById("emptySeats");
    var emptySeats = seatsEl ? Math.max(0, parseInt(seatsEl.value, 10) || 0) : 0;
    var btnMap = document.getElementById("btnShowMap");
    var btnMatch = document.getElementById("btnContinueMatch");
    var hint = document.getElementById("entryHint");
    if (!btnMap || !btnMatch) return;
    if (emptySeats === 0) {
      btnMap.classList.remove("hidden");
      btnMatch.classList.add("hidden");
      if (hint) hint.textContent = "车已满，打开地图按路线接送；到达每站后在地图页点「已到达」推进。";
    } else {
      btnMap.classList.remove("hidden");
      btnMatch.classList.remove("hidden");
      if (hint) hint.textContent = "有空位，点「继续接单」让后端匹配顺路单；也可打开地图查看当前路线。";
    }
  };

  C.dropOffAndUpdateDb = function (orderId, newLoc, idx) {
    var sup = C.getSupabaseClient();
    if (!sup) return;
    var driverId = C.getDriverId();
    sup.from("driver_state").select("empty_seats").eq("driver_id", driverId).maybeSingle()
      .then(function (r) {
        var nextSeats = (r.data && r.data.empty_seats != null) ? Math.min(4, r.data.empty_seats + 1) : 1;
        return Promise.all([
          sup.from("driver_state").update({ current_loc: newLoc, empty_seats: nextSeats }).eq("driver_id", driverId),
          sup.from("order_pool").update({ status: "completed", assigned_driver_id: null }).eq("id", orderId)
        ]);
      })
      .then(function () {
        C.passengerRows.splice(idx, 1);
        C.applyPassengerRows();
        if (newLoc) {
          var locEl = document.getElementById("driverLoc");
          if (locEl) locEl.value = newLoc;
        }
        var seatsEl = document.getElementById("emptySeats");
        if (seatsEl) seatsEl.value = String(Math.min(4, parseInt(seatsEl.value, 10) + 1));
        if (C.renderPassengerList) C.renderPassengerList();
        C.saveStateToStorage();
      })
      .catch(function (e) {
        var s = document.getElementById("gpsStatus");
        if (s) s.textContent = "下车更新失败: " + (e.message || e);
      });
  };

  C.loadFromDb = function (cb) {
    var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
    var sup = C.getSupabaseClient();
    if (!sup) {
      var why = [];
      if (!url) why.push("缺少 Supabase URL");
      if (!anon) why.push("缺少 Anon Key");
      if (!window.supabase) why.push("Supabase 脚本未加载");
      console.warn("[loadFromDb] 未连上数据库:", why.join("；"), "| 请确保 config.js 已部署且可访问，或登录后 localStorage 已写入。");
      try {
        var p = localStorage.getItem(C.STORAGE_PICKUPS), d = localStorage.getItem(C.STORAGE_DELIVERIES);
        if (p) C.pickups = JSON.parse(p);
        if (d) C.deliveries = JSON.parse(d);
        C.passengerRows = C.pickups.map(function (pu, i) { return { id: null, pickup: pu, delivery: C.deliveries[i] || "" }; });
        C.applyPassengerRows();
      } catch (e) {}
      var statusEl = document.getElementById("gpsStatus");
      if (statusEl) statusEl.innerHTML = "未连接数据库（" + (why.length ? why.join("、") : "未知") + "）。请部署 config.js 或检查登录后 <button type=\"button\" id=\"btnReloadDb\" class=\"underline text-accent\">重新加载</button>";
      var rel = document.getElementById("btnReloadDb");
      if (rel) rel.onclick = function () {
        if (statusEl) statusEl.textContent = "加载中…";
        C.loadSupabaseScriptThenRetry(function () {
          C.loadFromDb(function () {
            if (statusEl) statusEl.textContent = C.getSupabaseClient() ? "" : "仍无法连接，请检查 config.js 与 Supabase 密钥。";
          });
        });
      };
      C.updateEntryActions();
      if (cb) cb();
      return;
    }
    var driverId = C.getDriverId();
    sup.from("driver_state").select("current_loc, empty_seats").eq("driver_id", driverId).maybeSingle()
      .then(function (r) {
        var locEl = document.getElementById("driverLoc");
        var seatsEl = document.getElementById("emptySeats");
        if (r.data && locEl) locEl.value = r.data.current_loc || "";
        if (r.data && seatsEl) seatsEl.value = String(Math.max(0, Math.min(4, r.data.empty_seats || 0)));
        return sup.from("order_pool").select("id, pickup, delivery").eq("assigned_driver_id", driverId).eq("status", "assigned");
      })
      .then(function (r) {
        if (r.data && Array.isArray(r.data)) {
          C.passengerRows = r.data.map(function (o) { return { id: o.id, pickup: o.pickup || "", delivery: o.delivery || "" }; });
        } else {
          C.passengerRows = [];
        }
        C.applyPassengerRows();
        if (C.renderPassengerList) C.renderPassengerList();
        C.saveStateToStorage();
        var emptySeats = Math.max(0, Math.min(4, 4 - C.passengerRows.length));
        var seatsEl = document.getElementById("emptySeats");
        if (seatsEl) seatsEl.value = String(emptySeats);
        var sup2 = C.getSupabaseClient();
        if (sup2) sup2.from("driver_state").update({ empty_seats: emptySeats }).eq("driver_id", C.getDriverId()).then(function () {});
        return sup.from("drivers").select("name, plate_number").eq("id", driverId).maybeSingle()
          .then(function (rr) {
            if (rr && rr.data) {
              var un = document.getElementById("userName");
              if (un) un.textContent = (rr.data.name || "").trim() || "—";
              C.driverPlateNumber = (rr.data.plate_number || "").trim();
              var pe = document.getElementById("driverPlate");
              if (pe) pe.value = C.driverPlateNumber;
            }
            C.updateRestrictionHint();
            C.updateEntryActions();
            if (cb) cb();
          })
          .catch(function () {
            C.updateRestrictionHint();
            C.updateEntryActions();
            if (cb) cb();
          });
      })
      .catch(function (e) {
        var msg = (e && e.message) ? e.message : String(e);
        console.error("[loadFromDb] 拉取乘客/司机状态失败:", msg, e);
        C.passengerRows = [];
        C.applyPassengerRows();
        if (C.renderPassengerList) C.renderPassengerList();
        C.updateEntryActions();
        var statusEl = document.getElementById("gpsStatus");
        if (statusEl) statusEl.textContent = "加载失败: " + msg.slice(0, 80);
        C.showDbErrorBanner(msg);
        if (cb) cb();
      });
  };
})();
