import csv
import math
import os
import sys
import time
from pathlib import Path

# Retain compatibility with the Linux CPLEX Studio installation used for the
# experiments, while still allowing a standard docplex installation.
sys.path.append('/opt/ibm/ILOG/CPLEX_Studio2211/cplex/python/3.10/x86-64_linux')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docplex.mp.model import Model

from search_support import (  # noqa: E402
    analytical_cycle_lower_bound,
    average_power_cap,
    initial_probe_horizon,
    next_probe_horizon,
)


def calculate_qmax(W, m):
    return average_power_cap(W, m)


def create_assignment_model(n, m, c, model, Ex_times, W, lower_bound):
    X = [[model.binary_var(name=f'X_{i}_{j}') for j in range(m)] for i in range(n)]
    S = [
        [model.binary_var(name=f'S_{i}_{t}') for t in range(max(0, c - Ex_times[i] + 1))]
        for i in range(n)
    ]
    makespan = model.integer_var(ub=c, name='makespan')
    return model, X, S, calculate_qmax(W, m), makespan

def add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan, lower_bound):
    cons = 0
    # (1) Objective
    model.minimize(makespan)
    model.add_constraint(makespan >= lower_bound)
    cons += 1
    
    # (2) Each task assigned to exactly one station
    for j in range(n):
        model.add_constraint(model.sum(X[j][k] for k in range(m)) == 1)
        cons += 1

    # (3) The workload of every station is bounded by the optimized cycle time.
    for k in range(m):
        model.add_constraint(
            model.sum(Ex_times[j] * X[j][k] for j in range(n)) <= makespan
        )
        cons += 1
    
    # (4) Precedence: X[j,k] ≤ sum_{h≤k} X[i,h] for i ≺ j
    for (i, j) in precedence_relations:
        for k in range(m):
            model.add_constraint(X[j-1][k] <= model.sum(X[i-1][h] for h in range(k + 1)))
            cons += 1

    # (5) Each task assigned to exactly one start time
    for j in range(n):
        model.add_constraint(model.sum(S[j]) == 1)
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
                    r_i = range(
                        max(0, t - Ex_times[i] + 1), min(t, len(S[i]) - 1) + 1
                    )
                    r_j = range(
                        max(0, t - Ex_times[j] + 1), min(t, len(S[j]) - 1) + 1
                    )
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
                W[j] * model.sum(
                    S[j][s]
                    for s in range(
                        max(0, t - Ex_times[j] + 1), min(t, len(S[j]) - 1) + 1
                    )
                )
                for j in range(n)
            ) <= Wmax
        )
        cons += 1

    # (10) Makespan definition
    for j in range(n):
        model.add_constraint(
            makespan
            >= model.sum(S[j][t] * t for t in range(len(S[j]))) + Ex_times[j]
        )
        cons += 1
        
    return model, cons

def solve_assignment_problem(
    n, m, c, Ex_times, precedence_relations, W, lower_bound, time_limit=3600
):
    os.environ['PATH'] += os.pathsep + '/opt/ibm/ILOG/CPLEX_Studio2211/cplex/bin/x86-64_linux'

    model, X, S, Wmax, makespan = create_assignment_model(
        n, m, c, Model(name="Assignment_MIP"), Ex_times, W, lower_bound
    )
    print("Wmax =", Wmax)
    model, cons = add_assignment_constraints(
        n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations,
        makespan, lower_bound
    )

    model.parameters.mip.tolerances.mipgap = 0.0
    model.parameters.timelimit = max(0.001, time_limit)
    model.context.solver.log_output = True
    model.parameters.mip.limits.treememory = 2048

    variables = n * m + sum(len(row) for row in S) + 1
    try:
        solution = model.solve()
        return model, solution, X, S, makespan, variables, cons
    except (Exception, MemoryError) as exc:
        print("Error during solving:", exc)
        return model, None, X, S, makespan, variables, cons


def solver_status(model, solution):
    try:
        raw_status = str(model.solve_details.status).upper()
    except (AttributeError, TypeError):
        raw_status = ""
    if "OPTIMAL" in raw_status:
        return "Optimal"
    if "INFEASIBLE" in raw_status or "UNBOUNDED" in raw_status:
        return "Infeasible"
    if solution is not None:
        return "TIMEOUT"
    if "TIME LIMIT" in raw_status or "LIMIT" in raw_status:
        return "TIMEOUT"
    if "FAIL" in raw_status or "ERROR" in raw_status or "ABORT" in raw_status:
        return "FAILED"
    return "FAILED"


