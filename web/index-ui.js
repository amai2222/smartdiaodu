/**
 * 控制台 - UI 与事件（乘客列表、弹窗、模式、计划、推送、GPS、入口）
 * 依赖：index-config.js, index-state.js
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) { window.__smartdiaodu_nav_fallback = true; return; }

  C.renderPassengerList = function () {
    var list = document.getElementById("passengerList");
    var hint = document.getElementById("noPassengersHint");
    if (!list) return;
    list.innerHTML = "";
    var waypoints = C.waypoints || [];
    var len = C.passengerRows.length > 0 ? C.passengerRows.length : C.pickups.length;
    if (len === 0 && waypoints.length === 0) {
      if (hint) hint.classList.remove("hidden");
      return;
    }
    if (hint) hint.classList.add("hidden");
    for (var idx = 0; idx < len; idx++) {
      (function (i) {
        var row = C.passengerRows[i];
        var p = row ? row.pickup : (C.pickups[i] || "");
        var d = row ? row.delivery : (C.deliveries[i] || "");
        var orderId = row && row.id ? row.id : "";
        var shortP = p.length > 12 ? p.slice(0, 12) + "…" : p;
        var shortD = d.length > 12 ? d.slice(0, 12) + "…" : d;
        var li = document.createElement("li");
        li.className = "flex items-center justify-between gap-3 p-3 rounded-xl bg-[#0c0c0f] border border-border";
        var isOnboard = !!(row && row.onboard);
        li.innerHTML = "<span class=\"text-console flex-1 min-w-0\"><strong>" + (i + 1) + "号客</strong>" + (isOnboard ? " <span class=\"text-muted text-sm\">(已上车)</span> " : " ") + shortP + " → " + shortD + "</span>" +
          (isOnboard ? "" : "<button type=\"button\" class=\"onboard-passenger shrink-0 px-3 py-2 rounded-lg border border-accent/60 text-accent font-medium\" data-idx=\"" + i + "\">上车</button>") +
          "<button type=\"button\" class=\"edit-passenger shrink-0 px-3 py-2 rounded-lg border border-border text-muted hover:text-gray-100 font-medium\" data-idx=\"" + i + "\">编辑</button>" +
          "<button type=\"button\" class=\"drop-passenger shrink-0 px-3 py-2 rounded-lg bg-danger/20 text-danger font-medium\" data-idx=\"" + i + "\" data-order-id=\"" + (orderId || "") + "\" data-delivery=\"" + (d || "").replace(/"/g, "&quot;") + "\">✖️ 下车</button>";
        if (!isOnboard) {
          li.querySelector(".onboard-passenger").onclick = function () {
            var ix = parseInt(this.getAttribute("data-idx"), 10);
            var r = C.passengerRows[ix];
            if (!r) return;
            r.onboard = true;
            C.applyPassengerRows();
            C.renderPassengerList();
            C.saveStateToStorage();
          };
        }
        li.querySelector(".edit-passenger").onclick = function () {
          var ix = parseInt(this.getAttribute("data-idx"), 10);
          var r = C.passengerRows[ix];
          if (!r) return;
          C.editingPassengerIdx = ix;
          document.getElementById("editPickup").value = r.pickup || "";
          document.getElementById("editDelivery").value = r.delivery || "";
          document.getElementById("editPassengerModalOverlay").classList.add("show");
        };
        li.querySelector(".drop-passenger").onclick = function () {
          var ix = parseInt(this.getAttribute("data-idx"), 10);
          var oid = this.getAttribute("data-order-id");
          var dest = this.getAttribute("data-delivery") || (C.deliveries[ix] || "");
          if (oid && C.getSupabaseClient()) {
            C.dropOffAndUpdateDb(oid, dest, ix);
          } else {
            C.passengerRows.splice(ix, 1);
            if (C.passengerRows.length === 0) { C.pickups = []; C.deliveries = []; } else { C.applyPassengerRows(); }
            if (dest) { var locEl = document.getElementById("driverLoc"); if (locEl) locEl.value = dest; }
            C.renderPassengerList();
            C.saveStateToStorage();
          }
        };
        list.appendChild(li);
      })(idx);
    }
    for (var w = 0; w < waypoints.length; w++) {
      (function (wi) {
        var addr = waypoints[wi] || "";
        var shortAddr = addr.length > 14 ? addr.slice(0, 14) + "…" : addr;
        var li = document.createElement("li");
        li.className = "flex items-center justify-between gap-3 p-3 rounded-xl bg-[#0c0c0f] border border-border";
        li.innerHTML = "<span class=\"text-console flex-1 min-w-0\"><strong>途径点</strong> " + shortAddr + "</span>" +
          "<button type=\"button\" class=\"arrive-waypoint shrink-0 px-3 py-2 rounded-lg border border-accent/60 text-accent font-medium\" data-widx=\"" + wi + "\">到达</button>";
        li.querySelector(".arrive-waypoint").onclick = function () {
          var ix = parseInt(this.getAttribute("data-widx"), 10);
          if (C.waypoints && ix >= 0 && ix < C.waypoints.length) {
            C.waypoints.splice(ix, 1);
            C.saveStateToStorage();
            C.renderPassengerList();
          }
        };
        list.appendChild(li);
      })(w);
    }
  };

  document.getElementById("btnRefreshGps").onclick = function () {
    var status = document.getElementById("gpsStatus");
    var input = document.getElementById("driverLoc");
    status.textContent = "定位中…";
    if (!navigator.geolocation) {
      status.textContent = "浏览器不支持定位";
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = pos.coords.latitude, lng = pos.coords.longitude;
        var base = C.getApiBase();
        if (!base) {
          input.value = lat.toFixed(5) + ", " + lng.toFixed(5);
          status.textContent = "已填入经纬度（未配置 API 无法反查地址）";
          return;
        }
        fetch(base + "/reverse_geocode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat: lat, lng: lng })
        }).then(function (r) { return r.json(); }).then(function (d) {
          input.value = d.address || (lat.toFixed(5) + ", " + lng.toFixed(5));
          status.textContent = "已更新位置";
          C.saveStateToStorage();
          var sup = C.getSupabaseClient();
          if (sup) sup.from("driver_state").update({ current_loc: input.value.trim() }).eq("driver_id", C.getDriverId()).then(function () {});
        }).catch(function (e) {
          input.value = lat.toFixed(5) + ", " + lng.toFixed(5);
          status.textContent = "反查地址失败，已填经纬度";
        });
      },
      function () { status.textContent = "定位失败，请允许位置权限"; }
    );
  };

  function openPlanModal() {
    var list = C.passengerRows.length ? C.passengerRows : (function () {
      var p = [], d = [];
      try {
        var sp = localStorage.getItem(C.STORAGE_PICKUPS), sd = localStorage.getItem(C.STORAGE_DELIVERIES);
        if (sp) p = JSON.parse(sp);
        if (sd) d = JSON.parse(sd);
      } catch (e) {}
      return p.map(function (pu, i) { return { pickup: pu, delivery: d[i] || "" }; });
    })();
    var content = document.getElementById("planModalContent");
    if (!content) return;
    var waypoints = C.waypoints || [];
    if (list.length === 0 && waypoints.length === 0) {
      content.innerHTML = "<p class=\"text-muted text-console\">暂无乘客与途经点，当前无计划站点。</p>";
    } else {
      var html = list.map(function (row, i) {
        var pickup = (row.pickup || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        var delivery = (row.delivery || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return "<div class=\"plan-item\"><div class=\"label\">乘客 " + (i + 1) + " · 起点</div><div class=\"addr\">" + pickup + "</div><div class=\"label mt-2\">终点</div><div class=\"addr\">" + delivery + "</div></div>";
      }).join("");
      if (waypoints.length > 0) {
        html += waypoints.map(function (addr, i) {
          var a = (addr || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          return "<div class=\"plan-item\"><div class=\"label\">途径点 " + (i + 1) + "</div><div class=\"addr\">" + a + "</div></div>";
        }).join("");
      }
      content.innerHTML = html;
    }
    document.getElementById("planModalOverlay").classList.add("show");
  }
  function closePlanModal() {
    document.getElementById("planModalOverlay").classList.remove("show");
  }
  var btnShowPlan = document.getElementById("btnShowPlan");
  if (btnShowPlan) btnShowPlan.addEventListener("click", function (e) { e.stopPropagation(); openPlanModal(); });
  var planModalClose = document.getElementById("planModalClose");
  if (planModalClose) planModalClose.addEventListener("click", closePlanModal);
  document.getElementById("planModalOverlay").addEventListener("click", function (e) {
    if (e.target === document.getElementById("planModalOverlay")) closePlanModal();
  });

  function openWaypointsModal() {
    var content = document.getElementById("waypointsModalContent");
    var waypoints = C.waypoints || [];
    if (!content) return;
    if (waypoints.length === 0) {
      content.innerHTML = "<p class=\"text-muted text-console\">暂无途经点，可在下方输入地址添加。</p>";
    } else {
      content.innerHTML = waypoints.map(function (addr, i) {
        var a = (addr || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return "<div class=\"waypoint-item\">途径点：" + a + "</div>";
      }).join("");
    }
    var input = document.getElementById("waypointAddrInput");
    if (input) input.value = "";
    document.getElementById("waypointsModalOverlay").classList.add("show");
    if (input) setTimeout(function () { input.focus(); }, 100);
  }
  function closeWaypointsModal() {
    document.getElementById("waypointsModalOverlay").classList.remove("show");
  }
  var btnWaypoints = document.getElementById("btnWaypoints");
  if (btnWaypoints) btnWaypoints.addEventListener("click", openWaypointsModal);
  document.getElementById("waypointsModalClose").addEventListener("click", closeWaypointsModal);
  document.getElementById("waypointsModalOverlay").addEventListener("click", function (e) {
    if (e.target === document.getElementById("waypointsModalOverlay")) closeWaypointsModal();
  });
  var waypointAddBtn = document.getElementById("waypointAddBtn");
  var waypointAddrInput = document.getElementById("waypointAddrInput");
  if (waypointAddBtn && waypointAddrInput) {
    waypointAddBtn.addEventListener("click", function () {
      var addr = (waypointAddrInput.value || "").trim();
      if (!addr) return;
      C.waypoints = C.waypoints || [];
      C.waypoints.push(addr);
      C.saveStateToStorage();
      openWaypointsModal();
      if (C.renderPassengerList) C.renderPassengerList();
    });
    waypointAddrInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") waypointAddBtn.click();
    });
  }

  (function setupSettingsPanel() {
    var overlay = document.getElementById("settingsPanelOverlay");
    var btn = document.getElementById("btnSettings") || document.getElementById("navSettings");
    var closeBtn = document.getElementById("settingsPanelClose");
    if (!overlay) return;
    function openSettings() { overlay.classList.add("show"); overlay.setAttribute("aria-hidden", "false"); }
    function closeSettings() { overlay.classList.remove("show"); overlay.setAttribute("aria-hidden", "true"); }
    if (btn) btn.addEventListener("click", openSettings);
    if (closeBtn) closeBtn.addEventListener("click", closeSettings);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeSettings();
    });
  })();

  (function setupBottomNav() {
    var viewHome = document.getElementById("viewHome");
    var viewMap = document.getElementById("viewMap");
    var mapFrame = document.getElementById("mapFrame");
    var navHome = document.getElementById("navHome");
    var navMap = document.getElementById("navMap");
    var navSettings = document.getElementById("navSettings");
    if (!viewHome || !viewMap || !navHome || !navMap) return;

    function setActiveTab(tab) {
      [navHome, navMap, navSettings].forEach(function (el) {
        if (el) el.classList.toggle("active", el === tab);
      });
    }

    var bottomNav = document.getElementById("bottomNav");
    var appMain = document.getElementById("appMain");

    function showHome() {
      viewHome.classList.remove("hidden");
      viewMap.classList.add("hidden");
      if (bottomNav) bottomNav.classList.remove("bottom-nav-hidden");
      if (appMain) appMain.classList.remove("map-fullscreen");
      setActiveTab(navHome);
    }

    var mapLoaded = false;
    function showMap() {
      if (mapFrame && !mapLoaded) { mapFrame.src = "map.html"; mapLoaded = true; }
      viewHome.classList.add("hidden");
      viewMap.classList.remove("hidden");
      if (bottomNav) bottomNav.classList.add("bottom-nav-hidden");
      if (appMain) appMain.classList.add("map-fullscreen");
      setActiveTab(navMap);
    }

    function addTap(el, fn) {
      if (!el) return;
      el.addEventListener("click", fn);
      el.addEventListener("touchend", function (e) {
        e.preventDefault();
        fn();
      }, { passive: false });
    }
    addTap(navHome, showHome);
    addTap(navMap, showMap);

    var btnShowMap = document.getElementById("btnShowMap");
    if (btnShowMap) addTap(btnShowMap, showMap);

    if (navSettings) {
      var overlay = document.getElementById("settingsPanelOverlay");
      function openSettings() { if (overlay) overlay.classList.add("show"); }
      addTap(navSettings, openSettings);
    }

    window.addEventListener("message", function (e) {
      if (e.data && e.data.type === "smartdiaodu_map_back") showHome();
    });

    setActiveTab(navHome);
  })();

  function closeEditPassengerModal() {
    C.editingPassengerIdx = -1;
    document.getElementById("editPassengerModalOverlay").classList.remove("show");
  }
  document.getElementById("editPassengerModalCancel").addEventListener("click", closeEditPassengerModal);
  document.getElementById("editPassengerModalOverlay").addEventListener("click", function (e) {
    if (e.target === document.getElementById("editPassengerModalOverlay")) closeEditPassengerModal();
  });
  document.getElementById("editPassengerModalSave").addEventListener("click", function () {
    var idx = C.editingPassengerIdx;
    if (idx < 0 || idx >= C.passengerRows.length) { closeEditPassengerModal(); return; }
    var newPickup = (document.getElementById("editPickup").value || "").trim();
    var newDelivery = (document.getElementById("editDelivery").value || "").trim();
    var row = C.passengerRows[idx];
    row.pickup = newPickup;
    row.delivery = newDelivery;
    C.applyPassengerRows();
    C.saveStateToStorage();
    var sup = C.getSupabaseClient();
    if (sup && row.id) {
      sup.from("order_pool").update({ pickup: newPickup, delivery: newDelivery }).eq("id", row.id).then(function () {
        var s = document.getElementById("gpsStatus");
        if (s) s.textContent = "已写库，起终点已更新";
        C.renderPassengerList();
      }).catch(function (e) {
        var s = document.getElementById("gpsStatus");
        if (s) s.textContent = "写库失败: " + (e.message || String(e)).slice(0, 60);
        C.renderPassengerList();
      });
    } else {
      C.renderPassengerList();
    }
    closeEditPassengerModal();
  });

  /** 语音输入：为输入框绑定麦克风按钮，使用浏览器语音识别（中文），开车时免打字。
   * iOS Safari：必须在用户手势内延迟 start()，且每次新建实例，否则点击无反应。 */
  (function setupVoiceInput() {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    var voiceBtnIds = ["driverLocVoiceBtn", "waypointVoiceBtn", "editPickupVoiceBtn", "editDeliveryVoiceBtn", "editVoiceStartEndBtn"];
    if (!SpeechRecognition) {
      voiceBtnIds.forEach(function (id) { var b = document.getElementById(id); if (b) b.style.display = "none"; });
      return;
    }
    var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

    /** 从「乘客x起点：xxx，终点：xxx」或「起点：xxx，终点：xxx」中解析出起点、终点 */
    function parseStartEnd(text) {
      var s = (text || "").trim();
      var pickup = "", delivery = "";
      var iEnd = s.indexOf("终点");
      if (iEnd !== -1) {
        delivery = s.slice(iEnd + 2).replace(/^[：:\s，,]+/, "").trim();
        var beforeEnd = s.slice(0, iEnd).trim();
        var iStart = beforeEnd.indexOf("起点");
        if (iStart !== -1) {
          pickup = beforeEnd.slice(iStart + 2).replace(/^[：:\s]+/, "").replace(/[，,]\s*$/, "").trim();
        } else {
          pickup = beforeEnd.replace(/^乘客\d*[：:\s]*/, "").trim();
        }
      } else {
        var iStart = s.indexOf("起点");
        if (iStart !== -1) {
          pickup = s.slice(iStart + 2).replace(/^[：:\s]+/, "").trim();
        } else {
          pickup = s.replace(/^乘客\d*[：:\s]*/, "").trim();
        }
      }
      return { pickup: pickup, delivery: delivery };
    }

    function runStart(recognition, btnEl, state) {
      try {
        recognition.start();
        btnEl.classList.add("listening");
        btnEl.textContent = state.listeningText || "…";
        btnEl.setAttribute("title", state.listeningTitle || "正在听… 再说一次可停止");
      } catch (err) {
        btnEl.setAttribute("title", "请允许麦克风权限或重试");
      }
    }

    function bindVoice(inputEl, btnEl) {
      if (!inputEl || !btnEl) return;
      var originalTitle = btnEl.getAttribute("title") || "语音输入";
      var currentRecognition = null;
      var voiceJustStarted = false;
      function onTap() {
        if (btnEl.classList.contains("listening")) {
          if (voiceJustStarted) return;
          try { if (currentRecognition) currentRecognition.abort(); } catch (e) {}
          currentRecognition = null;
          btnEl.classList.remove("listening");
          btnEl.textContent = "🎤";
          btnEl.setAttribute("title", originalTitle);
          return;
        }
        var rec = isIOS ? new SpeechRecognition() : (currentRecognition || new SpeechRecognition());
        if (!isIOS) currentRecognition = rec;
        rec.lang = "zh-CN";
        rec.continuous = false;
        rec.interimResults = false;
        rec.onresult = function (e) {
          var text = (e.results[0] && e.results[0][0]) ? e.results[0][0].transcript : "";
          if (text && inputEl) inputEl.value = text;
        };
        rec.onend = rec.onerror = function () {
          voiceJustStarted = false;
          btnEl.classList.remove("listening");
          btnEl.textContent = "🎤";
          btnEl.setAttribute("title", originalTitle);
        };
        if (isIOS) {
          voiceJustStarted = true;
          setTimeout(function () { runStart(rec, btnEl, { listeningText: "…", listeningTitle: "正在听… 再说一次可停止" }); }, 0);
        } else {
          runStart(rec, btnEl, { listeningText: "…", listeningTitle: "正在听… 再说一次可停止" });
        }
      }
      btnEl.addEventListener("click", onTap);
      if (isIOS) btnEl.addEventListener("touchend", function (e) { e.preventDefault(); onTap(); }, { passive: false });
    }

    function bindVoiceStartEnd(pickupEl, deliveryEl, btnEl) {
      if (!pickupEl || !deliveryEl || !btnEl) return;
      var originalTitle = btnEl.getAttribute("title") || "";
      var originalText = btnEl.textContent || "";
      var currentRecognition = null;
      var voiceJustStarted = false;
      function onTap() {
        if (btnEl.classList.contains("listening")) {
          if (voiceJustStarted) return;
          try { if (currentRecognition) currentRecognition.abort(); } catch (e) {}
          currentRecognition = null;
          btnEl.classList.remove("listening");
          btnEl.textContent = originalText;
          btnEl.setAttribute("title", originalTitle);
          return;
        }
        var rec = isIOS ? new SpeechRecognition() : (currentRecognition || new SpeechRecognition());
        if (!isIOS) currentRecognition = rec;
        rec.lang = "zh-CN";
        rec.continuous = false;
        rec.interimResults = false;
        rec.onresult = function (e) {
          var text = (e.results[0] && e.results[0][0]) ? e.results[0][0].transcript : "";
          if (text) {
            var parsed = parseStartEnd(text);
            if (parsed.pickup) pickupEl.value = parsed.pickup;
            if (parsed.delivery) deliveryEl.value = parsed.delivery;
          }
        };
        rec.onend = rec.onerror = function () {
          voiceJustStarted = false;
          btnEl.classList.remove("listening");
          btnEl.textContent = originalText;
          btnEl.setAttribute("title", originalTitle);
        };
        if (isIOS) {
          voiceJustStarted = true;
          setTimeout(function () { runStart(rec, btnEl, { listeningText: "… 正在听", listeningTitle: "说：乘客x起点：xxx，终点：xxx" }); }, 0);
        } else {
          runStart(rec, btnEl, { listeningText: "… 正在听", listeningTitle: "说：乘客x起点：xxx，终点：xxx" });
        }
      }
      btnEl.addEventListener("click", onTap);
      if (isIOS) btnEl.addEventListener("touchend", function (e) { e.preventDefault(); onTap(); }, { passive: false });
    }

    bindVoice(document.getElementById("driverLoc"), document.getElementById("driverLocVoiceBtn"));
    bindVoice(document.getElementById("waypointAddrInput"), document.getElementById("waypointVoiceBtn"));
    bindVoice(document.getElementById("editPickup"), document.getElementById("editPickupVoiceBtn"));
    bindVoice(document.getElementById("editDelivery"), document.getElementById("editDeliveryVoiceBtn"));
    bindVoiceStartEnd(
      document.getElementById("editPickup"),
      document.getElementById("editDelivery"),
      document.getElementById("editVoiceStartEndBtn")
    );
  })();

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
      .then(function () { document.getElementById("gpsStatus").textContent = "已结束找单，下一批接上"; loadPlannedTrip(); });
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
      .then(function () { document.getElementById("gpsStatus").textContent = "第 " + (idx + 1) + " 批计划已保存"; loadPlannedTrip(); });
  }
  document.getElementById("btnAddPlan").onclick = function () {
    var base = C.getApiBase();
    if (!base) return;
    var body = { origin: "如东荣生花苑", destination: "上海", departure_time: "06:00", time_window_minutes: 30, min_orders: 2, max_orders: 4 };
    fetch(base + "/planned_trip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function () { document.getElementById("gpsStatus").textContent = "已添加一批，请填写时间与地点后保存"; loadPlannedTrip(); });
  };
  document.querySelectorAll(".mode-btn").forEach(function (btn) {
    btn.onclick = function () {
      var mode = this.getAttribute("data-mode");
      var base = C.getApiBase();
      if (!base) return;
      fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: mode }) })
        .then(function () { refreshMode(); });
    };
  });

  function loadConfig() {
    var base = C.getApiBase();
    if (!base) return;
    fetch(base + "/driver_mode_config").then(function (r) { return r.json(); }).then(function (c) {
      document.getElementById("detourVal").textContent = c.mode2_detour_max != null ? c.mode2_detour_max : 15;
      document.getElementById("profitVal").textContent = c.mode2_high_profit_threshold != null ? c.mode2_high_profit_threshold : 100;
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
  document.getElementById("detourMinus").onclick = function () {
    var el = document.getElementById("detourVal");
    var v = Math.max(0, parseInt(el.textContent, 10) - 5);
    el.textContent = v;
    saveDetour(v);
  };
  document.getElementById("detourPlus").onclick = function () {
    var el = document.getElementById("detourVal");
    var v = parseInt(el.textContent, 10) + 5;
    el.textContent = v;
    saveDetour(v);
  };
  document.getElementById("profitMinus").onclick = function () {
    var el = document.getElementById("profitVal");
    var v = Math.max(0, parseInt(el.textContent, 10) - 10);
    el.textContent = v;
    saveProfit(v);
  };
  document.getElementById("profitPlus").onclick = function () {
    var el = document.getElementById("profitVal");
    var v = parseInt(el.textContent, 10) + 10;
    el.textContent = v;
    saveProfit(v);
  };

  function addPushEvent(row) {
    var list = document.getElementById("pushEventsList");
    if (!list) return;
    var li = document.createElement("li");
    li.className = "p-4 rounded-xl bg-[#0c0c0f] border border-border";
    li.setAttribute("data-fingerprint", row.fingerprint || "");
    var extra = row.extra_mins != null ? row.extra_mins : "—";
    li.innerHTML = "<div class=\"flex justify-between items-start gap-2 mb-2\">" +
      "<span class=\"text-big font-semibold text-success\">￥" + (row.price || "0") + "</span>" +
      "<span class=\"text-console text-muted\">仅绕 " + extra + " 分钟</span></div>" +
      "<p class=\"text-console text-muted mb-1\">接：" + (row.pickup || "").slice(0, 28) + (row.pickup && row.pickup.length > 28 ? "…" : "") + "</p>" +
      "<p class=\"text-console text-muted mb-3\">送：" + (row.delivery || "").slice(0, 28) + (row.delivery && row.delivery.length > 28 ? "…" : "") + "</p>" +
      "<button type=\"button\" class=\"add-to-cabin w-full py-3 rounded-xl bg-accent hover:bg-blue-600 text-white font-medium\">➕ 添加至我的车厢</button>";
    li.querySelector(".add-to-cabin").onclick = function () {
      var sup = C.getSupabaseClient();
      if (sup) {
        var driverId = C.getDriverId();
        sup.from("order_pool").select("id").eq("pickup", row.pickup || "").eq("delivery", row.delivery || "").eq("status", "pending_match").limit(1)
          .then(function (res) {
            if (res.data && res.data[0]) {
              return sup.from("order_pool").update({ status: "assigned", assigned_driver_id: driverId }).eq("id", res.data[0].id)
                .then(function () { return sup.from("driver_state").select("empty_seats").eq("driver_id", driverId).maybeSingle(); })
                .then(function (r) {
                  var next = (r.data && r.data.empty_seats != null) ? Math.max(0, r.data.empty_seats - 1) : 3;
                  return sup.from("driver_state").update({ empty_seats: next }).eq("driver_id", driverId);
                })
                .then(function () { C.loadFromDb(); });
            }
            C.passengerRows.push({ id: null, pickup: row.pickup || "", delivery: row.delivery || "", onboard: false });
            C.applyPassengerRows();
            C.renderPassengerList();
            C.saveStateToStorage();
          });
      } else {
        C.pickups.push(row.pickup || "");
        C.deliveries.push(row.delivery || "");
        C.passengerRows.push({ id: null, pickup: row.pickup || "", delivery: row.delivery || "", onboard: false });
        C.renderPassengerList();
        C.saveStateToStorage();
      }
    };
    list.insertBefore(li, list.firstChild);
    while (list.children.length > 20) list.removeChild(list.lastChild);
    var status = document.getElementById("pushEventsStatus");
    if (status) status.textContent = "新推送会出现在上方；抢到后点「添加至我的车厢」。";
  }
  window.addEventListener("smartdiaodu_push", function (e) { if (e.detail) addPushEvent(e.detail); });

  if (typeof localStorage !== "undefined" && localStorage.getItem(C.STORAGE_USERNAME)) {
    var un = document.getElementById("userName");
    if (un) un.textContent = "（" + localStorage.getItem(C.STORAGE_USERNAME) + "）";
  }
  document.getElementById("btnLogout").onclick = function () {
    var sup = C.getSupabaseClient();
    if (sup) { try { sup.auth.signOut(); } catch (e) {} }
    if (typeof localStorage !== "undefined") { localStorage.removeItem(C.STORAGE_TOKEN); localStorage.removeItem(C.STORAGE_USERNAME); }
    window.location.replace("login.html");
  };

  document.getElementById("btnContinueMatch").onclick = function () {
    var base = C.getApiBase();
    if (base) {
      fetch(base + "/driver_mode").then(function (r) { return r.json(); }).then(function (d) {
        var mode = d.mode || "mode2";
        if (mode === "pause") {
          fetch(base + "/driver_mode", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "mode2" }) }).then(refreshMode);
        }
      });
    }
    document.getElementById("pushEventsList").scrollIntoView({ behavior: "smooth" });
    document.getElementById("gpsStatus").textContent = "后端正在匹配顺路单，新单会出现在下方「顺路单」区域。";
  };

  function run() {
    var locEl = document.getElementById("driverLoc");
    if (locEl) {
      locEl.addEventListener("change", function () { C.saveStateToStorage(); C.updateRestrictionHint(); });
      locEl.addEventListener("input", function () { C.saveStateToStorage(); C.updateRestrictionHint(); });
      locEl.addEventListener("blur", function () {
        C.saveStateToStorage();
        C.updateRestrictionHint();
        var sup = C.getSupabaseClient();
        if (sup && locEl.value.trim()) sup.from("driver_state").update({ current_loc: locEl.value.trim() }).eq("driver_id", C.getDriverId()).then(function () {});
      });
    }
    var plateEl = document.getElementById("driverPlate");
    if (plateEl) plateEl.addEventListener("blur", function () {
      var val = (plateEl.value || "").trim();
      C.driverPlateNumber = val;
      var sup = C.getSupabaseClient();
      if (sup) sup.from("drivers").update({ plate_number: val || null }).eq("id", C.getDriverId()).then(function () {});
    });
    var seatsEl = document.getElementById("emptySeats");
    if (seatsEl) {
      seatsEl.addEventListener("change", function () {
        C.updateEntryActions();
        var sup = C.getSupabaseClient();
        if (sup) {
          var v = Math.max(0, Math.min(4, parseInt(seatsEl.value, 10) || 0));
          sup.from("driver_state").update({ empty_seats: v }).eq("driver_id", C.getDriverId()).then(function () {});
        }
      });
    }
    document.getElementById("planPanel").classList.add("hidden");
    (function () {
      var header = document.getElementById("passengerSectionHeader");
      var body = document.getElementById("passengerSectionBody");
      var chevron = document.getElementById("passengerChevron");
      if (!header || !body) return;
      function togglePassengerCard() {
        var isHidden = body.classList.contains("hidden");
        body.classList.toggle("hidden", !isHidden);
        header.setAttribute("aria-expanded", isHidden ? "true" : "false");
        if (chevron) chevron.textContent = isHidden ? "▲" : "▼";
      }
      header.addEventListener("click", togglePassengerCard);
      header.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); togglePassengerCard(); } });
    })();
    C.loadFromDb(function () {
      C.renderPassengerList();
      C.updateEntryActions();
      refreshMode();
      loadConfig();
      refreshMode();
      C.saveStateToStorage();
    });
  }

  function showSupabaseBlockedNotice() {
    var header = document.querySelector("header");
    if (!header || document.getElementById("supabaseBlockedBanner")) return;
    var banner = document.createElement("div");
    banner.id = "supabaseBlockedBanner";
    banner.className = "mb-3 px-4 py-2 rounded-xl bg-amber-900/40 border border-amber-600/50 text-amber-200 text-sm";
    banner.textContent = "Supabase 连接异常（可能被浏览器「跟踪防护」拦截），乘客数据可能无法加载。请尝试：关闭跟踪/隐私保护、使用无痕模式或换用其他浏览器。";
    header.insertAdjacentElement("afterend", banner);
  }

  function checkAuthAndRun() {
    try {
      if (typeof localStorage === "undefined") { window.location.replace("login.html"); return; }
      if (localStorage.getItem(C.STORAGE_TOKEN)) { C.loadAppConfig(run); return; }
      var url = C.getSupabaseUrl(), anon = C.getSupabaseAnon();
      if (!url || !anon || !window.supabase) { window.location.replace("login.html"); return; }
      var sup = C.getSupabaseClient();
      if (!sup) { window.location.replace("login.html"); return; }
      sup.auth.getSession()
        .then(function (r) {
          if (r.data && r.data.session) C.loadAppConfig(run);
          else window.location.replace("login.html");
        })
        .catch(function () {
          C.loadAppConfig(function () { run(); showSupabaseBlockedNotice(); });
        });
    } catch (e) {
      C.loadAppConfig(function () { run(); showSupabaseBlockedNotice(); });
    }
  }
  checkAuthAndRun();
})();

