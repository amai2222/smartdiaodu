import requests
import time

# 与 tanzi.py 一致，指向同一大脑；本地调试可改为 http://127.0.0.1:8000/evaluate_new_order
BRAIN_URL = "https://xg.325218.xyz/api/evaluate_new_order"
# 当前司机 UUID，后端按此决定是否推送（与 seed 一致）
DRIVER_ID = "a0000001-0000-4000-8000-000000000001"

current_state = {
    "driver_loc": "如东县委党校",
    "pickups": ["如东县掘港镇荣生豪景花苑2号楼"],
    "deliveries": ["上海市外滩"]
}

mock_orders = [
    # 第一单：极品好单（必须点亮屏幕）
    {"pickup": "南通市崇川区万象城", "delivery": "上海奉贤区人民政府", "price": "88"},
    
    # 第二单：垃圾订单（必须静默拦截）
    {"pickup": "苏州市观前街", "delivery": "无锡市灵山大佛", "price": "40"},
    
    # 第三单：重复订单（测试防骚扰机制，必须拦截）
    {"pickup": "南通市崇川区万象城", "delivery": "上海奉贤区人民政府", "price": "85"}
]

print("🚗 探子脚本已启动，开始扫描顺风车大厅...\n")

for i, order in enumerate(mock_orders):
    print(f"[{i+1}] 抓取到新订单: {order['pickup']} -> {order['delivery']} ({order['price']}元)")
    
    payload = {
        "current_state": current_state,
        "new_order": order
    }
    if DRIVER_ID and str(DRIVER_ID).strip():
        payload["driver_id"] = str(DRIVER_ID).strip()

    try:
        response = requests.post(BRAIN_URL, json=payload)
        decision = response.json()
        
        if decision.get("status") == "matched":
            print("🟢 大脑决策：顺路单！已推送。")
            print(f"   预计绕路：{decision.get('detour_minutes')} 分钟\n")
        elif decision.get("status") == "ignored":
            print("🛡️ 大脑决策：拦截！刚刚推过，防骚扰生效。\n")
        else:
            print(f"🔴 大脑决策：放弃！原因: {decision.get('reason')}\n")
            
    except Exception as e:
        print("网络请求失败，检查后端是否启动:", e)
    
    time.sleep(5)