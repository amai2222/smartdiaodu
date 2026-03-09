# -*- coding: utf-8 -*-
"""
顺风车大厅 · 探针抓取脚本 (Python + UIAutomator2)
运行环境：PC 上运行，手机 USB 连接并开启 USB 调试；或 adb over WiFi
安装：pip install uiautomator2 requests
原理：通过底层 ADB/atx-agent 获取界面树并读控件，不依赖手机端「无障碍」，不易被 App 检测
使用前：用 weditor 或 d.app_hierarchy() 查看顺风车大厅列表页的真实控件结构，改掉下面选择器
风控：已加拟人化随机延迟，见 docs/探针端风控与隐蔽策略.md
"""

import json
import os
import random
import re
import hashlib
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# 保证同目录 common_human 可被导入（无论从何处运行）
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
# 从项目根目录加载 .env（与大脑一致，便于配置 SUPABASE_*、TANZI_DRIVER_ID 等）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(_script_dir), ".env"))
except ImportError:
    pass
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
# 配置（可由环境变量覆盖，与 web/config.js / app_config 保持一致）
# --------------------------------------------
API_BASE = os.environ.get("TANZI_API_BASE", "").strip() or "https://xg.325218.xyz/api"
LOOP_INTERVAL_SEC = float(os.environ.get("TANZI_LOOP_INTERVAL", "1.2") or "1.2")
DRIVER_ID = os.environ.get("TANZI_DRIVER_ID", "").strip() or "a0000001-0000-4000-8000-000000000001"

# 当前司机状态：可由环境变量 TANZI_CURRENT_STATE 覆盖（JSON 字符串，需含 driver_loc, pickups, deliveries）
_default_state = {
    "driver_loc": "如东县委党校",
    "pickups": ["如东县掘港镇荣生豪景花苑2号楼"],
    "deliveries": ["上海市外滩"],
}
_current_state_env = os.environ.get("TANZI_CURRENT_STATE", "").strip()
if _current_state_env:
    try:
        CURRENT_STATE = json.loads(_current_state_env)
        if "driver_loc" not in CURRENT_STATE:
            CURRENT_STATE["driver_loc"] = _default_state["driver_loc"]
        if "pickups" not in CURRENT_STATE:
            CURRENT_STATE["pickups"] = _default_state["pickups"]
        if "deliveries" not in CURRENT_STATE:
            CURRENT_STATE["deliveries"] = _default_state["deliveries"]
    except json.JSONDecodeError:
        CURRENT_STATE = _default_state.copy()
else:
    CURRENT_STATE = _default_state.copy()

# 选择器：需根据哈啰/滴滴实际界面用 weditor 或 hierarchy 确认后修改（单应用时使用）
SELECTOR_PICKUP = {"textContains": "出发"}
SELECTOR_DELIVERY = {"textContains": "到达"}
SELECTOR_PRICE = {"textMatches": r"\d+\.?\d*元?"}

# --------------------------------------------
# 探子当前仅用哈啰；多应用时可在此追加（如滴滴），并用 TANZI_USE_APP_ROTATION=1 开启轮流
# 每项：name=显示名, package=包名, selectors=起点/终点/价格选择器, stay_cycles=连续抓取轮数
# --------------------------------------------
APP_ROTATION = [
    {
        "name": "哈啰",
        "package": "com.jingyao.easybike",
        "selectors": {
            "pickup": {"textContains": "出发"},
            "delivery": {"textContains": "到达"},
            "price": {"textMatches": r"\d+\.?\d*元?"},
        },
        "stay_cycles": 5,
    },
]
# 是否启用应用切换：默认关闭，仅从当前前台抓取（请保持哈啰订单列表在前台）；TANZI_USE_APP_ROTATION=1 时才切到 APP_ROTATION 中的 app
_use_rot = os.environ.get("TANZI_USE_APP_ROTATION", "").strip().lower()
USE_APP_ROTATION = _use_rot in ("1", "true", "yes") and len(APP_ROTATION) > 0

# 切到下一个 app 前的等待（给界面加载时间），秒
APP_SWITCH_WAIT = (2.0, 4.0)

# 设备连接重试
CONNECT_RETRIES = 3
CONNECT_RETRY_DELAY = 5


def extract_price(raw: str) -> str:
    if not raw:
        return "0"
    m = re.search(r"[\d.]+", raw)
    return m.group(0) if m else "0"


def extract_one_order(d: u2.Device, selectors: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    """从当前屏幕提取一条订单：起点、终点、价格。无则返回 None。selectors 为 None 时用全局选择器。"""
    sel = selectors or {
        "pickup": SELECTOR_PICKUP,
        "delivery": SELECTOR_DELIVERY,
        "price": SELECTOR_PRICE,
    }
    try:
        pickup_el = d(**sel["pickup"])
        if not pickup_el.exists(timeout=1):
            return None
        pickup = (pickup_el.get_text() or "").strip()
        delivery_el = d(**sel["delivery"])
        if not delivery_el.exists(timeout=1):
            return None
        delivery = (delivery_el.get_text() or "").strip()
        price_el = d(**sel["price"])
        price_raw = (price_el.get_text() or "").strip() if price_el.exists(timeout=1) else ""
        price = extract_price(price_raw)
        if not pickup or not delivery:
            return None
        return {"pickup": pickup, "delivery": delivery, "price": price}
    except Exception as e:
        print("提取异常:", e)
        return None


def switch_to_app(d: u2.Device, package: str) -> None:
    """把指定包名的 app 切到前台并等待界面加载。"""
    try:
        d.app_start(package)
        time.sleep(random.uniform(*APP_SWITCH_WAIT))
    except Exception as e:
        print("切应用异常 (%s): %s" % (package, e))


def report_to_brain(order: dict) -> Optional[dict]:
    """POST 到大脑 /evaluate_new_order。带 driver_id 时后端按该司机设置决定是否推送。"""
    url = f"{API_BASE.rstrip('/')}/evaluate_new_order"
    payload = {
        "current_state": CURRENT_STATE,
        "new_order": order,
    }
    if DRIVER_ID and str(DRIVER_ID).strip():
        payload["driver_id"] = str(DRIVER_ID).strip()
    try:
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "")
            reason = (data.get("reason") or "").strip()
            if status == "matched":
                print("大脑返回: 顺路单，已推送。", data.get("detour_minutes"), "分钟绕路")
            elif status == "ignored":
                print("大脑返回: 忽略。", reason or "(防骚扰/模式1/暂停等)")
            else:
                print("大脑返回:", status, reason)
            return data
        print("请求失败:", r.status_code, (r.text or "")[:200])
    except requests.exceptions.RequestException as e:
        print("上报异常:", e)
    return None


