# -*- coding: utf-8 -*-
"""
测试：出发时间=今天，出发地/目的地=数据库获取。
模拟数据库有计划时，用「今天」作为出发时间执行哈啰设置流程。
用法：python probe/test_helo_today_from_db.py
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

# 出发时间：今天（可被环境变量覆盖，如 TANZI_DRIVER_DEPART_TIME=今天 14:00）
DEPART_TIME_TODAY = os.environ.get("TANZI_DRIVER_DEPART_TIME", "").strip() or "今天 08:00"
if "今天" not in DEPART_TIME_TODAY and "明天" not in DEPART_TIME_TODAY:
    DEPART_TIME_TODAY = "今天 " + DEPART_TIME_TODAY if DEPART_TIME_TODAY else "今天 08:00"


def main():
    from navigate_helo import get_planned_trip_from_db
    from helo_setup_then_orders import main as run_helo_setup

    plan = get_planned_trip_from_db()
    origin = (plan.get("origin") or "").strip() or None
    dest = (plan.get("destination") or "").strip() or None

    print("=" * 50)
    print("  测试：出发时间=今天，出发地/目的地=数据库")
    print("=" * 50)
    print("  出发时间: %s" % DEPART_TIME_TODAY)
    print("  出发地(库): %s" % (origin or "(未从数据库获取，将用环境变量/默认)"))
    print("  目的地(库): %s" % (dest or "(未从数据库获取，将用环境变量/默认)"))
    print("=" * 50)

    if not origin and not dest:
        print("  提示：数据库暂无计划，将使用 TANZI_DRIVER_LOC / TANZI_DRIVER_DEST 或脚本默认地址。")
    print()

    return run_helo_setup(origin=origin, dest=dest, departure_time=DEPART_TIME_TODAY)


if __name__ == "__main__":
    sys.exit(main())
