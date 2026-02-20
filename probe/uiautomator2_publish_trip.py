# -*- coding: utf-8 -*-
"""
探针：根据大脑建议行程在顺风车 App 内发布行程；接单后自动取消已发布行程。
运行环境：PC + UIAutomator2，手机 USB/网络 ADB，不依赖手机端无障碍，降低风控。
拟人化：每次点击前 human_delay；发布/取消之间随机停顿。见 docs/探针端风控与隐蔽策略.md
"""

import os
import random
import sys
import time
from typing import Any, Optional

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

API_BASE = "https://api.yourdomain.com"
POLL_INTERVAL_SEC = 60
CURRENT_STATE = {
    "driver_loc": "如东县委党校",
    "pickups": ["如东县掘港镇荣生豪景花苑2号楼"],
    "deliveries": ["上海市外滩"],
}


def get_publish_trip() -> Optional[dict]:
    url = f"{API_BASE.rstrip('/')}/probe_publish_trip"
    try:
        r = requests.post(url, json={"current_state": CURRENT_STATE}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("请求失败:", e)
    return None


def cancel_current_trip_in_app(d: u2.Device) -> None:
    """进入我的行程/已发布 → 点取消 → 确认。选择器需按实际 App 修改。"""
    human_delay(0.8, 1.5)
    if d(text="我的行程").exists(timeout=2):
        d(text="我的行程").click()
    elif d(text="已发布").exists(timeout=2):
        d(text="已发布").click()
    else:
        print("未找到 我的行程/已发布 入口，请修改选择器")
        return
    human_delay(1.0, 2.0)
    if d(text="取消").exists(timeout=2):
        d(text="取消").click()
    elif d(text="取消行程").exists(timeout=2):
        d(text="取消行程").click()
    else:
        print("未找到 取消 按钮")
        return
    human_delay(0.5, 1.0)
    if d(text="确定").exists(timeout=1.5):
        d(text="确定").click()
    elif d(text="确认取消").exists(timeout=1.5):
        d(text="确认取消").click()
    print("已执行取消行程")
    time.sleep(jitter_interval(2.0, 1.0))


def fill_and_publish(d: u2.Device, origin: str, dest: str, depart_time: str) -> bool:
    """填起点、终点、时间并点发布。选择器需按实际 App 修改。"""
    human_delay(0.5, 1.2)
    et = d(className="android.widget.EditText")
    if et.count >= 2:
        et[0].set_text(origin)
        human_delay(0.3, 0.7)
        et[1].set_text(dest)
    human_delay(0.4, 0.9)
    if depart_time and d(textContains="出发").exists(timeout=1):
        d(textContains="出发").click()
        human_delay(0.5, 1.0)
        if d(text=depart_time).exists(timeout=2):
            d(text=depart_time).click()
    human_delay(0.6, 1.2)
    if d(text="发布").exists(timeout=2):
        d(text="发布").click()
        return True
    return False


def main():
    d = u2.connect()
    print("探针·发布/取消行程 已启动（PC+UIAutomator2，拟人化延迟）")
    print("每约", POLL_INTERVAL_SEC, "秒轮询；接单后将自动取消已发布行程\n")
    while True:
        trip = get_publish_trip()
        if not trip:
            time.sleep(jitter_interval(POLL_INTERVAL_SEC))
            continue
        if trip.get("cancel_current_trip"):
            cancel_current_trip_in_app(d)
            time.sleep(jitter_interval(3.0, 2.0))
            continue
        origin = trip.get("origin")
        dest = trip.get("destination")
        if origin and dest:
            print("建议发布:", origin, "->", dest, trip.get("depart_time", ""))
            fill_and_publish(d, origin, dest, trip.get("depart_time") or "")
        time.sleep(jitter_interval(POLL_INTERVAL_SEC))


if __name__ == "__main__":
    main()
