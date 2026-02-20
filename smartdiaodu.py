

import requests
import hashlib
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = FastAPI(title="私人顺风车智能调度大脑 (单机完全体)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= 配置区 =================
BAIDU_AK = "xhDemVJisNK1JU962l0LKNGARjJvovdp"

# 填入你的 Bark Token
BARK_KEY = "bGPZAHqjNjdiQZTg5GeWWG" 

# 绕路容忍阈值（秒）：15分钟 = 900秒
MAX_DETOUR_SECONDS = 900 

# 内存数据库：用于存放已经推送过的订单指纹 { "MD5指纹": 推送时间戳 }
pushed_orders_cache = {}
# ==========================================

# 接口请求数据模型
class CurrentState(BaseModel):
    driver_loc: str
    pickups: List[str]
    deliveries: List[str]

class NewOrder(BaseModel):
    pickup: str
    delivery: str
    price: str

class EvaluateRequest(BaseModel):
    current_state: CurrentState
    new_order: NewOrder

# 1. 百度地理编码
def get_coordinate(address):
    url = f"https://api.map.baidu.com/geocoding/v3/?address={address}&output=json&ak={BAIDU_AK}"
    res = requests.get(url, timeout=5).json()
    if res['status'] == 0:
        loc = res['result']['location']
        return f"{loc['lat']},{loc['lng']}"
    raise Exception(f"地址无法解析: {address}")

# 2. 百度耗时矩阵
def get_duration_matrix(coords):
    points = "|".join(coords)
    url = f"https://api.map.baidu.com/routematrix/v2/driving?origins={points}&destinations={points}&ak={BAIDU_AK}&tactics=11"
    res = requests.get(url).json()
    if res['status'] != 0:
        raise Exception(f"矩阵获取失败: {res.get('message')}")
    
    size = len(coords)
    matrix = []
    for i in range(size):
        row = []
        for j in range(size):
            row.append(res['result'][i * size + j]['duration']['value'])
        matrix.append(row)
    return matrix

# 3. 核心算法：返回 (最优路线索引, 总耗时秒数)
def solve_pdp_route(matrix, num_pairs):
    num_nodes = len(matrix)
    manager = pywrapcp.RoutingIndexManager(num_nodes, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def duration_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if to_node == 0: # 不计算司机返回起点的耗时
            return 0 
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(duration_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index, 0, 300000, True, "Time"
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # 绑定接送关系
    for i in range(num_pairs):
        pickup_idx = manager.NodeToIndex(i + 1)
        delivery_idx = manager.NodeToIndex(i + 1 + num_pairs)
        routing.AddPickupAndDelivery(pickup_idx, delivery_idx)
        routing.solver().Add(routing.VehicleVar(pickup_idx) == routing.VehicleVar(delivery_idx))
        routing.solver().Add(time_dimension.CumulVar(pickup_idx) <= time_dimension.CumulVar(delivery_idx))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION

    solution = routing.SolveWithParameters(search_parameters)
    
    if solution:
        index = routing.Start(0)
        route_indices = []
        total_time = 0
        
        while not routing.IsEnd(index):
            route_indices.append(manager.IndexToNode(index))
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            # 累加实际行驶耗时
            total_time += routing.GetArcCostForVehicle(previous_index, index, 0)
            
        return route_indices, total_time
    return None, 0

# 4. 触发 iPhone Bark 推送
def push_to_bark(pickup, delivery, price, extra_mins):
    if not BARK_KEY or BARK_KEY == "在这里填入你的Bark_Key":
        print("未配置 Bark Key，跳过推送")
        return
        
    title = "🚨 发现极品顺路单！"
    body = f"接：{pickup}\n送：{delivery}\n价格：{price}元\n仅绕路：{extra_mins}分钟"
    # minuet 是一种提示音，你可以在 Bark app 里换别的
    url = f"https://api.day.app/{BARK_KEY}/{title}/{body}?sound=minuet"
    try:
        requests.get(url, timeout=3)
        print(f"已成功推送到 iPhone: 绕路 {extra_mins} 分钟, 赚 {price} 元")
    except Exception as e:
        print(f"推送失败: {e}")

# ================= 核心业务接口 =================

@app.post("/evaluate_new_order")
async def evaluate_new_order(req: EvaluateRequest):
    current = req.current_state
    new_order = req.new_order

    # 1. 生成订单 MD5 指纹进行防骚扰过滤
    order_str = f"{new_order.pickup}_{new_order.delivery}_{new_order.price}"
    fingerprint = hashlib.md5(order_str.encode()).hexdigest()
    
    now = time.time()
    if fingerprint in pushed_orders_cache:
        last_push_time = pushed_orders_cache[fingerprint]
        # 如果 30 分钟内已经推送过，直接静默拦截
        if now - last_push_time < 30 * 60:
            return {"status": "ignored", "reason": "该订单最近已评估/推送过，防骚扰拦截生效"}

    try:
        # 2. 计算【不接新单】的老路线总耗时
        old_addresses = [current.driver_loc] + current.pickups + current.deliveries
        old_coords = [get_coordinate(addr) for addr in old_addresses]
        old_matrix = get_duration_matrix(old_coords)
        _, old_total_time = solve_pdp_route(old_matrix, len(current.pickups))

        # 3. 计算【接下新单】的新路线总耗时
        new_pickups = current.pickups + [new_order.pickup]
        new_deliveries = current.deliveries + [new_order.delivery]
        new_addresses = [current.driver_loc] + new_pickups + new_deliveries
        
        new_coords = [get_coordinate(addr) for addr in new_addresses]
        new_matrix = get_duration_matrix(new_coords)
        new_route_indices, new_total_time = solve_pdp_route(new_matrix, len(new_pickups))

        if not new_route_indices:
            return {"status": "rejected", "reason": "无法规划出符合逻辑的合并路线"}

        # 4. 计算核心指标：绕路时间 (Detour)
        extra_time_seconds = new_total_time - old_total_time
        extra_time_minutes = round(extra_time_seconds / 60, 1)

        # 5. 商业逻辑判定：是否顺路？
        if extra_time_seconds <= MAX_DETOUR_SECONDS:
            # 记录到冷却池
            pushed_orders_cache[fingerprint] = now
            
            # 推送到手机
            push_to_bark(new_order.pickup, new_order.delivery, new_order.price, extra_time_minutes)
            
            # 整理新路线预览返回
            route_preview = [new_addresses[i] for i in new_route_indices]
            
            return {
                "status": "matched",
                "message": "极度顺路，已触发手机推送",
                "detour_minutes": extra_time_minutes,
                "profit": new_order.price,
                "new_route_preview": route_preview
            }
        else:
            return {
                "status": "rejected",
                "reason": f"绕路太远，将增加 {extra_time_minutes} 分钟，已放弃该单"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)