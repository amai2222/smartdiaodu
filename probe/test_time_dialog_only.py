# -*- coding: utf-8 -*-
"""
测试修改出发时间：先点击车主页「★ 出发时间 今天11:35」(clStartTime) 弹出时间选择框，
再在弹窗内选择目标时间并点「确认出发时间」。
"""
import os
import subprocess
import sys
import time

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(_script_dir), ".env"))
except ImportError:
    pass

try:
    import uiautomator2 as u2
except ImportError:
    print("请安装: pip install uiautomator2")
    sys.exit(1)

from helo_address_helpers import confirm_departure_time_dialog

DEVICE = os.environ.get("TANZI_DEVICE", "").strip()


def adb(*args):
    cmd = ["adb"] + (["-s", DEVICE] if DEVICE else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


HELO_PKG = "com.jingyao.easybike"


def main():
    target = os.environ.get("TANZI_DRIVER_DEPART_TIME", "明天 08:00")
    print("目标出发时间:", target)
    d = u2.connect()

    # 0) 窗口监测：确保当前是哈啰 app
    pkg = (d.app_current() or {}).get("package", "")
    if pkg != HELO_PKG:
        print("[监测] 当前不是哈啰，正在启动哈啰…")
        adb("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", HELO_PKG)
        for _ in range(20):
            time.sleep(1)
            pkg = (d.app_current() or {}).get("package", "")
            if pkg == HELO_PKG:
                print("[监测] 已进入哈啰。")
                time.sleep(2)
                break
        else:
            print("[监测] 未能进入哈啰，请手动打开哈啰后重试。")
            return 1

    # 1) 确保在「车主」标签里（有出发时间行即表示在车主页）
    for attempt in range(2):
        if d(resourceId="com.jingyao.easybike:id/clStartTime").exists(timeout=3):
            break
        if d(resourceId="com.jingyao.easybike:id/clStartAddress").exists(timeout=2):
            break
        if d(text="车主").exists(timeout=3):
            d(text="车主").click()
            print("[监测] 已点击「车主」标签，进入车主页。")
            time.sleep(3)
        elif d(textContains="车主").exists(timeout=2):
            d(textContains="车主").click()
            time.sleep(3)
        else:
            time.sleep(2)
    if not d(resourceId="com.jingyao.easybike:id/clStartTime").exists(timeout=5):
        print("[监测] 未在车主页（未找到出发时间行），请手动切到哈啰「车主」标签后重试。")
        return 1
    print("[监测] 已在哈啰 app 车主标签。")

    # 2) 只做一件事：点击「★ 出发时间 (76 可点) 今天11:35(78)」打开时间选择器弹窗
    start_time_row = d(resourceId="com.jingyao.easybike:id/clStartTime")
    if not start_time_row.exists(timeout=2):
        print("未找到出发时间行 clStartTime (76)，请确保在车主页。")
        return 1
    start_time_row.click()
    print("  已点击「出发时间」行 (clStartTime)，等待时间选择器弹窗…")
    # 等弹窗「请选择预计出发时间」出现后再操作（最多等 15 秒）
    time.sleep(1.5)
    for _ in range(28):
        time.sleep(0.5)
        if d(text="请选择预计出发时间").exists(timeout=0.6) or d(textContains="预计出发时间").exists(timeout=0.6):
            break
    else:
        print("未检测到时间选择器弹窗，请确认已点击「出发时间」且弹窗已弹出。")
        return 1
    time.sleep(1.2)  # 等弹窗内三列滚轮完全出现

    # 3) 仅在时间选择器弹窗内：日期列→小时列→分钟列 依次翻到目标，再点「确认出发时间」
    ok = confirm_departure_time_dialog(d, target_time=target)
    print("处理结果:", "成功" if ok else "未发现弹窗或未点击到确认按钮")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
