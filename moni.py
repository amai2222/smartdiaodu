import requests
import time

BRAIN_URL = "http://127.0.0.1:8000/evaluate_new_order"

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