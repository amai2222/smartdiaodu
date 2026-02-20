# -*- coding: utf-8 -*-
"""
探针拟人化：随机延迟与间隔，降低行为学风控风险。
供 uiautomator2_capture / uiautomator2_publish_trip 等脚本引用。
"""

import random
import time


def human_delay(min_sec: float = 0.5, max_sec: float = 1.5) -> None:
    """每次点击/操作前调用，随机等待，模拟人类反应时间。"""
    time.sleep(random.uniform(min_sec, max_sec))


def jitter_interval(base_sec: float, jitter_sec: float = 0.3) -> float:
    """在基础间隔上加减抖动，避免固定周期。"""
    return max(0.5, base_sec + random.uniform(-jitter_sec, jitter_sec))
