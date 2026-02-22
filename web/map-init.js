/**
 * 路线地图 - 地图初始化与覆盖物清理（百度地图加载、BMap 实例）
 * 依赖：map-config.js, map-state.js
 */
(function () {
  "use strict";
  var M = window.SmartDiaoduMap;
  if (!M) return;

  /** 专门对付 Safari iframe 高度 Bug：innerHeight 是 iframe 内唯一靠谱的可见高度，强制注入 #map */
  function fixSafariIframeHeight() {
    var mapEl = document.getElementById("map");
    if (mapEl) {
      mapEl.style.height = window.innerHeight + "px";
    }
  }
  fixSafariIframeHeight();
  window.addEventListener("resize", function () {
    fixSafariIframeHeight();
    if (M.bmap && typeof M.bmap.invalidateSize === "function") {
      clearTimeout(M._resizeMapT);
      M._resizeMapT = setTimeout(function () { try { M.bmap.invalidateSize(); } catch (e) {} }, 100);
    }
  });
  window.addEventListener("orientationchange", function () {
    setTimeout(fixSafariIframeHeight, 100);
    setTimeout(function () {
      if (M.bmap && typeof M.bmap.invalidateSize === "function") try { M.bmap.invalidateSize(); } catch (e) {}
    }, 300);
  });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", fixSafariIframeHeight);
    window.visualViewport.addEventListener("scroll", fixSafariIframeHeight);
  }

  M.destroyMap = function () {
    if (M.bmap) { try { M.bmap.destroy(); } catch (e) {} M.bmap = null; }
  };

  M.clearMapOverlays = function () {
    if (M.bmap) {
      if (typeof M.bmap.clearOverlays === "function") M.bmap.clearOverlays();
      else if (typeof M.bmap.getOverlays === "function") {
        var list = M.bmap.getOverlays();
        if (list && list.length) for (var i = 0; i < list.length; i++) M.bmap.removeOverlay(list[i]);
      }
    }
  };

  function loadBaiduSymbolLib(cb) {
    if (window.BMap_Symbol_SHAPE_FORWARD_CLOSED_ARROW != null) { if (cb) cb(); return; }
    var s = document.createElement("script");
    s.src = "https://api.map.baidu.com/library/DrawingManager/1.4/src/DrawingManager_min.js";
    s.onload = s.onerror = function () { if (cb) cb(); };
    document.head.appendChild(s);
  }
  M.loadBaiduSymbolLib = loadBaiduSymbolLib;

  function setRouteStatus(msg) {
    var el = document.getElementById("routeInfo");
    if (el) el.textContent = msg || "";
  }

  M.initMap = function () {
    var ak = (M.getBaiduMapAk() || "").trim();
    if (!ak) {
      setRouteStatus("请在 app_config 中配置 baidu_map_ak（网页端 AK）");
      return;
    }
    M.destroyMap();
    M.useBMapGL = false;
    if (window.BMap && typeof window.BMap.Map === "function") {
      M.initBaiduMap();
      loadBaiduSymbolLib(function () {
        if (M.lastRouteData && M.drawRouteFromIndex) M.drawRouteFromIndex(M.currentStopIndex);
        else if (M.getCurrentState && M.loadAndDraw) {
          var state = M.getCurrentState();
          if (state && (state.driver_loc || "").trim()) M.loadAndDraw();
        }
      });
      return;
    }
    window.baiduMapReady = function () {
      window.baiduMapReady = null;
      try {
        if (window.BMap && typeof window.BMap.Map === "function") {
          M.initBaiduMap();
          loadBaiduSymbolLib(function () {
            if (M.lastRouteData && M.drawRouteFromIndex) {
              M.drawRouteFromIndex(M.currentStopIndex);
            } else if (M.getCurrentState && M.loadAndDraw) {
              var state = M.getCurrentState();
              if (state && (state.driver_loc || "").trim()) M.loadAndDraw();
            }
          });
          return;
        }
      } catch (e) {
        setRouteStatus("百度地图加载异常，请刷新重试。若仍失败，请检查网络能否访问百度地图。");
        return;
      }
      setRouteStatus("百度地图 API 未就绪。请检查 F12 → Network 中 api.map.baidu.com 请求与 AK 白名单。");
    };
    var script = document.createElement("script");
    script.src = "https://api.map.baidu.com/api?v=3.0&ak=" + encodeURIComponent(ak) + "&s=1&callback=baiduMapReady";
    script.onerror = function () {
      setRouteStatus("百度地图脚本加载失败（网络错误）。请检查：1) 网络能否访问 api.map.baidu.com 2) AK 是否有效。");
    };
    document.head.appendChild(script);
  };

  M.initBaiduMap = function () {
    if (M.bmap) return;
    fixSafariIframeHeight();
    var container = document.getElementById("map");
    if (!container) return;
    if (M.useBMapGL && window.BMapGL && typeof window.BMapGL.Map === "function") {
      M.bmap = new window.BMapGL.Map("map");
      M.bmap.centerAndZoom(new window.BMapGL.Point(121.18, 32.32), 10);
      M.bmap.enableScrollWheelZoom(true);
      if (typeof M.bmap.invalidateSize === "function") setTimeout(function () { M.bmap.invalidateSize(); }, 200);
      return;
    }
    if (window.BMap && typeof window.BMap.Map === "function") {
      M.bmap = new window.BMap.Map("map");
      M.bmap.centerAndZoom(new window.BMap.Point(121.0, 32.0), 10);
      M.bmap.enableScrollWheelZoom(true);
      if (typeof M.bmap.enableDragging === "function") M.bmap.enableDragging();
      if (typeof M.bmap.enableInertialDragging === "function") M.bmap.enableInertialDragging();
      if (typeof M.bmap.enableDoubleClickZoom === "function") M.bmap.enableDoubleClickZoom(true);
      if (typeof M.bmap.addEventListener === "function") {
        M.bmap.addEventListener("tilesloaded", function () {});
        M.bmap.addEventListener("zoomend", function () {
          if (M.zoomRedrawTimer) clearTimeout(M.zoomRedrawTimer);
          var z = typeof M.bmap.getZoom === "function" ? M.bmap.getZoom() : null;
          if (z === M.lastRedrawZoom) return;
          M.zoomRedrawTimer = setTimeout(function () {
            M.zoomRedrawTimer = null;
            M.lastRedrawZoom = (typeof M.bmap.getZoom === "function" ? M.bmap.getZoom() : null);
            if (typeof requestAnimationFrame === "function") {
              requestAnimationFrame(function () { if (M.redrawRouteOnZoomChange) M.redrawRouteOnZoomChange(); });
            } else if (M.redrawRouteOnZoomChange) {
              M.redrawRouteOnZoomChange();
            }
          }, 480);
        });
      }
      setTimeout(function () {
        if (M.bmap && typeof M.bmap.invalidateSize === "function") M.bmap.invalidateSize();
      }, 200);
    }
  };

  if (window !== window.top) {
    setTimeout(fixSafariIframeHeight, 50);
    setTimeout(fixSafariIframeHeight, 200);
    setTimeout(function () {
      fixSafariIframeHeight();
      if (M.bmap && typeof M.bmap.invalidateSize === "function") try { M.bmap.invalidateSize(); } catch (e) {}
    }, 500);
    setTimeout(function () {
      fixSafariIframeHeight();
      if (M.bmap && typeof M.bmap.invalidateSize === "function") try { M.bmap.invalidateSize(); } catch (e) {}
    }, 1500);
  }
})();
