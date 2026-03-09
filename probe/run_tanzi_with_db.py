# -*- coding: utf-8 -*-
"""
探子整合脚本：根据数据库的出发时间、出发地点、目的地设置哈啰 App，并进入抓单循环获取订单。

流程：
1. 从 Supabase planned_trip_plans 读取第一条未完成计划的 origin、destination、departure_time
2. 启动/切到哈啰，进入车主页，设置出发地、目的地、出发时间（弹窗），点击「发布并搜索」
3. 同步探子当前状态（driver_loc/deliveries）为本次计划，便于大脑评估顺路单
4. 进入探子抓单循环：扫描顺风车大厅、上报大脑、按间隔轮询

用法：
  python probe/run_tanzi_with_db.py

环境变量：与 tanzi.py、navigate_helo、set_both_addresses 一致：
  SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY、TANZI_DRIVER_ID
  TANZI_DEVICE、TANZI_API_BASE、TANZI_LOOP_INTERVAL、TANZI_USE_APP_ROTATION 等
若数据库无计划，则使用 TANZI_DRIVER_LOC、TANZI_DRIVER_DEST、TANZI_DRIVER_DEPART_TIME 作为回退。
"""

import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
_root = os.path.dirname(_script_dir)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

# 先读库再导入 tanzi，以便下面可改写 tanzi.CURRENT_STATE
from navigate_helo import get_planned_trip_from_db
from set_both_addresses import main as set_helo_and_publish
import tanzi


def main():
    print("=" * 50)
    print("  探子整合脚本：数据库 → 哈啰设置 → 抓单")
    print("=" * 50)

    plan = get_planned_trip_from_db()
    origin = (plan.get("origin") or "").strip() or None
    dest = (plan.get("destination") or "").strip() or None
    departure_time = (plan.get("departure_time") or "").strip() or None

    if origin or dest:
        print("  数据库计划: 出发地=%s, 目的地=%s, 出发时间=%s" % (origin or "(空)", dest or "(空)", departure_time or "(空)"))
    else:
        print("  未从数据库读到计划，将使用环境变量 TANZI_DRIVER_LOC / TANZI_DRIVER_DEST / TANZI_DRIVER_DEPART_TIME")

    # 1) 设置哈啰：出发地、目的地、出发时间，并点击发布并搜索
    ret = set_helo_and_publish(origin=origin, dest=dest, departure_time=departure_time)
    if ret != 0:
        print("设置哈啰未成功，退出码:", ret)
        return ret

    # 2) 用本次计划更新探子当前状态，便于大脑评估顺路单
    if origin or dest:
        tanzi.CURRENT_STATE["driver_loc"] = origin or tanzi.CURRENT_STATE.get("driver_loc", "")
        tanzi.CURRENT_STATE["deliveries"] = [dest] if dest else (tanzi.CURRENT_STATE.get("deliveries") or [])
        tanzi.CURRENT_STATE["pickups"] = tanzi.CURRENT_STATE.get("pickups") or []
        print("  已同步探子状态: driver_loc=%s, deliveries=%s" % (tanzi.CURRENT_STATE["driver_loc"], tanzi.CURRENT_STATE["deliveries"]))

    # 3) 进入探子抓单循环（仅哈啰订单列表抓取、上报大脑）
    print("\n进入抓单循环，Ctrl+C 退出。\n")
    tanzi.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