def objective_bound(model):
    try:
        value = float(model.solve_details.best_bound)
        return value if math.isfinite(value) else None
    except (AttributeError, TypeError, ValueError):
        return None


def objective_gap(model):
    try:
        value = float(model.solve_details.mip_relative_gap)
        return value if math.isfinite(value) else None
    except (AttributeError, TypeError, ValueError):
        return None

def get_value(solution, X, S, makespan_var, n, m, c, W, Ex_times):
    X_values = [
        [int(round(solution.get_value(X[i][k]))) for k in range(m)]
        for i in range(n)
    ]
    S_values = [
        [int(round(solution.get_value(S[i][t]))) for t in range(len(S[i]))]
        for i in range(n)
    ]

    schedule = [[0 for _ in range(c)] for _ in range(m + 1)]
    for task in range(n):
        station = next(k for k in range(m) if X_values[task][k] == 1)
        start = next(t for t, value in enumerate(S_values[task]) if value == 1)
        print(f"Task {task + 1} assigned to machine {station + 1} at time {start}")
        for t in range(start, start + Ex_times[task]):
            schedule[station][t] = W[task]

    schedule[m] = [sum(schedule[k_idx][t] for k_idx in range(m)) for t in range(c)]
    peak = max(schedule[m]) if schedule[m] else 0
    model_makespan = int(round(solution.get_value(makespan_var)))
    return schedule, peak, model_makespan

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
    os.makedirs("AVG_Peak/Output", exist_ok=True)
    with open("AVG_Peak/Output/result_cplex_mip.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(result)

def optimal(filename, time_limit=3600):
    n, W, precedence_relations, Ex_times = input_file(filename[0])
    m = filename[1]
    qmax = calculate_qmax(W, m)
    lower_bound = analytical_cycle_lower_bound(Ex_times, W, m, qmax)
    requested_c = (
        int(filename[2])
        if len(filename) > 2
        else initial_probe_horizon(Ex_times, lower_bound, m)
    )
    safe_horizon = sum(Ex_times)
    initial_c = min(max(requested_c, lower_bound), safe_horizon)
    c = initial_c
    start_time = time.time()
    model = solution = X = S = makespan_var = None
    var = cons = 0
    status = "TIMEOUT"
    while time.time() - start_time < time_limit:
        print(f"n={n}, m={m}, c={c}")
        remaining = time_limit - (time.time() - start_time)
        model, solution, X, S, makespan_var, var, cons = solve_assignment_problem(
            n, m, c, Ex_times, precedence_relations, W, lower_bound, remaining
        )
        status = solver_status(model, solution)
        if status == "Infeasible" and c < safe_horizon:
            model.end()
            model = solution = None
            c = next_probe_horizon(c, safe_horizon)
            print("Expanding horizon to:", c)
            continue
        break
    end_time = time.time()
    elapsed_time = end_time - start_time
    print("Time taken:", elapsed_time)
    print("Status:", status)
    bound = objective_bound(model) if model is not None else None
    gap = objective_gap(model) if model is not None else None
    if solution is not None:
        schedule, peak, model_makespan = get_value(
            solution, X, S, makespan_var, n, m, c, W, Ex_times
        )
        print("Peak =", peak)
        if bound is not None:
            print("Best bound:", bound)
        if status == "Optimal":
            print("Optimal makespan:", model_makespan)
        else:
            print("New makespan:", model_makespan)
        write_to_csv([
            filename[0], n, m, initial_c, model_makespan, var, cons, elapsed_time,
            status, qmax, "" if gap is None else gap
        ])
    else:
        print("No solution found.")
        write_to_csv([
            filename[0], n, m, initial_c, "", var, cons, elapsed_time,
            status, qmax, "" if gap is None else gap
        ])
    if model is not None:
        model.end()

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
    initial_c = int(sys.argv[3]) if len(sys.argv) > 3 else None
    optimal([filename, m] if initial_c is None else [filename, m, initial_c])
