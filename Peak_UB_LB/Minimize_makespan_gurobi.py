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
    AVG = (sum(W_sorted[i] for i in range(n)) / n) * m
    LB = max(W_sorted[i] for i in range(n))
    makespan = model.addVar(vtype=gurobipy.GRB.INTEGER, name="makespan")
    Wmax = (UB + LB) / 2
    model.update()
    return model, X, S, int(Wmax), makespan

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
    # Khởi tạo model dựa trên đối tượng env toàn cục
    model, X, S, Wmax, makespan = create_assignment_model(n, m, c, gurobipy.Model(env=env), Ex_times, W)
    model, cons = add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan)
    
    # --- CẤU HÌNH THAM SỐ TỐI ƯU HÓA BỘ NHỚ RAM ---
    model.Params.TimeLimit = 3600       # Giới hạn thời gian 1 tiếng
    model.Params.LogToConsole = 1       # Bật log thời gian thực
    
    # Ép dùng Primal Simplex (0) và giảm Threads xuống 2 để tiết kiệm bộ nhớ tối đa tại bước Root Relaxation
    model.Params.Method = 0  
    model.Params.Threads = 2

    # Cơ chế ghi cây quyết định (Branch-and-Bound) xuống ổ cứng khi dùng quá 1.5 GB RAM
    model.Params.NodefileStart = 1.5    
    model.Params.NodefileDir = "."      
    
    # Ngưỡng giới hạn RAM mềm bảo vệ hệ thống trước khi bị OS can thiệp bằng lệnh Killed
    model.Params.MemLimit = 12.0        
    # -----------------------------------------------------------------
    
    try:
        model.optimize()
        return model, n*m + n*c, cons
    except gurobipy.GurobiError as e:
        # Bắt ngoại lệ nếu tràn RAM hoặc gặp lỗi phần cứng phát sinh từ Gurobi
        print(f"\n[⚠️ GUROBI ERROR]: Quá trình tối ưu bị dừng do lỗi nội bộ (Có thể do tràn RAM): {e}")
        return None, n*m + n*c, cons
    except Exception as e:
        # Bắt các lỗi Python ngoại vi khác
        print(f"\n[⚠️ SYSTEM ERROR]: Lỗi hệ thống không xác định: {e}")
        return None, n*m + n*c, cons

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

def get_value(model, n, m, c, W, Ex_times):
    X_values = [[0 for _ in range(m)] for _ in range(n)]
    S_values = [[0 for _ in range(c)] for _ in range(n)]

    for i in range(n):
        for k in range(m):
            var_name = f"X_{i}_{k}"
            X_values[i][k] = model.getVarByName(var_name).X

    for i in range(n):
        for t in range(c):
            var_name = f"S_{i}_{t}"
            S_values[i][t] = model.getVarByName(var_name).X

    schedule = [[0 for _ in range(c)] for _ in range(m + 1)]

    for k in range(m):
        for j in range(n):
            for t in range(c):
                for t0 in range(Ex_times[j]):
                    if X_values[j][k] == 1 and t - t0 >= 0 and S_values[j][t - t0] == 1:
                        schedule[k][t] = W[j]

    schedule[m] = [sum(schedule[j][t] for j in range(m)) for t in range(c)]
    peak = max(schedule[m])
    makespan = model.getVarByName("makespan").X
    for line in schedule:
        print(line[:math.ceil(makespan)])
    return schedule, makespan, peak

