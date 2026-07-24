import sys
# Ép Python tìm kiếm thư viện CPLEX trực tiếp trong thư mục cài đặt của IBM
sys.path.append('/opt/ibm/ILOG/CPLEX_Studio2211/cplex/python/3.10/x86-64_linux')

# Sau đó mới đến các dòng import hiện tại của bạn...
import math
import time
import csv
from docplex.mp.model import Model

def create_assignment_model(n, m, c, model, Ex_times, W):
    # Khai báo biến nhị phân trong MIP sử dụng binary_var_matrix hoặc binary_var_dict
    X = [[model.binary_var(name=f'X_{i}_{j}') for j in range(m)] for i in range(n)]
    S = [[model.binary_var(name=f'S_{i}_{t}') for t in range(c)] for i in range(n)]
    
    W_sorted = sorted(W, reverse=True)
    UB = sum(W_sorted[i] for i in range(m))
    AVG = (sum(W_sorted[i] for i in range(n)) / n) * m
    LB = max(W_sorted[i] for i in range(n))
    
    # Biến liên tục hoặc nguyên cho mục tiêu makespan
    makespan = model.integer_var(name='makespan')
    Wmax = (UB + LB) / 2
    return model, X, S, int(Wmax), makespan

def add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan):
    cons = 0
    # (1) Objective trong MIP dùng model.minimize() trực tiếp làm hàm mục tiêu
    model.minimize(makespan)
    
    # (2) Each task assigned to exactly one station
    for j in range(n):
        model.add_constraint(model.sum(X[j][k] for k in range(m)) == 1)
        cons += 1

    # (3) Processing times at each station ≤ c (MIP thích ứng tốt với tổng tuyến tính này)
    for k in range(m):
        model.add_constraint(model.sum(Ex_times[j] * X[j][k] for j in range(n)) <= c)
        cons += 1
    
    # (4) Precedence: X[j,k] ≤ sum_{h≤k} X[i,h] for i ≺ j
    for (i, j) in precedence_relations:
        for k in range(m):
            model.add_constraint(X[j-1][k] <= model.sum(X[i-1][h] for h in range(k + 1)))
            cons += 1

    # (5) Each task assigned to exactly one start time
    for j in range(n):
        model.add_constraint(model.sum(S[j][t] for t in range(c - Ex_times[j] + 1)) == 1)
        cons += 1

    # (6) S[j,t] ≤ sum_{τ=t-ti}^{t} S[i,τ] + 2 - X[i,k] - X[j,k]
    for (i, j) in precedence_relations:
        if i > 0 and j > 0:
            for k in range(m):
                for t in range(c - Ex_times[j-1] + 1):
                    tau_range = range(max(0, t - Ex_times[i-1] + 1)) # Đảm bảo index không âm
                    model.add_constraint(
                        S[j-1][t] <= model.sum(S[i-1][tau] for tau in tau_range) + 2 - X[i-1][k] - X[j-1][k]
                    )
                    cons += 1
                    
    # (7) X[i,k] + X[j,k] + sum_{τ=t-ti+1}^{t} S[i,τ] + sum_{τ=t-tj+1}^{t} S[j,τ] ≤ 3
    for i in range(n - 1):
        for j in range(i + 1, n):
            for k in range(m):
                for t in range(c):
                    r_i = range(max(0, t - Ex_times[i] + 1), t + 1)
                    r_j = range(max(0, t - Ex_times[j] + 1), t + 1)
                    model.add_constraint(
                        X[i][k] + X[j][k] +
                        model.sum(S[i][tau] for tau in r_i) +
                        model.sum(S[j][tau] for tau in r_j)
                        <= 3
                    )
                    cons += 1

    # (8) Power peak constraint
    for t in range(c):
        model.add_constraint(
            model.sum(
                W[j] * model.sum(S[j][s] for s in range(max(0, t - Ex_times[j] + 1), t + 1))
                for j in range(n)
            ) <= Wmax
        )
        cons += 1

    # (10) Makespan definition
    for j in range(n):
        model.add_constraint(makespan >= model.sum(S[j][t] * t for t in range(c - Ex_times[j] + 1)) + Ex_times[j])
        cons += 1
        
    return model, cons

def solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W):
    # Khởi tạo mô hình MIP thay vì CP
    import os
    os.environ['PATH'] += os.pathsep + '/opt/ibm/ILOG/CPLEX_Studio2211/cplex/bin/x86-64_linux'

    mip_model = Model(name="Assignment_MIP")
    model, X, S, Wmax, makespan = create_assignment_model(n, m, c, mip_model, Ex_times, W)
    print("Wmax =", Wmax)
    model, cons = add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan)
    
    # Thiết lập tham số cho CPLEX MIP
    model.parameters.mip.tolerances.mipgap = 0.0  # Tìm giải pháp tối ưu tuyệt đối nếu có thể
    model.parameters.timelimit = 3600
    model.context.solver.log_output = True
    model.parameters.mip.limits.treememory = 2048
    
    try:
        solution = model.solve()
        return solution, X, S, makespan, n*m+n*c, cons
    except (Exception, MemoryError) as e:
        print("Error during solving:", e)
        return None, None, None, None, n*m+n*c, cons

def get_value(solution, X, S, makespan_var, n, m, c, W, Ex_times):
    # MIP lấy giá trị biến bằng cách gọi .solution_value trực tiếp từ đối tượng biến
    X_values = [[int(round(X[i][k].solution_value)) for k in range(m)] for i in range(n)]
    S_values = [[int(round(S[i][t].solution_value)) for t in range(c)] for i in range(n)]

    schedule = [[0 for _ in range(c)] for _ in range(m + 1)]
    makespan = 0

    for k in range(m):
        for j in range(n):
            for t in range(c):
                for t0 in range(Ex_times[j]):
                    if t - t0 >= 0:
                        if X_values[j][k] == 1 and S_values[j][t - t0] == 1:
                            schedule[k][t] = W[j]
                            makespan = max(makespan, t + 1)

    schedule[m] = [sum(schedule[k_idx][t] for k_idx in range(m)) for t in range(c)]
    peak = max(schedule[m]) if schedule[m] else 0
    model_makespan = int(round(makespan_var.solution_value))
    
    return schedule, peak, makespan, model_makespan

# --- Các hàm đọc/ghi file giữ nguyên logic của bạn ---
def input_file(file_name):
    W = []
    precedence_relations = set()
    Ex_Time = []
    with open(f"task_power/{file_name}.txt") as f:
        for line in f:
            if line.strip():
                W.append(int(line.strip()))
    with open(f"data/{file_name}.IN2") as f:
        lines = f.readlines()
    n = int(lines[0])
    for idx, line in enumerate(lines[1:], start=1):
        line = line.strip()
        if not line: continue
        if idx > n:
            pair = tuple(map(int, line.split(',')))
            if pair == (-1, -1):
                break
            precedence_relations.add(pair)
        else:
            Ex_Time.append(int(line))
    return n, W, precedence_relations, Ex_Time

def write_to_csv(result):
    with open("Peak_UB_LB/Output/result_cplex_mip.csv", "a") as f:
        writer = csv.writer(f)
        writer.writerow(result)

def optimal(filename):
    n, W, precedence_relations, Ex_times = input_file(filename[0])
    m = filename[1]  
    c = max(max(Ex_times), 2 * int(sum(Ex_times) / m))
    print(f"n={n}, m={m}, c={c}")
    start_time = time.time()
    solution, X, S, makespan_var, var, cons = solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W)
    end_time = time.time()
    
    print("Time taken:", end_time - start_time)
    if solution:
        print(f"Solution for {filename[0]} with n={n}, m={m}, c={c}:")
        schedule, Wmax_val, makespan, model_makespan = get_value(solution, X, S, makespan_var, n, m, c, W, Ex_times)
        print("Makespan =", makespan)
        print("Model Makespan =", model_makespan)
        write_to_csv([filename[0], n, m, c, model_makespan, var, cons, end_time - start_time])
    else:
        print("No solution found.")
        write_to_csv([filename[0], n, m, c, "Timeout/Infeasible", var, cons, end_time - start_time])

