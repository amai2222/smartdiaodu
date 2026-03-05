/**
 * 人工模式：多图 OCR -> 候选确认 -> 智能挑选
 */
(function () {
  "use strict";
  var C = window.SmartDiaoduConsole;
  if (!C) return;

  var imageInput = document.getElementById("manualImageInput");
  var btnOcr = document.getElementById("btnManualOcr");
  var btnClearImages = document.getElementById("btnManualClearImages");
  var ocrStatus = document.getElementById("manualOcrStatus");
  var candidatesList = document.getElementById("manualCandidatesList");
  var candidatesEmpty = document.getElementById("manualCandidatesEmpty");
  var btnSelectAll = document.getElementById("btnManualSelectAll");
  var btnInverseSelect = document.getElementById("btnManualInverseSelect");
  var btnClearCandidates = document.getElementById("btnManualClearCandidates");
  var btnExportCandidates = document.getElementById("btnManualExportCandidates");
  var ocrPlatformEl = document.getElementById("manualOcrPlatform");
  var selectCountEl = document.getElementById("manualSelectCount");
  var tacticsEl = document.getElementById("manualTactics");
  var btnRecommend = document.getElementById("btnManualRecommend");
  var recommendList = document.getElementById("manualRecommendList");
  var recommendEmpty = document.getElementById("manualRecommendEmpty");

  if (!imageInput || !btnOcr || !candidatesList || !btnRecommend) return;

  var S = {
    files: [], // 压缩后的 File[]
    compressingCount: 0,
    candidates: [] // { pickup, delivery, price, source_image, checked }
  };

  function setStatus(text) {
    if (ocrStatus) ocrStatus.textContent = text || "";
  }

  function setOcrBtnEnabled(enabled) {
    if (!btnOcr) return;
    btnOcr.disabled = !enabled;
    btnOcr.classList.toggle("opacity-60", !enabled);
    btnOcr.classList.toggle("cursor-not-allowed", !enabled);
  }

  function getAuthHeaders(isJson) {
    var h = {};
    if (isJson !== false) h["Content-Type"] = "application/json";
    try {
      var token = localStorage.getItem(C.STORAGE_TOKEN);
      if (token) h.Authorization = "Bearer " + token;
    } catch (e) {}
    return h;
  }

  function readFileAsDataURL(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || "")); };
      reader.onerror = function () { reject(new Error("读取图片失败")); };
      reader.readAsDataURL(file);
    });
  }

  function canvasToBlob(canvas, quality) {
    return new Promise(function (resolve) {
      canvas.toBlob(function (blob) { resolve(blob); }, "image/jpeg", quality);
    });
  }

  async function compressImageFile(file) {
    // 小图直接用原图，减少二次编码损耗。
    if (!file || file.size <= 900 * 1024) return file;
    var dataUrl = await readFileAsDataURL(file);
    var img = await new Promise(function (resolve, reject) {
      var el = new Image();
      el.onload = function () { resolve(el); };
      el.onerror = function () { reject(new Error("加载图片失败")); };
      el.src = dataUrl;
    });
    var w = img.naturalWidth || img.width;
    var h = img.naturalHeight || img.height;
    if (!w || !h) return file;
    var maxSide = 1600;
    var scale = Math.min(1, maxSide / Math.max(w, h));
    var tw = Math.max(1, Math.round(w * scale));
    var th = Math.max(1, Math.round(h * scale));
    var canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    var ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(img, 0, 0, tw, th);
    var blob = await canvasToBlob(canvas, 0.78);
    if (!blob || blob.size <= 0) return file;
    if (blob.size >= file.size) return file;
    var name = (file.name || "upload").replace(/\.(png|webp|heic|heif)$/i, ".jpg");
    return new File([blob], name, { type: "image/jpeg", lastModified: Date.now() });
  }

  function getOcrPlatform() {
    var p = (ocrPlatformEl && ocrPlatformEl.value) || "hello";
    p = String(p).toLowerCase();
    if (p !== "hello" && p !== "didi" && p !== "auto") return "hello";
    return p;
  }

  function getCardTemplateRects(platform) {
    if (platform === "didi") {
      return [
        { x: 0.03, y: 0.13, w: 0.94, h: 0.24 },
        { x: 0.03, y: 0.38, w: 0.94, h: 0.24 },
        { x: 0.03, y: 0.63, w: 0.94, h: 0.24 }
      ];
    }
    return [
      { x: 0.03, y: 0.14, w: 0.94, h: 0.24 },
      { x: 0.03, y: 0.39, w: 0.94, h: 0.24 },
      { x: 0.03, y: 0.64, w: 0.94, h: 0.24 }
    ];
  }

  async function loadImageFromFile(file) {
    var dataUrl = await readFileAsDataURL(file);
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { reject(new Error("加载图片失败")); };
      img.src = dataUrl;
    });
  }

  async function cropWithTemplate(file, platform) {
    if (platform === "auto") return [file];
    var img = await loadImageFromFile(file);
    var sw = img.naturalWidth || img.width;
    var sh = img.naturalHeight || img.height;
    if (!sw || !sh) return [file];
    var rects = getCardTemplateRects(platform);
    var out = [];
    var base = (file.name || "image").replace(/\.[^.]+$/, "");
    for (var i = 0; i < rects.length; i++) {
      var r = rects[i];
      var sx = Math.max(0, Math.floor(sw * r.x));
      var sy = Math.max(0, Math.floor(sh * r.y));
      var cw = Math.max(1, Math.floor(sw * r.w));
      var ch = Math.max(1, Math.floor(sh * r.h));
      if (sx + cw > sw) cw = sw - sx;
      if (sy + ch > sh) ch = sh - sy;
      if (cw <= 0 || ch <= 0) continue;
      var canvas = document.createElement("canvas");
      canvas.width = cw;
      canvas.height = ch;
      var ctx = canvas.getContext("2d");
      if (!ctx) continue;
      ctx.drawImage(img, sx, sy, cw, ch, 0, 0, cw, ch);
      var blob = await canvasToBlob(canvas, 0.86);
      if (!blob || blob.size <= 0) continue;
      out.push(new File([blob], base + "_card" + (i + 1) + ".jpg", { type: "image/jpeg", lastModified: Date.now() }));
    }
    return out.length ? out : [file];
  }

  async function buildOcrFiles(files, platform) {
    if (!files || !files.length) return [];
    if (platform === "auto") return files.slice();
    var out = [];
    for (var i = 0; i < files.length; i++) {
      var cropped = await cropWithTemplate(files[i], platform);
      for (var j = 0; j < cropped.length; j++) out.push(cropped[j]);
    }
    return out;
  }

  function parsePrice(v) {
    if (v === null || v === undefined || v === "") return null;
    var n = Number(v);
    return isNaN(n) ? null : n;
  }

  function renderCandidates() {
    candidatesList.innerHTML = "";
    if (!S.candidates.length) {
      if (candidatesEmpty) candidatesEmpty.style.display = "";
      return;
    }
    if (candidatesEmpty) candidatesEmpty.style.display = "none";
    S.candidates.forEach(function (c, i) {
      var row = document.createElement("div");
      row.className = "p-3 rounded-xl border border-border bg-[#0c0c0f]";
      row.innerHTML =
        "<div class=\"flex items-center justify-between gap-2 mb-2\">" +
          "<label class=\"text-xs text-muted\"><input type=\"checkbox\" class=\"manual-cand-check mr-1\" " + (c.checked ? "checked" : "") + " data-idx=\"" + i + "\" /> 参与筛选</label>" +
          "<span class=\"text-xs text-muted\">" + ((c.source_image || "").replace(/</g, "&lt;").replace(/>/g, "&gt;")) + "</span>" +
        "</div>" +
        "<div class=\"grid grid-cols-1 gap-2\">" +
          "<input class=\"manual-cand-pickup bg-panel border border-border rounded-lg px-2 py-2 text-sm\" data-idx=\"" + i + "\" value=\"" + (c.pickup || "").replace(/"/g, "&quot;") + "\" placeholder=\"起点\" />" +
          "<input class=\"manual-cand-delivery bg-panel border border-border rounded-lg px-2 py-2 text-sm\" data-idx=\"" + i + "\" value=\"" + (c.delivery || "").replace(/"/g, "&quot;") + "\" placeholder=\"终点\" />" +
          "<input class=\"manual-cand-departure bg-panel border border-border rounded-lg px-2 py-2 text-sm\" data-idx=\"" + i + "\" value=\"" + (c.departure_time || "").replace(/"/g, "&quot;") + "\" placeholder=\"出发时间（可选，如 08:10）\" />" +
          "<input class=\"manual-cand-price bg-panel border border-border rounded-lg px-2 py-2 text-sm\" data-idx=\"" + i + "\" value=\"" + (c.price == null ? "" : c.price) + "\" placeholder=\"收益（可选）\" />" +
        "</div>";
      candidatesList.appendChild(row);
    });
  }

  function renderRecommend(items) {
    recommendList.innerHTML = "";
    if (!items || !items.length) {
      if (recommendEmpty) recommendEmpty.style.display = "";
      return;
    }
    if (recommendEmpty) recommendEmpty.style.display = "none";
    items.forEach(function (r, i) {
      var eta = r.pickup_eta_seconds == null ? "—" : (Math.round(r.pickup_eta_seconds / 60) + " 分钟");
      var detour = r.detour_seconds == null ? "—" : (Math.round(r.detour_seconds / 60) + " 分钟");
      var dep = r.departure_time || "—";
      var arrive = r.estimated_arrival_time || "—";
      var depDiff = r.departure_diff_seconds == null ? "—" : (Math.round(Math.abs(r.departure_diff_seconds) / 60) + " 分钟");
      var tollText = r.toll_negotiable === true ? "可协商高速费" : (r.toll_negotiable === false ? "不承担高速费" : "高速费未知");
      var rankLabel = r._rank_label || "推荐";
      var el = document.createElement("div");
      el.className = "p-3 rounded-xl border " + (r.eligible ? "border-success/60 bg-success/10" : "border-danger/60 bg-danger/10");
      el.innerHTML =
        "<div class=\"text-sm font-medium text-gray-100 mb-1\">" + rankLabel + " " + (i + 1) + "</div>" +
        "<div class=\"text-xs text-muted\">起点：<span class=\"text-gray-200\">" + (r.pickup || "").replace(/</g, "&lt;").replace(/>/g, "&gt;") + "</span></div>" +
        "<div class=\"text-xs text-muted\">终点：<span class=\"text-gray-200\">" + (r.delivery || "").replace(/</g, "&lt;").replace(/>/g, "&gt;") + "</span></div>" +
        "<div class=\"text-xs text-muted mt-1\">到起点：" + eta + " · 预计新增绕路：" + detour + "</div>" +
        "<div class=\"text-xs text-muted\">高速费：" + tollText + "</div>" +
        "<div class=\"text-xs text-muted\">乘客出发：" + dep + " · 预计到达起点：" + arrive + " · 时间差：" + depDiff + "（要求 ±30 分钟）</div>" +
        "<div class=\"text-xs " + (r.eligible ? "text-success" : "text-danger") + "\">" + (r.reason || "") + " · 评分：" + (r.score == null ? "—" : r.score) + "</div>";
      recommendList.appendChild(el);
    });
  }

  function syncCandidatesFromDom() {
    var checks = candidatesList.querySelectorAll(".manual-cand-check");
    for (var i = 0; i < checks.length; i++) {
      var idx = parseInt(checks[i].getAttribute("data-idx"), 10);
      if (S.candidates[idx]) S.candidates[idx].checked = !!checks[i].checked;
    }
    var ps = candidatesList.querySelectorAll(".manual-cand-pickup");
    for (var j = 0; j < ps.length; j++) {
      var idxP = parseInt(ps[j].getAttribute("data-idx"), 10);
      if (S.candidates[idxP]) S.candidates[idxP].pickup = (ps[j].value || "").trim();
    }
    var ds = candidatesList.querySelectorAll(".manual-cand-delivery");
    for (var k = 0; k < ds.length; k++) {
      var idxD = parseInt(ds[k].getAttribute("data-idx"), 10);
      if (S.candidates[idxD]) S.candidates[idxD].delivery = (ds[k].value || "").trim();
    }
    var ts = candidatesList.querySelectorAll(".manual-cand-departure");
    for (var t = 0; t < ts.length; t++) {
      var idxT = parseInt(ts[t].getAttribute("data-idx"), 10);
      if (S.candidates[idxT]) S.candidates[idxT].departure_time = (ts[t].value || "").trim();
    }
    var rs = candidatesList.querySelectorAll(".manual-cand-price");
    for (var m = 0; m < rs.length; m++) {
      var idxR = parseInt(rs[m].getAttribute("data-idx"), 10);
      if (S.candidates[idxR]) S.candidates[idxR].price = parsePrice((rs[m].value || "").trim());
    }
  }

  imageInput.addEventListener("change", function () {
    var files = imageInput.files || [];
    if (!files.length) return;
    var pending = files.length;
    S.compressingCount += files.length;
    setOcrBtnEnabled(false);
    setStatus("压缩图片中…");
    for (var i = 0; i < files.length; i++) {
      (function (f) {
        compressImageFile(f).then(function (ff) {
          S.files.push(ff);
          pending -= 1;
          S.compressingCount = Math.max(0, S.compressingCount - 1);
          if (pending <= 0) {
            var total = 0;
            for (var x = 0; x < S.files.length; x++) total += (S.files[x].size || 0);
            setStatus("已就绪 " + S.files.length + " 张，约 " + Math.round(total / 1024) + "KB");
            setOcrBtnEnabled(S.compressingCount === 0);
          }
        }).catch(function () {
          pending -= 1;
          S.compressingCount = Math.max(0, S.compressingCount - 1);
          if (pending <= 0) {
            setStatus("图片读取完成（部分失败）");
            setOcrBtnEnabled(S.compressingCount === 0);
          }
        });
      })(files[i]);
    }
    imageInput.value = "";
  });

  btnClearImages.addEventListener("click", function () {
    S.files = [];
    S.compressingCount = 0;
    setOcrBtnEnabled(true);
    setStatus("已清空图片");
  });

  btnSelectAll.addEventListener("click", function () {
    syncCandidatesFromDom();
    for (var i = 0; i < S.candidates.length; i++) S.candidates[i].checked = true;
    renderCandidates();
  });
  if (btnInverseSelect) btnInverseSelect.addEventListener("click", function () {
    syncCandidatesFromDom();
    for (var i = 0; i < S.candidates.length; i++) S.candidates[i].checked = !S.candidates[i].checked;
    renderCandidates();
  });
  if (btnClearCandidates) btnClearCandidates.addEventListener("click", function () {
    S.candidates = [];
    renderCandidates();
    renderRecommend([]);
    setStatus("已清空候选");
  });
  if (btnExportCandidates) btnExportCandidates.addEventListener("click", function () {
    syncCandidatesFromDom();
    if (!S.candidates.length) {
      setStatus("暂无可导出候选");
      return;
    }
    try {
      var data = {
        exported_at: new Date().toISOString(),
        count: S.candidates.length,
        candidates: S.candidates
      };
      var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "manual_candidates_" + Date.now() + ".json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus("候选已导出");
    } catch (e) {
      setStatus("导出失败: " + (e.message || e));
    }
  });

  btnOcr.addEventListener("click", function () {
    var base = C.getApiBase();
    if (!base) { setStatus("未配置后端 api_base"); return; }
    if (S.compressingCount > 0) { setStatus("图片仍在压缩，请稍候…"); return; }
    if (!S.files.length) { setStatus("请先上传截图"); return; }
    var platform = getOcrPlatform();
    setOcrBtnEnabled(false);
    setStatus(platform === "auto" ? "OCR 识别中…" : ("按" + (platform === "hello" ? "哈啰" : "滴滴") + "模板裁剪并识别中…"));
    buildOcrFiles(S.files, platform).then(function (ocrFiles) {
      var form = new FormData();
      for (var i = 0; i < ocrFiles.length; i++) {
        form.append("files", ocrFiles[i], ocrFiles[i].name || ("image_" + (i + 1) + ".jpg"));
      }
      form.append("ocr_platform", platform);
      return fetch(base + "/manual_ocr_extract", {
        method: "POST",
        headers: getAuthHeaders(false),
        body: form
      });
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (d) {
            throw new Error((d && d.detail) || ("HTTP " + r.status));
          });
        }
        return r.json();
      })
      .then(function (d) {
        var arr = (d && d.candidates) || [];
        S.candidates = arr.map(function (x) {
          return {
            pickup: (x.pickup || "").trim(),
            delivery: (x.delivery || "").trim(),
            price: x.price == null ? null : Number(x.price),
            departure_time: (x.departure_time || "").trim(),
            toll_negotiable: typeof x.toll_negotiable === "boolean" ? x.toll_negotiable : null,
            source_image: x.source_image || "",
            checked: true
          };
        });
        renderCandidates();
        setStatus("OCR 完成：识别候选 " + S.candidates.length + " 人");
      })
      .catch(function (e) {
        setStatus("OCR 失败: " + (e.message || e));
      })
      .finally(function () {
        setOcrBtnEnabled(S.compressingCount === 0);
      });
  });

  btnRecommend.addEventListener("click", function () {
    syncCandidatesFromDom();
    var selected = S.candidates.filter(function (c) { return c.checked && c.pickup && c.delivery; });
    if (!selected.length) {
      renderRecommend([]);
      if (recommendEmpty) recommendEmpty.textContent = "请至少勾选 1 条有效候选";
      return;
    }
    var base = C.getApiBase();
    if (!base) { setStatus("未配置后端 api_base"); return; }
    var body = {
      candidates: selected.map(function (c) { return { pickup: c.pickup, delivery: c.delivery, price: c.price, departure_time: c.departure_time || null, toll_negotiable: c.toll_negotiable }; }),
      select_count: parseInt((selectCountEl && selectCountEl.value) || "1", 10) || 1,
      tactics: parseInt((tacticsEl && tacticsEl.value) || "0", 10) || 0
    };
    setStatus("智能筛选中…");
    fetch(base + "/manual_candidates_recommend", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(body)
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (d) {
            throw new Error((d && d.detail) || ("HTTP " + r.status));
          });
        }
        return r.json();
      })
      .then(function (d) {
        var main = (d && d.recommended) || [];
        var backup = (d && d.backup_recommended) || [];
        var list = [];
        for (var i = 0; i < main.length; i++) {
          var x1 = Object.assign({}, main[i]);
          x1._rank_label = "推荐";
          list.push(x1);
        }
        for (var j = 0; j < backup.length; j++) {
          var x2 = Object.assign({}, backup[j]);
          x2._rank_label = "备选";
          list.push(x2);
        }
        renderRecommend(list);
        setStatus("筛选完成：已推荐 " + ((d && d.selected_count) || 0) + " 人，备选 " + ((d && d.backup_count) || 0) + " 人");
      })
      .catch(function (e) {
        setStatus("筛选失败: " + (e.message || e));
      });
  });
})();
