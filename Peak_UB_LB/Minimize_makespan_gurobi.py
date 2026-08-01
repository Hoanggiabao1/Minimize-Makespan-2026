import os
import csv
import time
import sys
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

def calculate_qmax(W, m):
    ordered = sorted(W, reverse=True)
    return (sum(ordered[:m]) + max(ordered)) // 2

def create_assignment_model(n, m, c, model, Ex_times, W):
    X = [[model.addVar(vtype=gurobipy.GRB.BINARY, name=f'X_{i}_{j}') for j in range(m)] for i in range(n)]
    S = [
        [model.addVar(vtype=gurobipy.GRB.BINARY, name=f'S_{i}_{t}')
         for t in range(max(0, c - Ex_times[i] + 1))]
        for i in range(n)
    ]
    makespan = model.addVar(vtype=gurobipy.GRB.INTEGER, name="makespan")
    Wmax = calculate_qmax(W, m)
    model.update()
    return model, X, S, Wmax, makespan

def solver_status(model):
    if model.Status == GRB.OPTIMAL:
        return "Optimal"
    if model.Status == GRB.TIME_LIMIT:
        return "TIMEOUT"
    if model.Status == GRB.INFEASIBLE:
        return "Infeasible"
    if model.Status == GRB.INF_OR_UNBD:
        # Completion-time constraints bound this model below.
        return "Infeasible"
    if model.Status == getattr(GRB, "MEM_LIMIT", -1):
        return "OOM"
    return f"STATUS_{model.Status}"

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
        model.addConstr(gurobipy.quicksum(S[j]) == 1)
        cons += 1

    # (6) Precedence time window constraint
    for (i, j) in precedence_relations:
        if i > 0 and j > 0:
            for k in range(m):
                for t in range(c - Ex_times[j-1] + 1):
                    tau_range = range(max(0, t - Ex_times[i-1] + 1))
                    model.addConstr(
                        S[j-1][t] <= gurobipy.quicksum(S[i-1][tau] for tau in tau_range) + 2 - X[i-1][k] - X[j-1][k]
                    )
                    cons += 1

    # (7) Overlap prevention
    for i in range(n - 1):
        for j in range(i + 1, n):
            for k in range(m):
                for t in range(c):
                    starts_i = range(max(0, t - Ex_times[i] + 1), min(t, len(S[i]) - 1) + 1)
                    starts_j = range(max(0, t - Ex_times[j] + 1), min(t, len(S[j]) - 1) + 1)
                    model.addConstr(
                        X[i][k] + X[j][k] +
                        gurobipy.quicksum(S[i][tau] for tau in starts_i) +
                        gurobipy.quicksum(S[j][tau] for tau in starts_j)
                        <= 3
                    )
                    cons += 1

    # (8) Power peak constraint
    for t in range(c):
        model.addConstr(
            gurobipy.quicksum([
                W[j] * gurobipy.quicksum(
                    S[j][s]
                    for s in range(max(0, t - Ex_times[j] + 1), min(t, len(S[j]) - 1) + 1)
                )
                for j in range(n)
            ]) <= Wmax
        )
        cons += 1

    # (10) Makespan definition
    for i in range(n):
        model.addConstr(makespan >= gurobipy.quicksum(k * S[i][k] for k in range(len(S[i]))) + Ex_times[i])
        cons += 1
    return model, cons

def solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W, time_limit=3600):
    # Khởi tạo model dựa trên đối tượng env đã được cấu hình từ .env trước đó
    model, X, S, Wmax, makespan = create_assignment_model(n, m, c, gurobipy.Model(env=env), Ex_times, W)
    model, cons = add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan)
    
    # Cấu hình các tham số chạy giải thuật
    model.Params.TimeLimit = max(0.001, time_limit)
    model.Params.SoftMemLimit = 4  # Gurobi measures this parameter in GB.
    model.Params.LogToConsole = 1     # ĐẶT BẰNG 1 để script ngoài bắt được log "New makespan:" theo thời gian thực
    
    model.optimize()
    return model, n * m + sum(max(0, c - p + 1) for p in Ex_times) + 1, cons

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
    S_values = [[0 for _ in range(max(0, c - Ex_times[i] + 1))] for i in range(n)]

    for i in range(n):
        for k in range(m):
            var_name = f"X_{i}_{k}"
            X_values[i][k] = solution.getVarByName(var_name).X

    for i in range(n):
        for t in range(len(S_values[i])):
            var_name = f"S_{i}_{t}"
            S_values[i][t] = solution.getVarByName(var_name).X

    schedule = [[0 for _ in range(c)] for _ in range(m + 1)]
    for task in range(n):
        station = next(k for k in range(m) if X_values[task][k] > 0.5)
        start = next(t for t, value in enumerate(S_values[task]) if value > 0.5)
        print(f"Task {task + 1} assigned to machine {station + 1} at time {start}")
        for t in range(start, start + Ex_times[task]):
            schedule[station][t] = W[task]

    schedule[m] = [sum(schedule[j][t] for j in range(m)) for t in range(c)]
    peak = max(schedule[m])
    makespan = int(round(solution.getVarByName("makespan").X))
    return schedule, makespan, peak

def write_to_csv(result):
    os.makedirs("Peak_UB_LB/Output", exist_ok=True)
    with open("Peak_UB_LB/Output/result_gurobi.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(result)

def optimal(filename):
    n, W, precedence_relations, Ex_times = input_file(filename[0])
    m = filename[1]  # Number of stations
    initial_c = filename[2]
    c = max(initial_c, max(Ex_times))
    safe_horizon = sum(Ex_times)
    start_time = time.time()
    solution = None
    var = cons = 0
    status = "TIMEOUT"
    while time.time() - start_time < 3600:
        print(f"n={n}, m={m}, c={c}")
        remaining = 3600 - (time.time() - start_time)
        solution, var, cons = solve_assignment_problem(
            n, m, c, Ex_times, precedence_relations, W, remaining
        )
        status = solver_status(solution)
        if status == "Infeasible" and c < safe_horizon:
            solution.dispose()
            solution = None
            c = min(safe_horizon, max(c + 1, (3 * c + 1) // 2))
            print("Expanding horizon to:", c)
            continue
        break
    end_time = time.time()
    elapsed_time = end_time - start_time
    if solution is None and status == "Infeasible":
        status = "TIMEOUT"
    print("Time taken:", elapsed_time)
    
    # Kiểm tra xem có tìm thấy lời giải hợp lệ (nghiệm khả thi) hay không
    if solution is not None and solution.SolCount > 0:
        schedule, makespan, peak = get_value(solution, n, m, c, W, Ex_times)
        best_bound = solution.ObjBound
        gap = solution.MIPGap
        print("Peak =", peak)
        print(f"Status: {status}")
        print(f"Best bound: {best_bound}")
        if status == "Optimal":
            print(f"Optimal makespan: {makespan}")
        else:
            print(f"New makespan: {makespan}")
        write_to_csv([filename[0], n, m, initial_c, makespan, var, cons, elapsed_time, status, calculate_qmax(W, m), gap])
    else:
        print(f"Status: {status}")
        print("No solution found.")
        write_to_csv([filename[0], n, m, initial_c, "", var, cons, elapsed_time, status, calculate_qmax(W, m), ""])
        
    # QUAN TRỌNG: Giải phóng bộ nhớ của model hiện tại để tránh tích tụ làm tràn RAM
    if solution is not None:
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

if __name__ == "__main__":
    if len(sys.argv) == 4:
        optimal([sys.argv[1], int(sys.argv[2]), int(sys.argv[3])])
    else:
        for item in file_name2:
            optimal(item)