file_name = [
    # Easy families 
    # MERTENS 
    ["MERTENS", 6, 6],      # 0
    ["MERTENS", 2, 18],     # 1
    ["MERTENS", 5, 7],      # 2
    ["MERTENS", 3, 10],     # 3
    # BOWMAN
    ["BOWMAN", 5, 20],      # 4
    # JAESCHKE
    ["JAESCHKE", 8, 6],     # 5
    ["JAESCHKE", 6, 8],     # 6
    ["JAESCHKE", 4, 10],    # 7
    ["JAESCHKE", 3, 18],    # 8
    # JACKSON
    ["JACKSON", 8, 7],      # 9
    ["JACKSON", 3, 21],     # 10
    ["JACKSON", 6, 9],      # 11
    ["JACKSON", 5, 10],     # 12
    ["JACKSON", 4, 13],     # 13
    # MANSOOR
    ["MANSOOR", 4, 48],     # 14
    ["MANSOOR", 2, 94],     # 15
    ["MANSOOR", 3, 62],     # 16
    # MITCHELL
    ["MITCHELL", 8, 14],    # 17
    ["MITCHELL", 3, 39],    # 18
    ["MITCHELL", 5, 26],    # 19
    # ROSZIEG
    ["ROSZIEG", 10, 14],    # 20
    ["ROSZIEG", 4, 32],     # 21
    ["ROSZIEG", 6, 25],     # 22
    ["ROSZIEG", 8, 18],     # 23
    # HESKIA
    ["HESKIA", 8, 138],     # 24
    ["HESKIA", 3, 342],     # 25
    ["HESKIA", 5, 205],     # 26
    ["HESKIA", 4, 324],     # 27

    # Hard families
    # BUXEY
    ["BUXEY", 7, 47],       # 28
    ["BUXEY", 8, 41],       # 29
    ["BUXEY", 11, 33],      # 30
    ["BUXEY", 13, 27],      # 31
    ["BUXEY", 12, 30],      # 32
    ["BUXEY", 10, 36],      # 33
    # SAWYER
    ["SAWYER", 14, 25],     # 34
    ["SAWYER", 8, 41],      # 35
    ["SAWYER", 12, 30],     # 36
    ["SAWYER", 13, 27],     # 37
    ["SAWYER", 11, 33],     # 38
    ["SAWYER", 10, 36],     # 39
    ["SAWYER", 7, 54],      # 40
    ["SAWYER", 5, 75],      # 41
    # GUNTHER
    ["GUNTHER", 9, 54],     # 42
    ["GUNTHER", 14, 41],    # 43
    ["GUNTHER", 12, 44],    # 44
    ["GUNTHER", 11, 49],    # 45
    ["GUNTHER", 8, 69],     # 46
    ["GUNTHER", 7, 81],     # 47
    # WARNECKE
    ["WARNECKE", 25, 65],   # 48
    ["WARNECKE", 31, 54],   # 49
    ["WARNECKE", 29, 56],   # 50
    ["WARNECKE", 27, 62],   # 51
    ["WARNECKE", 24, 68],   # 52    
    ["WARNECKE", 23, 71],   # 53
    ["WARNECKE", 22, 74],   # 54
    ["WARNECKE", 21, 78],   # 55
    ["WARNECKE", 20, 82],   # 56
    ["WARNECKE", 19, 86],   # 57
    ["WARNECKE", 17, 92],   # 58
    ["WARNECKE", 15, 104],  # 59
    ["WARNECKE", 14, 111],  # 60
    # Lutz2
    ["LUTZ2", 49, 11],      # 61
    ["LUTZ2", 44, 12],      # 62
    ["LUTZ2", 40, 13],      # 63
    ["LUTZ2", 37, 14],      # 64
    ["LUTZ2", 34, 15],      # 65
    ["LUTZ2", 31, 16],      # 66
    ["LUTZ2", 29, 17],      # 67
    ["LUTZ2", 28, 18],      # 68
    ["LUTZ2", 26, 19],      # 69
    ["LUTZ2", 25, 20],      # 70
    ["LUTZ2", 24, 21]       # 71
]

if __name__ == "__main__":
    filename = sys.argv[1]
    m = int(sys.argv[2])
    optimal([filename, m])
    