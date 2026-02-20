# 探针端：抓取方案与探针号

哈啰、滴滴等顺风车平台**没有官方 API**，订单数据只能从 App 侧获取。本目录提供 **PC + UIAutomator2**（推荐）与 **手机端 AutoX.js** 两套模板，**不用截图 OCR**。

**风控提醒**：平台会检测「无障碍服务」和「应用列表」，行为过机器化也会封号。**优先用 PC 跑 Python 脚本（UIAutomator2）**，不占手机、不依赖无障碍；若必须用手机跑 AutoX.js，请配合 **HideMyApplist** 隐藏自动化应用，并在脚本里加随机延迟。详见 **docs/探针端风控与隐蔽策略.md**。

---

## 一、为什么不用「截图 + OCR」？

| 问题       | 说明 |
|------------|------|
| **速度**   | 截图 → 预处理 → OCR → 正则，单次 1~2 秒，极品单常在 0.5 秒内被抢光。 |
| **发热**   | 24 小时跑图像识别，手机易发热、卡顿甚至死机。 |
| **脆弱**   | App 改 UI、弹窗、文字截断都会导致识别失败。 |

结论：**不推荐 OCR**。Root 后可直接读界面控件或（进阶）拦截网络，数据更准、更快。

---

## 二、推荐抓取方案（Root 特权）

### 方案 A：PC + UIAutomator2（推荐，不依赖无障碍）

- **技术**：在**电脑**上运行 Python 脚本，手机通过 USB 或网络 ADB 连接，使用 **UIAutomator2** 通过底层 atx-agent 获取界面树并读控件。
- **原理**：不开启手机系统里的「无障碍」，App 无法通过「辅助功能已开启」检测到你；点击/滑动由 PC 经 ADB 下发，更易做拟人化延迟。
- **本目录**：`uiautomator2_capture.py`（抓单）、`uiautomator2_publish_trip.py`（发布/取消行程），已带随机延迟与间隔抖动。
- **前提**：`pip install uiautomator2 requests`，手机开 USB 调试并 `python -m uiautomator2 init`；用 weditor 查大厅/发布页控件并改选择器。

### 方案 A'：手机端 AutoX.js（需隐藏应用 + 拟人化）

- **技术**：在 Root 手机上安装 AutoX.js，用无障碍读控件并点击。
- **风险**：哈啰/滴滴会检测无障碍，易弹窗或封号。若必须用，请用 **LSPosed + HideMyApplist** 对顺风车 App 隐藏 AutoX.js，并在脚本里**每次操作前加 0.5～1.5 秒随机延迟**。
- **本目录**：`autox_capture.js`、`autox_publish_trip.js` 为模板，需自行加随机 sleep 并调选择器。

### 方案 B：网络抓包 / Hook（进阶）

- **技术**：LSPosed + 自定义模块 或 抓包 + 逆向绕过 SSL Pinning。
- **原理**：拦截 App 请求「刷新大厅」的响应 JSON，直接拿到结构化订单（甚至含经纬度）。
- **优点**：比界面还快、数据最全。
- **缺点**：风控与证书绑定对抗难度大，适合有逆向经验的人。

本目录只提供 **方案 A** 的即用模板。

---

## 三、为什么必须用「探针号」？

| 做法     | 风险 |
|----------|------|
| 用**主驾驶大号**在探针机上 24 小时高频刷新 | 容易被判机器行为：限流大厅或封号，主号资产受损。 |
| 用**探针小号**在 Root 机上抓大厅，**大号只在车上接单** | 小号被封无所谓；大号表现像正常人，只在收到 Bark 推送后抢单，安全。 |

**建议**：探针机只登录**小号**（能看顺风车大厅即可，无需认证车主），大号放在日常用车手机（如 iPhone）上，人机分离。

---

## 四、本目录脚本说明

### 1. Python UIAutomator2：`uiautomator2_capture.py`（推荐）

- **运行位置**：**PC**，手机 USB 或 adb over WiFi。
- **特点**：不依赖手机无障碍，风控更小；已带 `human_delay` 与循环间隔抖动。
- **步骤**：安装 uiautomator2、requests，用 weditor 确认大厅控件，改 SELECTOR_* 与 API_BASE、CURRENT_STATE，在 PC 运行脚本。

### 2. Python UIAutomator2：`uiautomator2_publish_trip.py`

- **运行位置**：PC，同上。
- **作用**：轮询大脑 `POST /probe_publish_trip`，拿到建议行程后填表发布；收到 `cancel_current_trip` 时在 App 内取消已发布行程。每次点击前随机延迟。

### 3. AutoX.js：`autox_capture.js`

