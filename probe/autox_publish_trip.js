/**
 * 探针：根据大脑建议行程在 App 内发布行程；接单后自动取消已发布行程。
 * 用途：模式2 下平台可能要求先发布行程才展示顺路单；接单后探针自动取消该行程。
 *
 * 【风控】本脚本依赖无障碍，易被平台检测。建议优先用 PC 跑 uiautomator2_publish_trip.py。
 * 若必须用本脚本：LSPosed+HideMyApplist 隐藏 AutoX.js，并在每次点击前加随机 delay（如 0.5～1.5 秒）。
 * 详见 docs/探针端风控与隐蔽策略.md
 *
 * 使用前：配置 API_BASE、CURRENT_STATE；用布局分析改 SELECTORS、CANCEL_SELECTORS。
 */

"ui";

const CONFIG = {
  API_BASE: "https://api.yourdomain.com",
  POLL_INTERVAL_MS: 60000,
  CURRENT_STATE: {
    driver_loc: "如东县委党校",
    pickups: ["如东县掘港镇荣生豪景花苑2号楼"],
    deliveries: ["上海市外滩"]
  }
};

function humanDelay(minMs, maxMs) {
  if (minMs == null) minMs = 500;
  if (maxMs == null) maxMs = 1500;
  sleep(minMs + Math.random() * (maxMs - minMs));
}

function getPublishTrip() {
  var base = CONFIG.API_BASE.replace(/\/$/, "");
  var res = http.postJson(base + "/probe_publish_trip", { current_state: CONFIG.CURRENT_STATE }, { timeout: 8000 });
  if (res && res.statusCode === 200) {
    var body = res.body;
    if (typeof body === "string") body = JSON.parse(body);
    return body;
  }
  return null;
}

// 根据哈啰/滴滴「发布行程」页实际控件修改（起点/终点多为两个 EditText，取第 1、2 个）
var SELECTORS = {
  ORIGIN: function () { var arr = className("EditText").find(); return arr.length >= 1 ? arr[0] : null; },
  DEST: function () { var arr = className("EditText").find(); return arr.length >= 2 ? arr[1] : null; },
  TIME: function () { return textContains("出发").findOne(2000); },
  PUBLISH_BTN: function () { return text("发布").findOne(2000); }
};

// 取消已发布行程：进入「我的行程」/「已发布」页，找到当前行程的「取消」并点击
var CANCEL_SELECTORS = {
  MY_TRIP_OR_PUBLISHED: function () { return text("我的行程").findOne(2000) || text("已发布").findOne(2000); },
  CANCEL_BTN: function () { return text("取消").findOne(2000) || text("取消行程").findOne(2000); },
  CONFIRM_CANCEL: function () { return text("确定").findOne(1500) || text("确认取消").findOne(1500); }
};

function cancelCurrentTripInApp() {
  log("收到接单信号，执行取消探针号已发布行程");
  humanDelay(800, 1500);
  var entry = CANCEL_SELECTORS.MY_TRIP_OR_PUBLISHED();
  if (entry) { entry.click(); humanDelay(1000, 2000); }
  var cancelBtn = CANCEL_SELECTORS.CANCEL_BTN();
  if (cancelBtn) {
    cancelBtn.click();
    humanDelay(500, 1000);
    var confirm = CANCEL_SELECTORS.CONFIRM_CANCEL();
    if (confirm) { confirm.click(); }
    log("已点击取消");
  } else {
    log("未找到取消按钮，请检查 CANCEL_SELECTORS");
  }
}

function fillAndPublish(origin, dest, departTime) {
  humanDelay(500, 1200);
  var o = SELECTORS.ORIGIN();
  if (o) { o.setText(origin); humanDelay(300, 700); }
  var d = SELECTORS.DEST();
  if (d) { d.setText(dest); humanDelay(400, 900); }
  var t = SELECTORS.TIME();
  if (t && departTime) { t.click(); humanDelay(500, 1000); text(departTime).findOne(2000).click(); }
  humanDelay(600, 1200);
  var btn = SELECTORS.PUBLISH_BTN();
  if (btn) { btn.click(); return true; }
  return false;
}

function main() {
  log("探针·发布行程 已启动，每 " + (CONFIG.POLL_INTERVAL_MS / 1000) + " 秒拉取；接单后将自动取消已发布行程");
  while (true) {
    var trip = getPublishTrip();
    if (!trip) { sleep(CONFIG.POLL_INTERVAL_MS); continue; }
    if (trip.cancel_current_trip) {
      cancelCurrentTripInApp();
      sleep(2000);
      continue;
    }
    if (trip.origin && trip.destination) {
      log("建议发布: " + trip.origin + " -> " + trip.destination + " " + (trip.depart_time || ""));
      fillAndPublish(trip.origin, trip.destination, trip.depart_time || "");
    }
    sleep(CONFIG.POLL_INTERVAL_MS);
  }
}

main();
