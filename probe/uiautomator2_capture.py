# -*- coding: utf-8 -*-
"""
顺风车大厅 · 探针抓取脚本 (Python + UIAutomator2)
运行环境：PC 上运行，手机 USB 连接并开启 USB 调试；或 adb over WiFi
安装：pip install uiautomator2 requests
原理：通过底层 ADB/atx-agent 获取界面树并读控件，不依赖手机端「无障碍」，不易被 App 检测
使用前：用 weditor 或 d.app_hierarchy() 查看顺风车大厅列表页的真实控件结构，改掉下面选择器
风控：已加拟人化随机延迟，见 docs/探针端风控与隐蔽策略.md
"""

import os
import random
import re
import hashlib
import sys
import time
from typing import Optional

# 保证同目录 common_human 可被导入（无论从何处运行）
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
try:
    from common_human import human_delay, jitter_interval
except ImportError:
    def human_delay(a=0.5, b=1.5):
        time.sleep(random.uniform(a, b))
    def jitter_interval(base, jitter=0.3):
        return max(0.5, base + random.uniform(-jitter, jitter))

import requests
import uiautomator2 as u2

# --------------------------------------------
# 配置
# --------------------------------------------
API_BASE = "https://api.yourdomain.com"  # 结尾不要 /
LOOP_INTERVAL_SEC = 1.2
# 当前司机状态（若后端从 Supabase 按 driver_id 读可留空，由后端补全）
CURRENT_STATE = {
    "driver_loc": "如东县委党校",
    "pickups": ["如东县掘港镇荣生豪景花苑2号楼"],
    "deliveries": ["上海市外滩"],
}

# 选择器：需根据哈啰/滴滴实际界面用 weditor 或 hierarchy 确认后修改
# 示例为按 text/description 匹配，实际建议用 resourceId
SELECTOR_PICKUP = {"textContains": "出发"}   # 或 {"resourceId": "com.xxx:id/tv_pickup"}
SELECTOR_DELIVERY = {"textContains": "到达"}  # 或 {"resourceId": "com.xxx:id/tv_delivery"}
SELECTOR_PRICE = {"textMatches": r"\d+\.?\d*元?"}  # 或 {"resourceId": "com.xxx:id/tv_price"}


def extract_price(raw: str) -> str:
    if not raw:
        return "0"
    m = re.search(r"[\d.]+", raw)
    return m.group(0) if m else "0"


def extract_one_order(d: u2.Device) -> Optional[dict]:
    """从当前屏幕提取一条订单：起点、终点、价格。无则返回 None。"""
    try:
        # 方式一：按文本/id 找控件（需根据实际 app 改）
        pickup_el = d(**SELECTOR_PICKUP)
        if not pickup_el.exists(timeout=1):
            return None
        pickup = (pickup_el.get_text() or "").strip()
        delivery_el = d(**SELECTOR_DELIVERY)
        if not delivery_el.exists(timeout=1):
            return None
        delivery = (delivery_el.get_text() or "").strip()
        price_el = d(**SELECTOR_PRICE)
        price_raw = (price_el.get_text() or "").strip() if price_el.exists(timeout=1) else ""
        price = extract_price(price_raw)
        if not pickup or not delivery:
            return None
        return {"pickup": pickup, "delivery": delivery, "price": price}
    except Exception as e:
        print("提取异常:", e)
        return None


def report_to_brain(order: dict) -> dict | None:
    """POST 到大脑 /evaluate_new_order。"""
    url = f"{API_BASE.rstrip('/')}/evaluate_new_order"
    payload = {
        "current_state": CURRENT_STATE,
        "new_order": order,
    }
    try:
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            data = r.json()
            print("大脑返回:", data.get("status"), data.get("reason", ""))
            return data
        print("请求失败:", r.status_code, r.text[:200])
    except Exception as e:
        print("上报异常:", e)
    return None


def main():
    # 连接设备：USB 默认 127.0.0.1:7912（atx-agent）；或 "192.168.x.x:5555"
    d = u2.connect()
    print("设备已连接，请确保顺风车大厅列表页在前台")
    print("每", LOOP_INTERVAL_SEC, "秒抓取一次，Ctrl+C 退出\n")
    last_fingerprint = None
    while True:
        order = extract_one_order(d)
        if order:
            fp = hashlib.md5(
                f"{order['pickup']}_{order['delivery']}_{order['price']}".encode()
            ).hexdigest()
            if fp != last_fingerprint:  # 简单去重，避免同一屏重复上报
                last_fingerprint = fp
                human_delay(0.3, 0.8)  # 拟人：不立刻上报
                print("抓取:", order["pickup"], "->", order["delivery"], order["price"], "元")
                report_to_brain(order)
        time.sleep(jitter_interval(LOOP_INTERVAL_SEC))


if __name__ == "__main__":
    main()