(function () {
  if (!window.__smartdiaodu_nav_fallback) return;
  window.__smartdiaodu_nav_fallback = false;
  function run() {
    var viewHome = document.getElementById("viewHome");
    var viewMap = document.getElementById("viewMap");
    var mapFrame = document.getElementById("mapFrame");
    var navHome = document.getElementById("navHome");
    var navMap = document.getElementById("navMap");
    var navSettings = document.getElementById("navSettings");
    if (!viewHome || !viewMap || !navHome || !navMap) return;
    var bottomNav = document.getElementById("bottomNav");
    var appMain = document.getElementById("appMain");
    function setActiveTab(tab) {
      [navHome, navMap, navSettings].forEach(function (el) {
        if (el) el.classList.toggle("active", el === tab);
      });
    }
    function showHome() {
      viewHome.classList.remove("hidden");
      viewMap.classList.add("hidden");
      if (bottomNav) bottomNav.classList.remove("bottom-nav-hidden");
      if (appMain) appMain.classList.remove("map-fullscreen");
      setActiveTab(navHome);
    }
    var mapLoaded = false;
    function showMap() {
      if (mapFrame && !mapLoaded) { mapFrame.src = "map.html"; mapLoaded = true; }
      viewHome.classList.add("hidden");
      viewMap.classList.remove("hidden");
      if (bottomNav) bottomNav.classList.add("bottom-nav-hidden");
      if (appMain) appMain.classList.add("map-fullscreen");
      setActiveTab(navMap);
    }
    function addTap(el, fn) {
      if (!el) return;
      el.addEventListener("click", fn);
      el.addEventListener("touchend", function (e) { e.preventDefault(); fn(); }, { passive: false });
    }
    addTap(navHome, showHome);
    addTap(navMap, showMap);
    var btnShowMap = document.getElementById("btnShowMap");
    if (btnShowMap) addTap(btnShowMap, showMap);
    if (navSettings) {
      var overlay = document.getElementById("settingsPanelOverlay");
      addTap(navSettings, function () { if (overlay) overlay.classList.add("show"); });
    }
    window.addEventListener("message", function (e) {
      if (e.data && e.data.type === "smartdiaodu_map_back") showHome();
    });
    setActiveTab(navHome);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
