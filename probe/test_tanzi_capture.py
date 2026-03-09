# -*- coding: utf-8 -*-
"""
探子抓单与上报测试：运行若干轮后退出，便于在终端查看能否获取订单并上报大脑。
用法：确保手机已连接、哈啰/滴滴顺风车大厅在前台，然后运行：
  python probe/test_tanzi_capture.py
"""
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(_script_dir), ".env"))
except ImportError:
    pass

import tanzi

MAX_CYCLES = 8  # 跑几轮后退出
SLEEP_SEC = 2.0


def main():
    print("=" * 50)
    print("  探子抓单测试（%d 轮后退出）" % MAX_CYCLES)
    print("=" * 50)
    print("  API:", tanzi.API_BASE)
    print("  司机:", tanzi.DRIVER_ID)
    print("  请确保手机已连接且顺风车大厅在前台")
    print("=" * 50)

    d = tanzi.connect_device()
    if not d:
        print("无法连接设备，请检查 USB/ADB 与 atx-agent。")
        return 1

    print("设备已连接。开始抓取…\n")
    last_fp = None
    app_index = 0
    use_rotation = tanzi.USE_APP_ROTATION and getattr(tanzi, "APP_ROTATION", None)

    for cycle in range(MAX_CYCLES):
        try:
            if use_rotation:
                app = tanzi.APP_ROTATION[app_index]
                tanzi.switch_to_app(d, app["package"])
                sel = app["selectors"]
                name = app["name"]
            else:
                sel = None
                name = ""
            order = tanzi.extract_one_order(d, sel)
            if order:
                fp = __import__("hashlib").md5(
                    ("%s_%s_%s" % (order["pickup"], order["delivery"], order["price"])).encode()
                ).hexdigest()
                if fp != last_fp:
                    last_fp = fp
                    tag = (" [%s]" % name) if name else ""
                    print("[抓取%s] %s -> %s %s 元" % (tag, order["pickup"], order["delivery"], order["price"]))
                    result = tanzi.report_to_brain(order)
                    if result is not None:
                        print("  -> 大脑已处理:", result.get("status"), result.get("reason", ""))
                    else:
                        print("  -> 上报失败或未返回")
            else:
                print("[轮次 %d] 当前屏幕未识别到订单（请确保在大厅列表页）" % (cycle + 1))
        except Exception as e:
            print("[轮次 %d] 异常: %s" % (cycle + 1, e))
        if cycle < MAX_CYCLES - 1:
            __import__("time").sleep(SLEEP_SEC)
        if use_rotation and (cycle + 1) % 5 == 0:
            app_index = (app_index + 1) % len(tanzi.APP_ROTATION)

    print("\n测试结束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
