import os
import csv
import math
import time
import gurobipy
from gurobipy import GRB
from dotenv import load_dotenv

# 1. Tự động tìm và nạp các biến môi trường từ file .env vào hệ thống
load_dotenv()

# 2. Đọc thông tin bản quyền từ file .env
wls_access_id = os.getenv("WLSACCESSID")
wls_secret = os.getenv("WLSSECRET")
license_id = os.getenv("LICENSEID")

if not all([wls_access_id, wls_secret, license_id]):
    print("LỖI: Thiếu thông tin bản quyền trong file .env!")
    exit(1)

# 3. Khởi tạo môi trường Gurobi Environment Toàn cục (Global)
# Sử dụng cơ chế nạp biến môi trường chuẩn của Gurobi thông qua Env(empty=True)
env = gurobipy.Env(empty=True)
env.setParam('WLSACCESSID', wls_access_id)
env.setParam('WLSSECRET', wls_secret)
env.setParam('LICENSEID', int(license_id))
env.start()

def create_assignment_model(n, m, c, model, Ex_times, W):
    X = [[model.addVar(vtype=gurobipy.GRB.BINARY, name=f'X_{i}_{j}') for j in range(m)] for i in range(n)]
    S = [[model.addVar(vtype=gurobipy.GRB.BINARY, name=f'S_{i}_{t}') for t in range(c)] for i in range(n)]
    W_sorted = sorted(W, reverse=True)
    UB = sum(W_sorted[i] for i in range(m))
    AVG = (sum(W_sorted[i] for i in range(n)) // n) * m
    LB = max(W_sorted[i] for i in range(n))
    makespan = model.addVar(vtype=gurobipy.GRB.INTEGER, name="makespan")
    Wmax = (AVG + LB) // 2
    model.update()
    return model, X, S, Wmax, makespan

def add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan):
    cons = 0
    # (1) Objective
    model.setObjective(makespan, gurobipy.GRB.MINIMIZE)
    cons += 1

    # (2) Each task assigned to exactly one station
    for j in range(n):
        model.addConstr(gurobipy.quicksum(X[j][k] for k in range(m)) == 1)
        cons += 1

    # (3) Processing times at each station ≤ makespan
    for k in range(m):
        model.addConstr(gurobipy.quicksum(Ex_times[j] * X[j][k] for j in range(n)) <= makespan)
        cons += 1
    
    # (4) Precedence
    for (i, j) in precedence_relations:
        for k in range(m):
            model.addConstr(X[j-1][k] <= gurobipy.quicksum(X[i-1][h] for h in range(k + 1)))
            cons += 1

    # (5) Each task assigned to exactly one start time
    for j in range(n):
        model.addConstr(gurobipy.quicksum(S[j][t] for t in range(c - Ex_times[j] + 1)) == 1)
        cons += 1

    # (6) Precedence time window constraint
    for (i, j) in precedence_relations:
        if i > 0 and j > 0:
            for k in range(m):
                for t in range(c - Ex_times[j-1] + 1):
                    tau_range = range(t - Ex_times[i-1] + 1)
                    model.addConstr(
                        S[j-1][t] <= gurobipy.quicksum(S[i-1][tau] for tau in tau_range) + 2 - X[i-1][k] - X[j-1][k]
                    )
                    cons += 1

    # (7) Overlap prevention
    for i in range(n - 1):
        for j in range(i + 1, n):
            for k in range(m):
                for t in range(c):
                    model.addConstr(
                        X[i][k] + X[j][k] +
                        gurobipy.quicksum(S[i][tau] for tau in range(t - Ex_times[i] + 1, t + 1)) +
                        gurobipy.quicksum(S[j][tau] for tau in range(t - Ex_times[j] + 1, t + 1))
                        <= 3
                    )
                    cons += 1

    # (8) Power peak constraint
    for t in range(c):
        model.addConstr(
            gurobipy.quicksum([
                W[j] * gurobipy.quicksum([S[j][s] for s in range(t - Ex_times[j] + 1, t + 1)])
                for j in range(n)
            ]) <= Wmax
        )
        cons += 1

    # (10) Makespan definition
    for i in range(n):
        model.addConstr(makespan >= gurobipy.quicksum(k * S[i][k] for k in range(c - Ex_times[i] + 1)) + Ex_times[i])
        cons += 1
    return model, cons

def solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W):
    # Khởi tạo model dựa trên đối tượng env đã được cấu hình từ .env trước đó
    model, X, S, Wmax, makespan = create_assignment_model(n, m, c, gurobipy.Model(env=env), Ex_times, W)
    model, cons = add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan)
    
    # Cấu hình các tham số chạy giải thuật
    model.Params.TimeLimit = 3600
    model.Params.MemLimit = 4096      # Giới hạn bộ nhớ 4GB
    model.Params.SoftMemLimit = 8192  
    model.Params.LogToConsole = 1     # ĐẶT BẰNG 1 để script ngoài bắt được log "New makespan:" theo thời gian thực
    
    model.optimize()
    return model, n*m + n*c, cons

def input_file(file_name):
    W = []  
    precedence_relations = set()
    Ex_Time = []

    # Đọc file task_power
    with open(f"task_power/{file_name}.txt") as f:
        for line in f:
            if line.strip():
                W.append(int(line.strip()))

    # Đọc file data
    with open(f"data/{file_name}.IN2") as f:
        lines = f.readlines()

    n = int(lines[0])
    for idx, line in enumerate(lines[1:], start=1):
        line = line.strip()
        if not line:
            continue
        if idx > n:
            pair = tuple(map(int, line.split(',')))
            if pair == (-1, -1):
                break
            precedence_relations.add(pair)
        else:
            Ex_Time.append(int(line))

    return n, W, precedence_relations, Ex_Time

def get_value(solution, n, m, c, W, Ex_times):
    X_values = [[0 for _ in range(m)] for _ in range(n)]
    S_values = [[0 for _ in range(c)] for _ in range(n)]

    for i in range(n):
        for k in range(m):
            var_name = f"X_{i}_{k}"
            X_values[i][k] = solution.getVarByName(var_name).X

    for i in range(n):
        for t in range(c):
            var_name = f"S_{i}_{t}"
            S_values[i][t] = solution.getVarByName(var_name).X

    schedule = [[0 for _ in range(c)] for _ in range(m + 1)]

    for k in range(m):
        for j in range(n):
            for t in range(c):
                for t0 in range(Ex_times[j]):
                    if X_values[j][k] == 1 and t - t0 >= 0 and S_values[j][t - t0] == 1:
                        schedule[k][t] = W[j]

    schedule[m] = [sum(schedule[j][t] for j in range(m)) for t in range(c)]
    peak = max(schedule[m])
    makespan = solution.getVarByName("makespan").X
    return schedule, makespan, peak

def write_to_csv(result):
    with open("Output/result_gurobi.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(result)

def optimal(filename):
    n, W, precedence_relations, Ex_times = input_file(filename[0])
    m = filename[1]  # Number of stations
    c = filename[2]  # Increased capacity to avoid infeasibility
    print(f"n={n}, m={m}, c={c}")
    start_time = time.time()
    
    solution, var, cons = solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print("Time taken:", elapsed_time)
    
    # Kiểm tra xem có tìm thấy lời giải hợp lệ (nghiệm khả thi) hay không
    if solution.SolCount > 0:
        schedule, makespan, peak = get_value(solution, n, m, c, W, Ex_times)
        print("Peak =", peak)
        # Ép print cú pháp này để file điều khiển cha (Subprocess) bắt trọn được kể cả khi timeout giữa chừng
        print(f"New makespan: {makespan}")
        write_to_csv([filename[0], n, m, c, makespan, var, cons, elapsed_time])
    else:
        print("No solution found.")
        write_to_csv([filename[0], n, m, c, "Timeout/Infeasible", var, cons, elapsed_time])
        
    # QUAN TRỌNG: Giải phóng bộ nhớ của model hiện tại để tránh tích tụ làm tràn RAM
    solution.dispose()

file_name2 = [
    # Easy families 
    ["MERTENS", 6, 10, 164],     # 0
    ["MERTENS", 2, 29, 54],      # 1
    ["BOWMAN", 5, 30, 146],      # 2
    ["JAESCHKE", 8, 10, 173],    # 3
    ["JAESCHKE", 3, 25, 47],     # 4
    ["JACKSON", 8, 12, 166],     # 5
    ["JACKSON", 3, 31, 57],      # 6
    ["MANSOOR", 4, 93, 111],     # 7
    ["MANSOOR", 2, 185, 71],     # 8
    ["MITCHELL", 8, 27, 225],    # 9
    ["MITCHELL", 3, 70, 84],     # 10
    ["ROSZIEG", 10, 25, 242],    # 11
    ["ROSZIEG", 4, 63, 118],     # 12
    # Hard families
    ["BUXEY", 7, 93, 184],       # 13
    ["BUXEY", 14, 47, 999],      # 14
    ["SAWYER", 14, 47, 282],     # 15
    ["SAWYER", 7, 93, 158]       # 16
]

for i in range(len(file_name2)):
    optimal(file_name2[i])