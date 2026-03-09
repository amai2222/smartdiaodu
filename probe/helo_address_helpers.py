# -*- coding: utf-8 -*-
"""
哈啰地址设置公共逻辑：地址拆分、出现「请选择预计出发时间」时选择日期时间并点确定。
支持从数据库或环境变量读取目标出发时间，并滚动时间条选择（如明天 8点00分）。
滚轮内「明天/18点/05分」等文案通常不暴露给无障碍，故用「当前时间与目标差值」算拖拽次数，不依赖 exists()。
"""
import os
import re
import time
from datetime import datetime


def split_city_and_detail(full_address):
    """
    从完整地址拆出：城市（仅到「XX市」）+ 详细地址（市后面的部分）。
    例如：江苏省南通市如东县掘港街道荣生豪景花苑 -> ("南通市", "如东县掘港街道荣生豪景花苑")
         上海市浦江镇地铁站 -> ("上海市", "浦江镇地铁站")
    """
    s = (full_address or "").strip()
    if not s:
        return ("", "")
    m = re.search(r"([\u4e00-\u9fff]+市)", s)
    if m:
        city = m.group(1)
        idx = s.find(city) + len(city)
        detail = s[idx:].strip()
        return (city, detail)
    return (s, "")


def _parse_departure_time(s):
    """
    解析目标出发时间字符串，返回 (明天: bool, 时: int, 分: int)。
    支持："08:00"、"明天 08:00"、"明天8点00分"、"8点00分"、"明天 8:00"。
    """
    if not s or not isinstance(s, str):
        return (False, 8, 0)
    s = s.strip()
    tomorrow = "明天" in s
    hour, minute = 8, 0
    # 匹配 8点 或 08点 或 8:00 或 08:00
    m = re.search(r"(\d{1,2})\s*[点:]\s*(\d{1,2})", s)
    if m:
        hour = max(0, min(23, int(m.group(1))))
        minute = max(0, min(59, int(m.group(2))))
    else:
        m = re.search(r"(\d{1,2})\s*:\s*(\d{1,2})", s)
        if m:
            hour = max(0, min(23, int(m.group(1))))
            minute = max(0, min(59, int(m.group(2))))
    return (tomorrow, hour, minute)


def _scroll_picker_to_value(d, target_text, picker_center_x, picker_center_y, swipe_up=True, max_swipes=25, click_after_scroll=True):
    """在时间选择器某一列内上下滑动，直到出现 target_text。click_after_scroll=True 时找到后点击，False 时只停在那一行不点。"""
    h = 280  # 滑动幅度加大，否则滚轮可能不响应
    x1 = picker_center_x
    x2 = picker_center_x
    y1 = picker_center_y - h // 2
    y2 = picker_center_y + h // 2

    def target_visible():
        if d(text=target_text).exists(timeout=0.3):
            return True
        if target_text == "明天" and d(textContains="明天").exists(timeout=0.3):
            return True
        return False

    def try_click():
        if not click_after_scroll:
            return False  # 只滚动不点时不在「检查」阶段返回，交给下面 swipe 后再判
        if d(text=target_text).exists(timeout=0.3):
            try:
                d(text=target_text).click()
                return True
            except Exception:
                pass
        if target_text == "明天" and d(textContains="明天").exists(timeout=0.3):
            try:
                d(textContains="明天").click()
                return True
            except Exception:
                pass
        return False

    for i in range(max_swipes):
        if click_after_scroll and try_click():
            return True
        # 先滑动再检查，避免屏幕别处已有「明天」时没滚动就退出
        if swipe_up:
            d.swipe(x1, y2, x2, y1, duration=0.4)  # 向上滑，稍慢一点让滚轮识别
        else:
            d.swipe(x1, y1, x2, y2, duration=0.4)
        time.sleep(0.35)
        # 只滚动不点时：至少滑过一次后再判断是否已到「明天」
        if not click_after_scroll and target_visible():
            return True
        if click_after_scroll and try_click():
            return True
    return False


