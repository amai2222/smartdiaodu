/**
 * 顺风车大厅 · 探针抓取脚本 (AutoX.js)
 * 运行环境：Root 过的安卓机，安装 AutoX.js，登录探针小号后在前台打开顺风车大厅列表页
 * 原理：通过 UI 控件节点直接读取文本，毫秒级提取，无需截图/OCR
 *
 * 【风控】哈啰/滴滴会检测「无障碍服务」，用本脚本有封号风险。建议优先用 PC 跑
 * uiautomator2_capture.py（不依赖无障碍）。若必须用本脚本：请用 LSPosed+HideMyApplist
 * 对顺风车 App 隐藏 AutoX.js，并在每次上报前加 random 延迟（如 sleep(500+random(1000))）。
 * 详见 docs/探针端风控与隐蔽策略.md
 *
 * 使用前必做：
 * 1. 用 AutoX.js 的「布局分析」查看当前大厅列表页的控件 id/text/className
 * 2. 把下面 SELECTORS 里占位符改成你实际抓到的选择器
 * 3. 配置 API 地址和当前司机状态
 */

"ui";

const CONFIG = {
  // 大脑 API 基础地址（结尾不要 /）
  API_BASE: "https://api.yourdomain.com",
  // 单次抓取间隔（毫秒），建议 800~2000，太频繁容易被风控
  LOOP_INTERVAL_MS: 1200,
  // 当前司机状态（用于 /evaluate_new_order）。若后端按 driver_id 从 Supabase 读可留空，由后端补全
  CURRENT_STATE: {
    driver_loc: "如东县委党校",
    pickups: ["如东县掘港镇荣生豪景花苑2号楼"],
    deliveries: ["上海市外滩"]
  }
};

// --------------------------------------------
// 选择器：必须根据哈啰/滴滴实际界面修改
// 用 AutoX.js 布局分析或 console 打印 ui hierarchy 确认
// --------------------------------------------
const SELECTORS = {
  // 列表项容器（通常大厅是 RecyclerView，每一项是包含 起点/终点/价格 的节点）
  LIST_ITEM: () => className("android.widget.LinearLayout").depth(10).findOne(2000),
  // 起点文本控件（示例：id("tv_pickup") 或 textContains("出发").parent().findOne(className("TextView"))）
  PICKUP: (item) => item ? item.findOne(className("TextView").depth(12)) : null,
  // 终点（同上，按实际层级改）
  DELIVERY: (item) => item ? item.findOne(className("TextView").depth(13)) : null,
  // 价格（可能带「元」字，需正则提取数字）
  PRICE: (item) => item ? item.findOne(className("TextView").depth(14)) : null
};

// 若你已确认真实 id，可改为更稳的写法，例如：
// const SELECTORS = {
//   PICKUP:   () => id("tv_pickup_address").findOne(1500),
//   DELIVERY: () => id("tv_delivery_address").findOne(1500),
//   PRICE:    () => id("tv_price").findOne(1500),
// };

function extractPriceText(raw) {
  if (typeof raw !== "string") return "";
  const m = raw.match(/[\d.]+/);
  return m ? m[0] : raw.replace(/[^\d.]/g, "");
}

function extractOneOrder() {
  const item = SELECTORS.LIST_ITEM();
  if (!item) return null;
  const pickupNode = SELECTORS.PICKUP(item);
  const deliveryNode = SELECTORS.DELIVERY(item);
  const priceNode = SELECTORS.PRICE(item);
  const pickup = pickupNode ? (pickupNode.text() || pickupNode.desc() || "").trim() : "";
  const delivery = deliveryNode ? (deliveryNode.text() || deliveryNode.desc() || "").trim() : "";
  const priceRaw = priceNode ? (priceNode.text() || priceNode.desc() || "").trim() : "";
  const price = extractPriceText(priceRaw);
  if (!pickup || !delivery) return null;
  return { pickup, delivery, price: price || "0" };
}

function reportToBrain(order) {
  const url = CONFIG.API_BASE + "/evaluate_new_order";
  const body = {
    current_state: CONFIG.CURRENT_STATE,
    new_order: order
  };
  try {
    const res = http.postJson(url, body, { timeout: 8000 });
    if (res && res.statusCode === 200) {
      const data = res.body ? (typeof res.body === "string" ? JSON.parse(res.body) : res.body) : {};
      log("大脑返回: " + data.status + (data.reason ? " " + data.reason : ""));
      return data;
    }
    log("请求失败: " + (res ? res.statusCode : "null"));
  } catch (e) {
    log("上报异常: " + e);
  }
  return null;
}

function mainLoop() {
  log("探针已启动，每 " + CONFIG.LOOP_INTERVAL_MS + " ms 抓取一次，请保持顺风车大厅在前台");
  while (true) {
    const order = extractOneOrder();
    if (order) {
      log("抓取: " + order.pickup + " -> " + order.delivery + " " + order.price + "元");
      reportToBrain(order);
    }
    sleep(CONFIG.LOOP_INTERVAL_MS);
  }
}

// 无 UI 后台运行入口（推荐 24 小时挂机）
if (typeof engines !== "undefined") {
  mainLoop();
} else {
  mainLoop();
}
