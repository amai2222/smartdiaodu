/**
 * 路线地图 - 路线绘制与导航 URL（坐标转换、分段算路、箭头与标注）
 * 依赖：map-config.js, map-state.js, map-init.js
 */
(function () {
  "use strict";
  var M = window.SmartDiaoduMap;
  if (!M) return;

  var ROUTE_STROKE_WEIGHT = 12;
  var ROUTE_GREEN = "#18a45b";
  var ROUTE_ALTERNATIVE_COLOR = "#7cb89a";

  M.getNumPlans = function (results) {
    if (!results || typeof results.getPlan !== "function") return 0;
    var n = 0;
    try { while (results.getPlan(n)) n++; } catch (e) {}
    return n;
  };

  /** 百度驾车策略枚举值。BMap 未就绪时用 0（默认）兜底，避免首次打开路线策略未生效。 */
  M.getDrivingPolicyValue = function (key) {
    var P = window.BMap && window.BMap.DrivingPolicy;
    var k = (key || M.routePolicyKey || "DEFAULT").toUpperCase();
    if (P) {
      if (P[k] != null) return P[k];
      if (k === "LEAST_FEE" && P.LEAST_TOLL != null) return P.LEAST_TOLL;
      if (k === "DEFAULT") return 0;
      if (P.LEAST_TIME != null) return P.LEAST_TIME;
    }
    return 0;
  };

  M.wgs84ToBd09 = function (lat, lng) {
    var x_PI = (3.14159265358979324 * 3000.0) / 180.0, a = 6378245.0, ee = 0.00669342162296594323;
    function trLat(x, y) {
      var r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
      r += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
      r += (20 * Math.sin(y * Math.PI) + 40 * Math.sin(y / 3 * Math.PI)) * 2 / 3;
      return r;
    }
    function trLng(x, y) {
      var r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
      r += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
      r += (20 * Math.sin(x * Math.PI) + 40 * Math.sin(x / 3 * Math.PI)) * 2 / 3;
      return r;
    }
    var dlat = trLat(lng - 105, lat - 35), dlng = trLng(lng - 105, lat - 35);
    var radlat = (lat / 180) * Math.PI, magic = 1 - ee * Math.sin(radlat) * Math.sin(radlat), sqrtmagic = Math.sqrt(magic);
    dlat = (dlat * 180) / ((a * (1 - ee)) / (magic * sqrtmagic) * Math.PI);
    dlng = (dlng * 180) / (a / sqrtmagic * Math.cos(radlat) * Math.PI);
    var mglat = lat + dlat, mglng = lng + dlng;
    return [mglng + 0.0065 * Math.cos(mglat * x_PI), mglat + 0.006 * Math.sin(mglng * x_PI)];
  };

  /** 入参为 BD09（与 route_coords 一致）时直接拼 URL；若为 WGS84 请先转 BD09 再传入。 */
  M.getNavUrl = function (lat, lng, name) {
    if (lat == null || lng == null) return "#";
    var dest = lat + "," + lng;
    return "baidumap://map/direction?destination=name:" + encodeURIComponent(name || "") + "|latlng:" + dest + "&mode=driving";
  };

  /** 后端返回的 route_coords / route_path 均为 BD09 [lat, lng]，可直接用于百度地图。 */
  M.getNavUrlWithWaypoints = function () {
    if (!M.route_coords.length || M.route_addresses.length !== M.route_coords.length) return "#";
    var c0 = M.route_coords[0], cLast = M.route_coords[M.route_coords.length - 1];
    if (!c0 || c0[0] == null || c0[1] == null || !cLast || cLast[0] == null || cLast[1] == null) return "#";
    var lat0 = c0[0], lng0 = c0[1], latLast = cLast[0], lngLast = cLast[1];
    var origin = "latlng:" + lat0 + "," + lng0 + "|name:" + (M.point_labels[0] || "起点");
    var destination = "latlng:" + latLast + "," + lngLast + "|name:" + (M.point_labels[M.point_labels.length - 1] || "终点");
    var viaPointsList = [];
    for (var i = 1; i < M.route_coords.length - 1; i++) {
      var c = M.route_coords[i];
      if (!c || c[0] == null || c[1] == null) continue;
      viaPointsList.push({ name: (M.point_labels[i] || ("第" + (i + 1) + "站")) + "", lat: c[0], lng: c[1] });
    }
    var viaData = { viaPoints: viaPointsList };
    var viaPointsStr = encodeURIComponent(JSON.stringify(viaData));
    return "baidumap://map/direction?mode=driving&origin=" + encodeURIComponent(origin) + "&destination=" + encodeURIComponent(destination) + "&viaPoints=" + viaPointsStr + "&coord_type=bd09ll&src=smartdiaodu";
  };

  function getStartEndIconDataURL(text, bgColor) {
    var s = '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36"><circle cx="18" cy="18" r="16" fill="' + bgColor + '" stroke="#fff" stroke-width="2"/><text x="18" y="23" text-anchor="middle" fill="#fff" font-size="14" font-weight="bold" font-family="sans-serif">' + text + '</text></svg>';
    return "data:image/svg+xml," + encodeURIComponent(s);
  }
  function getViaPointIconDataURL(num, isDelivery) {
    var bg = isDelivery ? "#eab308" : "#3b82f6";
    var s = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="12" fill="' + bg + '" stroke="#fff" stroke-width="2"/><text x="14" y="18" text-anchor="middle" fill="#fff" font-size="12" font-weight="bold" font-family="sans-serif">' + num + '</text></svg>';
    return "data:image/svg+xml," + encodeURIComponent(s);
  }

  M.addMarkersWithNS = function (bdPoints, fromIndex, addresses, labels, types, NS) {
    var orderNums = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];
    for (var i = 0; i < bdPoints.length; i++) {
      var pt = bdPoints[i], num = fromIndex + i + 1, numStr = orderNums[num - 1] || String(num);
      var typeLabel = (labels && labels[i]) || (types && types[i]) || "途经", fullAddr = (addresses && addresses[i]) ? String(addresses[i]) : "";
      var mk;
      if (i === 0) {
        mk = new NS.Marker(pt, { icon: new NS.Icon(getStartEndIconDataURL("起", "#22c55e"), new NS.Size(36, 36)) });
      } else if (i === bdPoints.length - 1) {
        mk = new NS.Marker(pt, { icon: new NS.Icon(getStartEndIconDataURL("终", "#ef4444"), new NS.Size(36, 36)) });
      } else {
        var isDelivery = (types && types[i] === "delivery");
        mk = new NS.Marker(pt, { icon: new NS.Icon(getViaPointIconDataURL(numStr, isDelivery), new NS.Size(28, 28)) });
        if (typeof NS.InfoWindow !== "undefined" && M.bmap) {
          var detail = typeLabel + (fullAddr ? "<br/>" + fullAddr.replace(/</g, "&lt;") : "");
          (function (marker, content) {
            marker.addEventListener("click", function () {
              var info = new NS.InfoWindow(content, { width: 260, enableMessage: false });
              M.bmap.openInfoWindow(info, marker.getPosition());
            });
          })(mk, detail);
        }
      }
      M.bmap.addOverlay(mk);
    }
  };

  function pathLengthMeters(pathBd) {
    if (!pathBd || pathBd.length < 2) return 0;
    function dist(p1, p2) {
      var dx = (p2.lng - p1.lng) * 111320 * Math.cos((p1.lat || 0) * Math.PI / 180);
      var dy = (p2.lat - p1.lat) * 110540;
      return Math.sqrt(dx * dx + dy * dy);
    }
    var total = 0;
    for (var i = 0; i < pathBd.length - 1; i++) total += dist(pathBd[i], pathBd[i + 1]);
    return total;
  }
  function getMetersPerPixel() {
    if (!M.bmap || typeof M.bmap.getZoom !== "function") return 10;
    var z = M.bmap.getZoom();
    var center = M.bmap.getCenter && M.bmap.getCenter();
    var lat = center && center.lat != null ? center.lat : 31;
    return (156543.03392 * Math.cos(lat * Math.PI / 180)) / Math.pow(2, z);
  }
  function pathSegmentForArrows(pathBd, startFrac, endFrac, excludeRanges) {
    if (!pathBd || pathBd.length < 2 || startFrac >= endFrac) return [];
    var BPoint = window.BMap && window.BMap.Point;
    if (!BPoint) return [pathBd];
    function dist(p1, p2) {
      var dx = (p2.lng - p1.lng) * 111320 * Math.cos((p1.lat || 0) * Math.PI / 180);
      var dy = (p2.lat - p1.lat) * 110540;
      return Math.sqrt(dx * dx + dy * dy);
    }
    function interp(p1, p2, t) {
      return new BPoint(p1.lng + t * (p2.lng - p1.lng), p1.lat + t * (p2.lat - p1.lat));
    }
    var total = 0, segs = [];
    for (var i = 0; i < pathBd.length - 1; i++) {
      var d = dist(pathBd[i], pathBd[i + 1]);
      segs.push({ start: pathBd[i], end: pathBd[i + 1], len: d });
      total += d;
    }
    if (total <= 0) return [pathBd];
    var exclude = excludeRanges || [];
    var ranges = [{ start: startFrac, end: endFrac }];
    for (var e = 0; e < exclude.length; e++) {
      var newRanges = [];
      for (var r = 0; r < ranges.length; r++) {
        var ra = ranges[r], ex = exclude[e];
        if (ex.end <= ra.start || ex.start >= ra.end) { newRanges.push(ra); continue; }
        if (ex.start > ra.start) newRanges.push({ start: ra.start, end: ex.start });
        if (ex.end < ra.end) newRanges.push({ start: ex.end, end: ra.end });
      }
      ranges = newRanges;
    }
    var outSegments = [];
    for (var ri = 0; ri < ranges.length; ri++) {
      var startLen = ranges[ri].start * total, endLen = ranges[ri].end * total, acc = 0, out = [];
      for (var j = 0; j < segs.length; j++) {
        var seg = segs[j], segStart = acc, segEnd = acc + seg.len;
        acc = segEnd;
        if (segEnd <= startLen || segStart >= endLen) continue;
        var t0 = segStart < startLen ? (startLen - segStart) / seg.len : 0;
        var t1 = segEnd > endLen ? (endLen - segStart) / seg.len : 1;
        if (t0 > 0) out.push(interp(seg.start, seg.end, t0));
        if (t1 > t0 && t1 < 1) out.push(interp(seg.start, seg.end, t1));
        else if (t1 >= 1) out.push(seg.end);
      }
      if (out.length >= 2) outSegments.push(out);
    }
    return outSegments.length ? outSegments : [pathBd];
  }
  /** 直线段箭头间距（像素），约疏 3 倍 */
  function getArrowRepeatPixelsStraight() {
    if (!M.bmap || typeof M.bmap.getZoom !== "function") return 78;
    var z = M.bmap.getZoom();
    if (z <= 10) return 108;
    if (z <= 13) return 90;
    if (z <= 16) return 84;
    return 78;
  }
  /** 弯道箭头间距（像素），约疏 3 倍 */
  function getArrowRepeatPixelsCurve() {
    if (!M.bmap || typeof M.bmap.getZoom !== "function") return 126;
    var z = M.bmap.getZoom();
    if (z <= 10) return 156;
    if (z <= 13) return 138;
    if (z <= 16) return 132;
    return 126;
  }

  /** 判断路段是否偏弯：路径长/直线距离 > 阈值则视为弯道 */
  function isCurvedSegment(segBd) {
    if (!segBd || segBd.length < 2) return false;
    var pathLen = pathLengthMeters(segBd);
    var straightLen = pathLengthMeters([segBd[0], segBd[segBd.length - 1]]);
    if (straightLen <= 0) return true;
    return pathLen / straightLen > 1.12;
  }

  M.addDirectionalPolyline = function (pathBd, strokeColor, excludeRanges) {
    if (M.useBMapGL) return;
    strokeColor = strokeColor || ROUTE_GREEN;
    try {
      var SymbolShape = window.BMap_Symbol_SHAPE_FORWARD_CLOSED_ARROW
        || (window.BMap.Symbol && (window.BMap.Symbol.SHAPE_FORWARD_CLOSED_ARROW || window.BMap.SymbolShapeType && window.BMap.SymbolShapeType.BMAP_SHAPE_FORWARD_CLOSED_ARROW));
      if (SymbolShape == null && window.BMap.Symbol) SymbolShape = 2;
      if (window.BMap.Symbol && window.BMap.IconSequence && SymbolShape != null) {
        var lineFull = new window.BMap.Polyline(pathBd, { strokeColor: strokeColor, strokeWeight: ROUTE_STROKE_WEIGHT, strokeOpacity: 0.95 });
        M.bmap.addOverlay(lineFull);
        var sy = new window.BMap.Symbol(SymbolShape, {
          scale: 0.9,
          strokeColor: "#ffffff",
          fillColor: strokeColor,
          strokeWeight: 1,
          fillOpacity: 1
        });
        var arrowSegments = pathSegmentForArrows(pathBd, 0.08, 0.92, excludeRanges || []);
        for (var si = 0; si < arrowSegments.length; si++) {
          var seg = arrowSegments[si];
          if (seg.length < 2) continue;
          var segBd = [];
          for (var pi = 0; pi < seg.length; pi++) {
            var pt = seg[pi];
            var lng = pt.lng != null ? pt.lng : (typeof pt.getLng === "function" ? pt.getLng() : null);
            var lat = pt.lat != null ? pt.lat : (typeof pt.getLat === "function" ? pt.getLat() : null);
            if (lng != null && lat != null) segBd.push({ lng: lng, lat: lat });
          }
          var arrowPx = (segBd.length >= 2 && isCurvedSegment(segBd)) ? getArrowRepeatPixelsCurve() : getArrowRepeatPixelsStraight();
          var icons = new window.BMap.IconSequence(sy, "0", String(arrowPx));
          var lineArrows = new window.BMap.Polyline(seg, { strokeColor: "transparent", strokeWeight: ROUTE_STROKE_WEIGHT, strokeOpacity: 0, icons: [icons] });
          M.bmap.addOverlay(lineArrows);
        }
        return;
      }
    } catch (e) {}
    M.bmap.addOverlay(new window.BMap.Polyline(pathBd, { strokeColor: strokeColor, strokeWeight: ROUTE_STROKE_WEIGHT, strokeOpacity: 0.95 }));
  };

  /** 仅当路段在屏幕上的像素长度 ≥ 该值时才显示路名（随缩放变化），优先保证箭头清晰 */
  var MIN_SEGMENT_PIXELS_FOR_ROAD_NAME = 80;

  M.addRoadNameLabelsFromSteps = function (route_steps, BPoint) {
    if (!M.bmap || !route_steps || !route_steps.length || !BPoint || typeof window.BMap.Label === "undefined") return;
    var roadNameRe = /高速|国道|省道|大道|快速路|环路|线|路$/;
    var maxFontPx = Math.min(12, ROUTE_STROKE_WEIGHT);
    var metersPerPixel = getMetersPerPixel();
    for (var i = 0; i < route_steps.length; i++) {
      var step = route_steps[i];
      var name = (step.road_name || "").trim();
      if (!name || name === "无名路" || name.length > 20 || !roadNameRe.test(name)) continue;
      var path = step.path;
      if (!path || path.length < 2) continue;
      var segBd = [];
      for (var sj = 0; sj < path.length; sj++) segBd.push({ lng: path[sj][1], lat: path[sj][0] });
      var segLenMeters = pathLengthMeters(segBd);
      var segLenPixels = metersPerPixel > 0 ? segLenMeters / metersPerPixel : 0;
      if (segLenPixels < MIN_SEGMENT_PIXELS_FOR_ROAD_NAME) continue;
      var midIdx = Math.floor(path.length / 2);
      var p = path[midIdx];
      if (!p || p[0] == null || p[1] == null) continue;
      var pt = new BPoint(p[1], p[0]);
      var label = new window.BMap.Label(name, { offset: new window.BMap.Size(0, 0), position: pt, enableMassClear: true });
      label.setStyle({
        color: "#1a1a1a",
        fontSize: maxFontPx + "px",
        fontWeight: "bold",
        border: "none",
        background: "none",
        backgroundColor: "rgba(0,0,0,0)",
        padding: "0",
        maxWidth: "none"
      });
      M.bmap.addOverlay(label);
    }
  };

  M.addRoadNameLabels = function (route) {
    if (!M.bmap || !route || typeof route.getNumSteps !== "function") return;
    try {
      var maxFontPx = Math.min(12, ROUTE_STROKE_WEIGHT);
      var metersPerPixel = getMetersPerPixel();
      var n = route.getNumSteps();
      for (var i = 0; i < n; i++) {
        var step = route.getStep && route.getStep(i);
        if (!step) continue;
        var name = (step.getRoadName && step.getRoadName()) || (step.roadName) || "";
        if (!name || name === "无名路" || name.length > 20) continue;
        if (!/高速|国道|省道|大道|快速路|环路|线|路$/.test(name)) continue;
        var path = step.getPath && step.getPath();
        if (!path || path.length < 2) continue;
        var segBd = [];
        for (var pi = 0; pi < path.length; pi++) {
          var pt = path[pi];
          if (!pt) continue;
          var lng = pt.lng != null ? pt.lng : (typeof pt.getLng === "function" ? pt.getLng() : null);
          var lat = pt.lat != null ? pt.lat : (typeof pt.getLat === "function" ? pt.getLat() : null);
          if (lng != null && lat != null) segBd.push({ lng: lng, lat: lat });
        }
        if (segBd.length < 2) continue;
        var segLenMeters = pathLengthMeters(segBd);
        var segLenPixels = metersPerPixel > 0 ? segLenMeters / metersPerPixel : 0;
        if (segLenPixels < MIN_SEGMENT_PIXELS_FOR_ROAD_NAME) continue;
        var mid = path[Math.floor(path.length / 2)];
        if (!mid) continue;
        var label = new window.BMap.Label(name, { offset: new window.BMap.Size(0, 0), position: mid, enableMassClear: true });
        label.setStyle({
          color: "#1a1a1a",
          fontSize: maxFontPx + "px",
          fontWeight: "bold",
          border: "none",
          background: "none",
          backgroundColor: "rgba(0,0,0,0)",
          padding: "0",
          maxWidth: "none"
        });
        M.bmap.addOverlay(label);
      }
    } catch (e) {}
  };

  M.drawRouteFromIndex = function (fromIndex, preserveViewport) {
    if (!M.lastRouteData) return;
    var coords = M.route_coords.slice(fromIndex), addresses = M.route_addresses.slice(fromIndex);
    var types = M.point_types.slice(fromIndex), labels = M.point_labels.slice(fromIndex);
    document.getElementById("routeInfo").textContent = "剩余 " + (addresses.length - 1) + " 站";
    if (coords.length === 0) return;
    M.clearMapOverlays();
    if (!M.bmap) return;
    var NS = M.useBMapGL ? window.BMapGL : window.BMap;
    if (!NS || !NS.Point) return;
    var bdPoints = [];
    for (var i = 0; i < coords.length; i++) {
      var c = coords[i];
      if (!c || c[0] == null || c[1] == null) continue;
      bdPoints.push(new NS.Point(c[1], c[0]));
    }
    if (bdPoints.length === 0) return;

    /* 💡 优先使用后端返回的路线集合，同时在地图上画出所有备选路线 */
    if (fromIndex === 0 && M.route_paths && M.route_paths.length > 0 && !M.useBMapGL) {
      var BPoint = window.BMap && window.BMap.Point;
      if (BPoint) {
        M.addMarkersWithNS(bdPoints, fromIndex, addresses, labels, types, NS);

        for (var i = M.route_paths.length - 1; i >= 0; i--) {
          if (i === M.routeAlternativeIndex) continue;
          var pathArr = M.route_paths[i];
          if (!pathArr || pathArr.length < 2) continue;
          var bdPath = [];
          for (var j = 0; j < pathArr.length; j++) {
            bdPath.push(new BPoint(pathArr[j][1], pathArr[j][0]));
          }
          M.bmap.addOverlay(new window.BMap.Polyline(bdPath, {
            strokeColor: ROUTE_ALTERNATIVE_COLOR,
            strokeWeight: ROUTE_STROKE_WEIGHT - 4,
            strokeOpacity: 0.8
          }));
        }

        var mainPathArr = M.route_paths[M.routeAlternativeIndex] || M.route_paths[0];
        if (mainPathArr && mainPathArr.length >= 2) {
          var mainBdPath = [];
          for (var k = 0; k < mainPathArr.length; k++) {
            mainBdPath.push(new BPoint(mainPathArr[k][1], mainPathArr[k][0]));
          }
          M.addDirectionalPolyline(mainBdPath, ROUTE_GREEN, []);
        }

        if (!preserveViewport && M.bmap.setViewport) M.bmap.setViewport(bdPoints);
        if (M.updateNavPanel) M.updateNavPanel();
        if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();
        if (M.bmap && typeof M.bmap.getZoom === "function") M.lastRedrawZoom = M.bmap.getZoom();
        var hintEl = document.getElementById("restrictionHint");
        if (hintEl) hintEl.style.display = "none";
        return;
      }
    }

    if (bdPoints.length === 1) {
      var statusEl = document.getElementById("routeInfo");
      if (statusEl) statusEl.textContent = "司机位置";
      if (!preserveViewport) {
        M.bmap.setCenter && M.bmap.setCenter(bdPoints[0]);
        M.bmap.setZoom && M.bmap.setZoom(14);
      }
      M.addMarkersWithNS(bdPoints, fromIndex, addresses, labels, types, NS);
      if (M.updateNavPanel) M.updateNavPanel();
      if (M.showRestrictionHintIfNeeded) M.showRestrictionHintIfNeeded();
      if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();
      if (M.bmap && typeof M.bmap.getZoom === "function") M.lastRedrawZoom = M.bmap.getZoom();
      return;
    }
    if (M.useBMapGL && window.BMapGL && window.BMapGL.DrivingRoute) {
      var driving = new window.BMapGL.DrivingRoute(M.bmap, { renderOptions: { map: M.bmap, autoViewport: true } });
      var start = bdPoints[0], end = bdPoints[bdPoints.length - 1];
      var waypoints = bdPoints.length > 2 ? bdPoints.slice(1, -1).slice(0, 10) : [];
      document.getElementById("routeInfo").textContent = "正在规划驾车路线…";
      driving.search(start, end, waypoints.length ? { waypoints: waypoints } : undefined);
      var onDone = function () {
        M.addMarkersWithNS(bdPoints, fromIndex, addresses, labels, types, NS);
        document.getElementById("routeInfo").textContent = "剩余 " + (addresses.length - 1) + " 站";
        if (M.showRestrictionHintIfNeeded) M.showRestrictionHintIfNeeded();
      };
      if (typeof driving.setSearchCompleteCallback === "function") driving.setSearchCompleteCallback(onDone);
      else setTimeout(onDone, 1500);
      return;
    }
    M.addMarkersWithNS(bdPoints, fromIndex, addresses, labels, types, NS);
    if (typeof window.BMap.DrivingRoute === "undefined") {
      M.addDirectionalPolyline(bdPoints, ROUTE_GREEN);
      if (!preserveViewport && M.bmap.setViewport) M.bmap.setViewport(bdPoints);
      if (M.showRestrictionHintIfNeeded) M.showRestrictionHintIfNeeded();
      if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();
      if (M.bmap && typeof M.bmap.getZoom === "function") M.lastRedrawZoom = M.bmap.getZoom();
      return;
    }
    var policyVal = M.getDrivingPolicyValue(M.routePolicyKey);
    var opts = { renderOptions: { map: null }, policy: policyVal };
    M.lastSegmentResults = [];
    var driving = new window.BMap.DrivingRoute(M.bmap, opts);
    var segIndex = 0;
    function updateStatus() { document.getElementById("routeInfo").textContent = "剩余 " + (addresses.length - 1) + " 站"; }
    function searchNextSegment() {
      if (segIndex >= bdPoints.length - 1) {
        if (!preserveViewport && M.bmap.setViewport) M.bmap.setViewport(bdPoints);
        updateStatus();
        if (M.updateNavPanel) M.updateNavPanel();
        if (M.showRestrictionHintIfNeeded) M.showRestrictionHintIfNeeded();
        if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();
        if (M.bmap && typeof M.bmap.getZoom === "function") M.lastRedrawZoom = M.bmap.getZoom();
        return;
      }
      driving.search(bdPoints[segIndex], bdPoints[segIndex + 1]);
    }
    var onSegmentFail = function () {
      M.bmap.addOverlay(new window.BMap.Polyline([bdPoints[segIndex], bdPoints[segIndex + 1]], { strokeColor: ROUTE_GREEN, strokeWeight: ROUTE_STROKE_WEIGHT }));
      segIndex++;
      searchNextSegment();
    };
    if (typeof driving.setSearchCompleteCallback === "function") {
      driving.setSearchCompleteCallback(function () {
        var results = driving.getResults && driving.getResults();
        if (results) {
          M.lastSegmentResults[segIndex] = results;
          var nPlans = M.getNumPlans(results), planIdx = nPlans ? (M.routeAlternativeIndex % nPlans) : 0;
          var plan = results.getPlan && results.getPlan(planIdx);
          if (!plan) plan = results.getPlan && results.getPlan(0);
          if (plan) {
            try {
              var route = plan.getRoute && plan.getRoute(0);
              var path = route && route.getPath && route.getPath();
              if (path && path.length > 0) {
                var lineColor = (M.routeAlternativeIndex === 0 ? ROUTE_GREEN : ROUTE_ALTERNATIVE_COLOR);
                M.addDirectionalPolyline(path, lineColor);
                segIndex++;
                searchNextSegment();
                return;
              }
            } catch (e) {}
          }
        }
        onSegmentFail();
      });
    }
    if (typeof driving.setErrorCallback === "function") driving.setErrorCallback(onSegmentFail);
    document.getElementById("routeInfo").textContent = "正在规划驾车路线…";
    searchNextSegment();
  };

  M.redrawFromStoredSegments = function (preserveViewport) {
    if (!M.bmap || !M.lastRouteData || !M.lastSegmentResults || M.lastSegmentResults.length === 0) return;
    var fromIndex = M.currentStopIndex;
    var coords = M.route_coords.slice(fromIndex), addresses = M.route_addresses.slice(fromIndex);
    var types = M.point_types.slice(fromIndex), labels = M.point_labels.slice(fromIndex);
    var NS = M.useBMapGL ? window.BMapGL : window.BMap;
    if (!NS || !NS.Point) return;
    var bdPoints = [];
    for (var i = 0; i < coords.length; i++) {
      var c = coords[i];
      if (!c || c[0] == null || c[1] == null) continue;
      bdPoints.push(new NS.Point(c[1], c[0]));
    }
    if (bdPoints.length < 2) return;
    M.clearMapOverlays();
    M.addMarkersWithNS(bdPoints, fromIndex, addresses, labels, types, NS);
    for (var i = 0; i < M.lastSegmentResults.length; i++) {
      var res = M.lastSegmentResults[i];
      if (!res) continue;
      var nPlans = M.getNumPlans(res), planIdx = nPlans ? (M.routeAlternativeIndex % nPlans) : 0;
      var plan = res.getPlan && res.getPlan(planIdx);
      if (!plan) plan = res.getPlan && res.getPlan(0);
      if (!plan) continue;
      try {
        var route = plan.getRoute && plan.getRoute(0);
        var path = route && route.getPath && route.getPath();
        if (path && path.length > 0) {
          var lineColor = (M.routeAlternativeIndex === 0 ? ROUTE_GREEN : ROUTE_ALTERNATIVE_COLOR);
          M.addDirectionalPolyline(path, lineColor);
        }
      } catch (e) {}
    }
    if (!preserveViewport && M.bmap.setViewport) M.bmap.setViewport(bdPoints);
    if (M.updateNavPanel) M.updateNavPanel();
    if (M.updateStrategyPanelActive) M.updateStrategyPanelActive();
    if (M.bmap && typeof M.bmap.getZoom === "function") M.lastRedrawZoom = M.bmap.getZoom();
    var name = M.POLICY_NAMES[M.routePolicyKey] || M.routePolicyKey;
    document.getElementById("routeInfo").textContent = "已切换为「" + name + "」路线（浅灰绿）";
    if (M.showRestrictionHintIfNeeded) M.showRestrictionHintIfNeeded();
  };
})();
