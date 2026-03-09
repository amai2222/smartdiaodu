/**
 * 探子 · 手机独立运行版（无需连电脑）
 * 运行环境：三星/安卓机 + AutoX.js，授予「无障碍」权限
 *
 * 使用步骤：
 * 1. 在手机上安装 AutoX.js（或 Auto.js）
 * 2. 打开本脚本，修改下方 CONFIG 里的 API_BASE、DRIVER_ID（与大脑/Web 一致）
 * 3. 手动打开哈啰 App，进入「车主」→ 发布行程或点「寻找乘客中」进入订单列表页
 * 4. 在 AutoX.js 里运行本脚本（可后台运行）
 * 5. 脚本会持续读取当前屏幕上的订单（出发、到达、价格），去重后上报大脑
 *
 * 风控：哈啰可能检测无障碍，建议用 LSPosed + HideMyApplist 对哈啰隐藏 AutoX.js，
 *       并在 CONFIG 里把 LOOP_INTERVAL_MS 设为 1200 以上，脚本内已加随机延迟。
 */

"use strict";

const CONFIG = {
  API_BASE: "https://xg.325218.xyz/api",
  LOOP_INTERVAL_MS: 1500,
  DRIVER_ID: "a0000001-0000-4000-8000-000000000001",
  CURRENT_STATE: {
    driver_loc: "",
    pickups: [],
    deliveries: []
  }
};

let lastFingerprint = "";

function extractPrice(raw) {
  if (typeof raw !== "string") return "0";
  const m = String(raw).match(/[\d.]+/);
  return m ? m[0] : "0";
}

function makeFingerprint(pickup, delivery, price) {
  return pickup + "|" + delivery + "|" + price;
}

function extractOneOrder() {
  const pickupNode = textContains("出发").findOne(1500);
  const deliveryNode = textContains("到达").findOne(1500);
  if (!pickupNode || !deliveryNode) return null;
  const pickup = (pickupNode.text() || pickupNode.desc() || "").trim();
  const delivery = (deliveryNode.text() || deliveryNode.desc() || "").trim();
  if (!pickup || !delivery) return null;
  let price = "0";
  const priceNodes = textContains("元").find();
  if (priceNodes && priceNodes.length > 0) {
    for (let i = 0; i < priceNodes.length; i++) {
      const raw = (priceNodes[i].text() || priceNodes[i].desc() || "").trim();
      if (raw && /\d/.test(raw)) {
        price = extractPrice(raw);
        break;
      }
    }
  }
  return { pickup: pickup, delivery: delivery, price: price };
}

function reportToBrain(order) {
  const url = CONFIG.API_BASE.replace(/\/$/, "") + "/evaluate_new_order";
  const body = {
    current_state: CONFIG.CURRENT_STATE,
    new_order: order
  };
  if (CONFIG.DRIVER_ID && String(CONFIG.DRIVER_ID).trim()) {
    body.driver_id = String(CONFIG.DRIVER_ID).trim();
  }
  try {
    const res = http.postJson(url, body, { timeout: 8000 });
    if (res && res.statusCode === 200) {
      const data = res.body ? (typeof res.body === "string" ? JSON.parse(res.body) : res.body) : {};
      log("大脑: " + (data.status || "") + (data.reason ? " " + data.reason : ""));
      return data;
    }
    log("请求失败: " + (res ? res.statusCode : ""));
  } catch (e) {
    log("上报异常: " + e);
  }
  return null;
}

function mainLoop() {
  log("探子(手机版)已启动，请保持哈啰订单列表在前台");
  log("API: " + CONFIG.API_BASE + " 司机: " + (CONFIG.DRIVER_ID || "未指定"));
  while (true) {
    const order = extractOneOrder();
    if (order) {
      const fp = makeFingerprint(order.pickup, order.delivery, order.price);
      if (fp !== lastFingerprint) {
        lastFingerprint = fp;
        log("抓取: " + order.pickup + " -> " + order.delivery + " " + order.price + "元");
        sleep(300 + Math.random() * 500);
        reportToBrain(order);
      }
    }
    sleep(CONFIG.LOOP_INTERVAL_MS + Math.random() * 400);
  }
}

mainLoop();