def write_to_csv(result):
    with open("Peak_UB_LB/Output/result_gurobi.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(result)

def optimal(filename):
    n, W, precedence_relations, Ex_times = input_file(filename[0])
    m = filename[1]  # Number of stations
    c = max(max(Ex_times), (sum(Ex_times[i] for i in range(n)) // m)*2)
    print(f"\n--- Đang xử lý file: {filename[0]} (n={n}, m={m}) ---")
    start_time = time.time()
    
    # Thực hiện giải mô hình toán học
    model, var, cons = solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print("Time taken:", elapsed_time)
    
    try:
        # Nếu mô hình tồn tại hợp lệ và tìm được ít nhất 1 nghiệm khả thi (SolCount > 0)
        if model and model.SolCount > 0:
            schedule, makespan, peak = get_value(model, n, m, c, W, Ex_times)
            print("Peak =", peak)
            print(f"New makespan: {makespan}")
            write_to_csv([filename[0], n, m, c, makespan, var, cons, elapsed_time])
        else:
            # Trường hợp trả về None do dính ngoại lệ tràn RAM hoặc timeout không có nghiệm
            print("Không tìm thấy lời giải nào (Timeout / Vô nghiệm / Hoặc lỗi sập bộ nhớ RAM).")
            write_to_csv([filename[0], n, m, c, "No Solution", var, cons, elapsed_time])
    except Exception as e:
        print(f"Lỗi phát sinh khi trích xuất hoặc ghi dữ liệu kết quả: {e}")
        write_to_csv([filename[0], n, m, c, "Execution Error", var, cons, elapsed_time])
    finally:
        # Giải phóng tài nguyên của model hiện tại để chuẩn bị cho vòng lặp kế tiếp
        if model:
            model.dispose()

file_name = [
    # Easy families 
    # MERTENS 
    ["MERTENS", 6, 6],      # 0
    ["MERTENS", 2, 18],     # 1
    ["MERTENS", 5, 7],      # 2
    ["MERTENS", 5, 8],      # 3
    ["MERTENS", 3, 10],     # 4
    ["MERTENS", 2, 15],     # 5
    # BOWMAN
    ["BOWMAN", 5, 20],      # 6
    # JAESCHKE
    ["JAESCHKE", 8, 6],     # 7
    ["JAESCHKE", 3, 18],    # 8
    ["JAESCHKE", 6, 8],     # 9
    ["JAESCHKE", 4, 10],    # 10
    ["JAESCHKE", 3, 18],    # 11
    # JACKSON
    ["JACKSON", 8, 7],      # 12
    ["JACKSON", 3, 21],     # 13
    ["JACKSON", 6, 9],      # 14
    ["JACKSON", 5, 10],     # 15
    ["JACKSON", 4, 13],     # 16
    ["JACKSON", 4, 14],     # 17
    # MANSOOR
    ["MANSOOR", 4, 48],     # 18
    ["MANSOOR", 2, 94],     # 19
    ["MANSOOR", 3, 62],     # 20
    # MITCHELL
    ["MITCHELL", 8, 14],    # 21
    ["MITCHELL", 3, 39],    # 22
    ["MITCHELL", 8, 15],    # 23
    ["MITCHELL", 5, 21],    # 24
    ["MITCHELL", 5, 26],    # 25
    ["MITCHELL", 3, 35],    # 26
    # ROSZIEG
    ["ROSZIEG", 10, 14],    # 27
    ["ROSZIEG", 4, 32],     # 28
    ["ROSZIEG", 6, 25],     # 29
    ["ROSZIEG", 8, 16],     # 30
    ["ROSZIEG", 8, 18],     # 31
    ["ROSZIEG", 6, 21],     # 32
    # HESKIA
    ["HESKIA", 8, 138],     # 33
    ["HESKIA", 3, 342],     # 34
    ["HESKIA", 5, 205],     # 35
    ["HESKIA", 5, 216],     # 36
    ["HESKIA", 4, 256],     # 37
    ["HESKIA", 4, 324],     # 38

    # Hard families
    # BUXEY
    ["BUXEY", 7, 47],       # 39
    ["BUXEY", 8, 41],       # 40
    ["BUXEY", 11, 33],      # 41
    ["BUXEY", 13, 27],      # 42
    ["BUXEY", 12, 30],      # 43
    ["BUXEY", 7, 54],       # 44
    ["BUXEY", 10, 36],      # 45
    # SAWYER
    ["SAWYER", 14, 25],     # 46
    ["SAWYER", 7, 47],      # 47
    ["SAWYER", 8, 41],      # 48
    ["SAWYER", 12, 30],     # 49
    ["SAWYER", 13, 27],     # 50
    ["SAWYER", 11, 33],     # 51
    ["SAWYER", 10, 36],     # 52
    ["SAWYER", 7, 54],      # 53
    ["SAWYER", 5, 75],      # 54
    # GUNTHER
    ["GUNTHER", 9, 54],     # 55
    ["GUNTHER", 9, 61],     # 56
    ["GUNTHER", 14, 41],    # 57
    ["GUNTHER", 12, 44],    # 58
    ["GUNTHER", 11, 49],    # 59
    ["GUNTHER", 8, 69],     # 60
    ["GUNTHER", 7, 81],     # 61
    # WARNECKE
    ["WARNECKE", 25, 65],   # 62
    ["WARNECKE", 31, 54],   # 63
    ["WARNECKE", 29, 56],   # 64
    ["WARNECKE", 29, 58],   # 65
    ["WARNECKE", 27, 60],   # 66
    ["WARNECKE", 27, 62],   # 67
    ["WARNECKE", 24, 68],   # 68    
    ["WARNECKE", 23, 71],   # 69
    ["WARNECKE", 22, 74],   # 70
    ["WARNECKE", 21, 78],   # 71
    ["WARNECKE", 20, 82],   # 72
    ["WARNECKE", 19, 86],   # 73
    ["WARNECKE", 17, 92],   # 74
    ["WARNECKE", 17, 97],   # 75
    ["WARNECKE", 15, 104],  # 76
    ["WARNECKE", 14, 111],  # 77
    # Lutz2
    ["LUTZ2", 49, 11],      # 78
    ["LUTZ2", 44, 12],      # 79
    ["LUTZ2", 40, 13],      # 80
    ["LUTZ2", 37, 14],      # 81
    ["LUTZ2", 34, 15],      # 82
    ["LUTZ2", 31, 16],      # 83
    ["LUTZ2", 29, 17],      # 84
    ["LUTZ2", 28, 18],      # 85
    ["LUTZ2", 26, 19],      # 86
    ["LUTZ2", 25, 20],      # 87
    ["LUTZ2", 24, 21]
]

if __name__ == "__main__":
    # Bắt đầu chạy liên tục từ họ bài toán nặng HESKIA (vị trí index 33) cho tới hết file
    for i in range(len(file_name)):
        optimal(file_name[i])