def confirm_departure_time_dialog(d, target_time=None):
    """
    若出现「请选择预计出发时间」弹窗：三列选择器为 日期 | 时间(小时) | 分钟。
    顺序必须严格：1 先选日期 → 2 再选小时 → 3 再选分钟 → 4 最后点「确认出发时间」。
    target_time 示例："明天 08:00"、"8点00分"。若为 None 则只点确认（保持当前选择）。
    返回 True 表示处理了弹窗（点了确认），False 表示未发现弹窗。
    """
    time.sleep(0.5)
    if not d(text="请选择预计出发时间").exists(timeout=3) and not d(textContains="预计出发时间").exists(timeout=2):
        return False

    tomorrow, hour, minute = (False, 8, 0)
    if target_time:
        tomorrow, hour, minute = _parse_departure_time(target_time)
        print("  [出发时间] 目标: %s -> 明天=%s, %d点%02d分" % (target_time, tomorrow, hour, minute))

    # 弹窗三列：优先从 dump 取 dayView/hourView/minuteView 中心（与 test_time_date_only 一致，可滑动）
    try:
        w, h = d.window_size()
    except Exception:
        w, h = 1080, 2280
    col_date_x, col_hour_x, col_min_x = int(w * 0.24), int(w * 0.33), int(w * 0.5)
    date_cy = hour_cy = min_cy = picker_y = int(h * 0.55)
    try:
        xml = d.dump_hierarchy()
        for rid, name in [("dayView", "col_date"), ("hourView", "col_hour"), ("minuteView", "col_min")]:
            m = re.search(r'resource-id="com\.jingyao\.easybike:id/%s"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % rid, xml)
            if not m:
                m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*resource-id="com\.jingyao\.easybike:id/%s"' % rid, xml)
            if m:
                x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                if name == "col_date":
                    col_date_x, date_cy = cx, cy
                elif name == "col_hour":
                    col_hour_x, hour_cy = cx, cy
                else:
                    col_min_x, min_cy = cx, cy
    except Exception:
        pass

    # 1) 先选日期：明天在今天的下一行，在 dayView 中心向上拖 1 次即滚一行，不依赖检测「明天」（滚轮可能不暴露该文案）
    if tomorrow:
        row_h = 100
        for _ in range(2):  # 固定拖 2 次，确保从「今天」到「明天」；不循环等 exists("明天")，避免一直翻
            try:
                d.drag(col_date_x, date_cy, col_date_x, date_cy - row_h, duration=0.6)
            except Exception:
                d.swipe(col_date_x, date_cy, col_date_x, date_cy - row_h, duration=0.5)
            time.sleep(0.4)
        print("  [日期列] 已向上拖 2 次，应为「明天」")
        time.sleep(0.35)

    # 2) 小时列：滚轮不暴露「18点」，用「基准时→目标时」算拖拽次数（不依赖 exists）
    row_h = 100
    now = datetime.now()
    # 选「明天」后不少 picker 会重置为 0点0分，否则认为仍是当前时间
    base_hour = 0 if tomorrow else now.hour
    base_minute = 0 if tomorrow else now.minute
    h_diff = (hour - base_hour) % 24
    h_drag_down = h_diff if h_diff <= 12 else 0
    h_drag_up = (24 - h_diff) if h_diff > 12 else 0
    n_hour = h_drag_down or h_drag_up
    for _ in range(n_hour):
        try:
            if h_drag_down:
                d.drag(col_hour_x, hour_cy, col_hour_x, hour_cy + row_h, duration=0.6)
            else:
                d.drag(col_hour_x, hour_cy, col_hour_x, hour_cy - row_h, duration=0.6)
        except Exception:
            d.swipe(col_hour_x, hour_cy, col_hour_x, hour_cy + row_h if h_drag_down else hour_cy - row_h, duration=0.5)
        time.sleep(0.35)
    if n_hour:
        print("  [小时列] 已拖 %d 次 -> 目标 %d点（基准 %d点）" % (n_hour, hour, base_hour))
    time.sleep(0.25)

    # 3) 分钟列：同上，用「基准分→目标分」算拖拽次数
    m_diff = (minute - base_minute) % 60
    m_drag_down = m_diff if m_diff <= 30 else 0
    m_drag_up = (60 - m_diff) if m_diff > 30 else 0
    n_min = m_drag_down or m_drag_up
    for _ in range(n_min):
        try:
            if m_drag_down:
                d.drag(col_min_x, min_cy, col_min_x, min_cy + row_h, duration=0.6)
            else:
                d.drag(col_min_x, min_cy, col_min_x, min_cy - row_h, duration=0.6)
        except Exception:
            d.swipe(col_min_x, min_cy, col_min_x, min_cy + row_h if m_drag_down else min_cy - row_h, duration=0.5)
        time.sleep(0.35)
    if n_min:
        print("  [分钟列] 已拖 %d 次 -> 目标 %02d分（基准 %02d分）" % (n_min, minute, base_minute))

    time.sleep(0.35)

    # 4) 最后必须点「确认出发时间」关闭弹窗，否则会挡住后面的出发地/目的地输入
    # 优先用 resource-id（与 time_picker_dump.xml 一致），再试文案、description
    for attempt, sel in enumerate([
        {"resourceId": "com.jingyao.easybike:id/tvConfirm"},
        {"text": "确认出发时间"},
        {"textContains": "确认出发时间"},
        {"description": "确认出发时间"},
    ]):
        try:
            btn = d(**sel)
            if btn.exists(timeout=1):
                btn.click()
                print("  [已点击「确认出发时间」]")
                time.sleep(0.6)
                return True
        except Exception:
            pass
    return False