- **运行位置**：**直接在 Root 安卓机上**运行，无需 PC。
- **适合**：24 小时挂机、家里放一台二手三星专门当探针。
- **步骤**：
  1. 安装 [AutoX.js](https://github.com/kkevsekk1/AutoX)（或 Auto.js），授予无障碍 + 悬浮窗等权限。
  2. 用其「布局分析」或「无障碍」查看顺风车大厅列表页，记下「起点 / 终点 / 价格」对应控件的 `id` 或 `className`+ 层级。
  3. 打开 `autox_capture.js`，修改顶部 `CONFIG.API_BASE` 和 `CONFIG.CURRENT_STATE`，把 `SELECTORS` 改成你实际抓到的选择器。
  4. 前台打开顺风车大厅列表，运行脚本；脚本会循环抓取当前屏订单并 POST 到大脑 `/evaluate_new_order`。

### 2. Python UIAutomator2：`uiautomator2_capture.py`

- **运行位置**：**PC**，手机通过 USB 或 adb over WiFi 连接。
- **适合**：开发调试、用 `weditor` 查控件结构。
- **步骤**：
  1. `pip install uiautomator2 requests`，手机开启 USB 调试，执行 `python -m uiautomator2 init`。
  2. 用 `weditor` 打开顺风车大厅页，确认起点/终点/价格控件的 `resourceId` 或文本特征。
  3. 修改脚本里 `SELECTOR_PICKUP` / `SELECTOR_DELIVERY` / `SELECTOR_PRICE` 和 `API_BASE`、`CURRENT_STATE`。
  4. 在 PC 上运行 `python uiautomator2_capture.py`，保持大厅在前台。

两种脚本都是：**从当前界面提取一条订单 → 组装 `current_state` + `new_order` → POST 到大脑 `POST /evaluate_new_order`**。  
若你后续改为「先写入 Supabase 订单池再由后端统一匹配」，只需把上报地址改为后端的「订单接入」接口即可。

### 4. 自动发布行程：`uiautomator2_publish_trip.py`（推荐）/ `autox_publish_trip.js`

- **用途**：模式2 下从「第一个客人下车点」找顺路单时，部分平台可能要求**先发布行程**才展示匹配订单；探针自动填起点/终点/时间并发布，接单后自动取消已发布行程。
- **Python 版**（`uiautomator2_publish_trip.py`）：在 **PC** 运行，不依赖无障碍，已带拟人化延迟；轮询 `POST /probe_publish_trip`，收到 `cancel_current_trip` 时在 App 内执行取消。
- **AutoX 版**（`autox_publish_trip.js`）：在手机运行时建议配合 **HideMyApplist** 并加随机 sleep。
- **接单后取消**：大脑在用户点「接单」后置位，探针下次轮询拿到 `cancel_current_trip: true`，进入「我的行程/已发布」点取消。需按实际 App 改选择器。
- **是否必须**：取决于平台；若不发布就看不到顺路单再启用。

---

## 五、与后端 / Supabase 的对接方式

- **当前（单司机 / 单状态）**  
  探针脚本里配置好 `CURRENT_STATE`（司机位置 + 已接单起终点），每次抓到一个新单就 POST 到现有 **`/evaluate_new_order`**。大脑用 OR-Tools 算绕路并决定是否 Bark 推送。

- **多司机 + Supabase（你已有表结构）**  
  1. 探针**不再**直接调 `/evaluate_new_order`，改为调用后端新接口，例如 **`POST /order_ingest`**：  
     请求体：`{ "pickup", "delivery", "price" }`（可选带 `order_hash`）。  
  2. 后端把该条写入 **Supabase `order_pool`**（`status=pending_match`），并触发或由定时任务：  
     对每个在线司机从 `driver_state` / `active_trips` 取当前状态，调用原有 PDP 逻辑评估，匹配则更新 `order_pool.assigned_driver_id`、写入/更新 `active_trips`，并给该司机发 Bark。

这样探针端只负责「抓取 + 上报一条订单」，多司机匹配与状态全部在后端和 Supabase 完成。

---

## 六、选择器如何找（必做）

- **AutoX.js**：运行后使用「布局分析」或「悬浮窗 → 查看控件」，点选大厅列表里**一条订单**的起点、终点、价格文字，记下 `id`、`text`、`className`、`depth`。
- **UIAutomator2**：PC 运行 `weditor`，手机同屏打开大厅，在 weditor 里点选对应控件，看 `resourceId`、`text`，把脚本里的 `SELECTOR_*` 改成一致。

不同 App 版本界面可能变化，选择器需随版本微调。