def fetch_driver_mode() -> Optional[str]:
    """获取当前司机调度模式，用于启动时展示。"""
    url = f"{API_BASE.rstrip('/')}/driver_mode"
    try:
        params = {}
        if DRIVER_ID and str(DRIVER_ID).strip():
            params["driver_id"] = str(DRIVER_ID).strip()
        r = requests.get(url, params=params or None, timeout=5)
        if r.status_code == 200:
            return (r.json() or {}).get("mode")
    except Exception:
        pass
    return None


def connect_device():
    """连接 U2 设备，失败时重试。"""
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            d = u2.connect()
            return d
        except Exception as e:
            print("设备连接失败 (尝试 %d/%d): %s" % (attempt, CONNECT_RETRIES, e))
            if attempt < CONNECT_RETRIES:
                time.sleep(CONNECT_RETRY_DELAY)
    return None


def _run_one_capture_cycle(
    d: u2.Device,
    last_fingerprint: Optional[str],
    selectors: Optional[Dict[str, Any]] = None,
    app_name: str = "",
) -> Tuple[Optional[str], bool]:
    """执行一轮抓单：抓一条、去重、上报。返回 (新 last_fingerprint, 是否发生上报)。"""
    order = extract_one_order(d, selectors)
    if not order:
        return last_fingerprint, False
    fp = hashlib.md5(
        f"{order['pickup']}_{order['delivery']}_{order['price']}".encode()
    ).hexdigest()
    if fp == last_fingerprint:
        return last_fingerprint, False
    human_delay(0.3, 0.8)
    tag = (" [%s]" % app_name) if app_name else ""
    print("抓取%s: %s -> %s %s 元" % (tag, order["pickup"], order["delivery"], order["price"]))
    report_to_brain(order)
    return fp, True


def main():
    use_rotation = USE_APP_ROTATION and (APP_ROTATION or [])
    print("=" * 50)
    print("  探子脚本已启动，开始扫描顺风车大厅")
    print("=" * 50)
    print("  API: %s" % API_BASE)
    print("  司机: %s" % (DRIVER_ID or "(未指定)"))
    print("  当前状态: 位置=%s, 已接 %d 单" % (CURRENT_STATE.get("driver_loc", ""), len(CURRENT_STATE.get("pickups") or [])))
    mode = fetch_driver_mode()
    if mode:
        print("  当前模式: %s" % mode)
    if use_rotation:
        names = [a["name"] for a in APP_ROTATION]
        print("  多应用轮流: %s（每应用 %s 轮后切换）" % (" + ".join(names), " / ".join(str(a["stay_cycles"]) for a in APP_ROTATION)))
    else:
        print("  仅哈啰：从当前前台抓取，每 %.1f 秒一次（请保持哈啰订单列表在前台）" % LOOP_INTERVAL_SEC)
    print("  Ctrl+C 退出")
    print("=" * 50 + "\n")

    d = connect_device()
    if not d:
        print("无法连接设备，请检查 USB/ADB 与 atx-agent，退出。")
        sys.exit(1)
    if use_rotation:
        print("设备已连接，将切到哈啰大厅抓单。\n")
    else:
        print("设备已连接，仅从当前前台抓取，请保持哈啰订单列表在前台。\n")

    last_fingerprint: Optional[str] = None
    app_index = 0

    while True:
        try:
            if use_rotation:
                app = APP_ROTATION[app_index]
                switch_to_app(d, app["package"])
                for _ in range(app["stay_cycles"]):
                    last_fingerprint, _ = _run_one_capture_cycle(
                        d, last_fingerprint, app["selectors"], app["name"]
                    )
                    time.sleep(jitter_interval(LOOP_INTERVAL_SEC))
                app_index = (app_index + 1) % len(APP_ROTATION)
            else:
                last_fingerprint, _ = _run_one_capture_cycle(d, last_fingerprint, None, "")
                time.sleep(jitter_interval(LOOP_INTERVAL_SEC))
        except Exception as e:
            err_str = str(e).lower()
            if "connection" in err_str or "device" in err_str or "adb" in err_str:
                print("设备异常，尝试重连...", e)
                time.sleep(CONNECT_RETRY_DELAY)
                d = connect_device()
                if not d:
                    print("重连失败，退出。")
                    sys.exit(1)
                print("已重新连接设备。")
            else:
                print("本轮异常:", e)


if __name__ == "__main__":
    main()
