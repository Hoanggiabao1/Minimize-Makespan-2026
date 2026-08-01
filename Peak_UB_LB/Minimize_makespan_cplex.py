import os
import sys

import docplex.cp
from docplex.cp.model import CpoModel
import time
import csv
from docplex.cp.config import context

cpo_execfile = os.getenv("CPO_EXECFILE")
if cpo_execfile:
    context.solver.local.execfile = cpo_execfile

def calculate_qmax(W, m):
    ordered = sorted(W, reverse=True)
    return (sum(ordered[:m]) + max(ordered)) // 2

def create_assignment_model(n, m, c, model, Ex_times, W):
    X = [[model.binary_var(name=f'X_{i}_{j}') for j in range(m)] for i in range(n)]
    S = [
        [model.binary_var(name=f'S_{i}_{t}') for t in range(max(0, c - Ex_times[i] + 1))]
        for i in range(n)
    ]
    makespan = model.integer_var(name='makespan')
    return model, X, S, calculate_qmax(W, m), makespan

def solver_status(solution):
    if solution is None:
        return "FAILED"
    raw_status = str(solution.get_solve_status()).upper()
    if "OPTIMAL" in raw_status:
        return "Optimal"
    if "INFEASIBLE" in raw_status:
        return "Infeasible"
    if "FEASIBLE" in raw_status or "UNKNOWN" in raw_status:
        return "TIMEOUT"
    if "FAIL" in raw_status or "ABORT" in raw_status:
        return "FAILED"
    return raw_status or "UNKNOWN"

def objective_bound(solution):
    try:
        bounds = solution.get_objective_bounds()
        return float(bounds[0]) if bounds else None
    except (AttributeError, IndexError, TypeError, ValueError):
        return None

def objective_gap(solution):
    try:
        gaps = solution.get_objective_gaps()
        return float(gaps[0]) if gaps else None
    except (AttributeError, IndexError, TypeError, ValueError):
        return None

def add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan):
    cons = 0
    # (1) Objective
    model.add_constraint(model.minimize(makespan))
    cons += 1
    # (2) Each task assigned to exactly one station
    for j in range(n):
        model.add_constraint(model.sum([X[j][k] for k in range(m)]) == 1)
        cons += 1

    # (3) Processing times at each station ≤ c
    for k in range(m):
        model.add_constraint(model.sum([Ex_times[j] * X[j][k] for j in range(n)]) <= makespan)
        cons += 1
    
    # (4) Precedence: X[j,k] ≤ sum_{h<k} X[i,h] for i ≺ j
    for (i, j) in precedence_relations:
        for k in range(m):
            model.add_constraint(X[j-1][k] <= model.sum([X[i-1][h] for h in range(k + 1)]))
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
                    tau_range = range(max(0, t - Ex_times[i-1] + 1))
                    model.add_constraint(
                        S[j-1][t] <= model.sum([S[i-1][tau] for tau in tau_range]) + 2 - X[i-1][k] - X[j-1][k]
                    )
                    cons += 1
                    
    # (7) X[i,k] + X[j,k] + sum_{τ=t-ti+1}^{t} S[i,τ] + sum_{τ=t-tj+1}^{t} S[j,τ] ≤ 3
    for i in range(n - 1):
        for j in range(i + 1, n):
            for k in range(m):
                for t in range(c):
                    starts_i = range(max(0, t - Ex_times[i] + 1), min(t, len(S[i]) - 1) + 1)
                    starts_j = range(max(0, t - Ex_times[j] + 1), min(t, len(S[j]) - 1) + 1)
                    model.add_constraint(
                        X[i][k] + X[j][k] +
                        model.sum([S[i][tau] for tau in starts_i]) +
                        model.sum([S[j][tau] for tau in starts_j])
                        <= 3
                    )
                    cons += 1

    # (8) Power peak constraint
    for t in range(c):
        model.add_constraint(
            model.sum([
                W[j] * model.sum([
                    S[j][s]
                    for s in range(max(0, t - Ex_times[j] + 1), min(t, len(S[j]) - 1) + 1)
                ])
                for j in range(n)
            ]) <= Wmax
        )
        cons += 1

    # (9) Variable domains (already set by binary_var/integer_var)

    # (10) Makespan definition
    for j in range(n):
        model.add_constraint(makespan >= model.sum([S[j][t] * t for t in range(len(S[j]))]) + Ex_times[j])
        cons += 1
    return model, cons

def solve_assignment_problem(n, m, c, Ex_times, precedence_relations, W, time_limit=3600):
    model, X, S, Wmax, makespan = create_assignment_model(n, m, c, CpoModel(), Ex_times, W)
    print("Wmax =", Wmax)
    model, cons = add_assignment_constraints(n, m, c, model, X, S, Wmax, W, Ex_times, precedence_relations, makespan)
    model.set_parameters(LogVerbosity="Quiet", TimeLimit=max(1, time_limit))
    try:
        solution = model.solve()
        return solution, n * m + sum(len(row) for row in S) + 1, cons
    except Exception as exc:
        print(f"CP Optimizer error: {exc}")
        return None, n * m + sum(len(row) for row in S) + 1, cons

def write_html(file_name, ans_map, n, m, c, peak, makespan):
    with open(f"Output/{file_name}_makespan {n} {m} {c}/{file_name}_makespan {n} {m} {c}.html", "w") as f:
        f.write("<html><head><style>")
        f.write("table {border-collapse: collapse;}")
        f.write("td, th {border: 1px solid black; padding: 5px; text-align: center;}")
        f.write("</style></head><body>")
        f.write(f"<h2>Schedule for {file_name} n = {n} m = {m} c = {c} peak = {peak} (Makespan: {makespan})</h2>")
        f.write("<table>")
        f.write("<tr><th>Machine</th>")
        for i in range(makespan):
            f.write(f"<th>Time {i + 1}</th>")
        f.write("</tr>")
        for j in range(m + 1):
            machine_name = f"Machine {j+1}" if j < m else "Total Power"
            f.write(f"<tr><td>{machine_name}</td>")
            for i in range(makespan):
                f.write(f"<td>{ans_map[j][i]}</td>")
            f.write("</tr>")

        f.write("</table></body></html>")

def input_file(file_name):
    W = []
    precedence_relations = set()
    Ex_Time = []

    # Đọc file task_power
    with open(f"task_power/{file_name}.txt") as f:
        for line in f:
            W.append(int(line.strip()))

    # Đọc file data
    with open(f"data/{file_name}.IN2") as f:
        lines = f.readlines()

    n = int(lines[0])
    for idx, line in enumerate(lines[1:], start=1):
        line = line.strip()
        if idx > n:
            pair = tuple(map(int, line.split(',')))
            if pair == (-1, -1):
                break
            precedence_relations.add(pair)
        else:
            Ex_Time.append(int(line))

    return n, W, precedence_relations, Ex_Time

def get_value(solution, n, m, c, W, Ex_times):
    # From solution take X and S return matrix of scheduled tasks
    X_values = [[0 for _ in range(m)] for _ in range(n)]
    S_values = [[0 for _ in range(max(0, c - Ex_times[i] + 1))] for i in range(n)]

    for i in range(n):
        for k in range(m):
            var_name = f"X_{i}_{k}"
            X_values[i][k] = solution.get_value(var_name)

    for i in range(n):
        for t in range(len(S_values[i])):
            var_name = f"S_{i}_{t}"
            S_values[i][t] = solution.get_value(var_name)

    schedule = [[0 for _ in range(c)] for _ in range(m +1)]
    for task in range(n):
        station = next(k for k in range(m) if X_values[task][k] > 0.5)
        start = next(t for t, value in enumerate(S_values[task]) if value > 0.5)
        print(f"Task {task + 1} assigned to machine {station + 1} at time {start}")
        for t in range(start, start + Ex_times[task]):
            schedule[station][t] = W[task]

    #Last row = sum(schedule[j][t] for j in range(n))
    schedule[m] = [sum(schedule[j][t] for j in range(m)) for t in range(c)]
    peak = max(schedule[m])
    model_makespan = int(round(solution.get_value("makespan")))
    return schedule, peak, model_makespan

def write_to_csv(result):
    os.makedirs("Peak_UB_LB/Output", exist_ok=True)
    with open("Peak_UB_LB/Output/result_cplex.csv", "a") as f:
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
    last_solved_c = None
    while time.time() - start_time < 3600:
        print(f"n={n}, m={m}, c={c}")
        last_solved_c = c
        remaining = 3600 - (time.time() - start_time)
        solution, var, cons = solve_assignment_problem(
            n, m, c, Ex_times, precedence_relations, W, remaining
        )
        status = solver_status(solution)
        if status == "Infeasible" and c < safe_horizon:
            c = min(safe_horizon, max(c + 1, (3 * c + 1) // 2))
            print("Expanding horizon to:", c)
            continue
        break
    end_time = time.time()
    elapsed_time = end_time - start_time
    if last_solved_c != c:
        status = "TIMEOUT"
        solution = None
    print("Time taken:", elapsed_time)
    print("Status:", status)
    has_incumbent = solution is not None and solution.is_solution()
    bound = objective_bound(solution) if solution is not None else None
    gap = objective_gap(solution) if solution is not None else None
    if has_incumbent:
        schedule, peak, makespan = get_value(solution, n, m, c, W, Ex_times)
        if bound is not None:
            print("Best bound:", bound)
        if status == "Optimal":
            print("Optimal makespan:", makespan)
        else:
            print("New makespan:", makespan)
        write_to_csv([
            filename[0], n, m, initial_c, makespan, var, cons, elapsed_time,
            status, calculate_qmax(W, m), "" if gap is None else gap
        ])
    else:
        print("No solution found.")
        write_to_csv([
            filename[0], n, m, initial_c, "", var, cons, elapsed_time,
            status, calculate_qmax(W, m), "" if gap is None else gap
        ])

file_name = [
    # Easy families 
    # MERTENS 
    ["MERTENS", 6, 6],      # 0
    ["MERTENS", 2, 18],     # 1
    ["MERTENS", 5, 7],      # 2
    ["MERTENS", 5, 8],      # 3
    ["MERTENS", 3, 10],     # 4
    ["MERTENS", 2, 15],     # 5
    # Easy/MERTENS count: 6

    # BOWMAN
    ["BOWMAN", 5, 20],      # 6
    # Easy/BOWMAN count: 1

    # JAESCHKE
    ["JAESCHKE", 8, 6],     # 7
    ["JAESCHKE", 3, 18],    # 8
    ["JAESCHKE", 6, 8],     # 9
    ["JAESCHKE", 4, 10],    # 10
    ["JAESCHKE", 3, 18],    # 11
    # Easy/JAESCHKE count: 5

    # JACKSON
    ["JACKSON", 8, 7],      # 12
    ["JACKSON", 3, 21],     # 13
    ["JACKSON", 6, 9],      # 14
    ["JACKSON", 5, 10],     # 15
    ["JACKSON", 4, 13],     # 16
    ["JACKSON", 4, 14],     # 17
    # Easy/JACKSON count: 6

    # MANSOOR
    ["MANSOOR", 4, 48],     # 18
    ["MANSOOR", 2, 94],     # 19
    ["MANSOOR", 3, 62],     # 20
    # Easy/MANSOOR count: 3

    # MITCHELL
    ["MITCHELL", 8, 14],    # 21
    ["MITCHELL", 3, 39],    # 22
    ["MITCHELL", 8, 15],    # 23
    ["MITCHELL", 5, 21],    # 24
    ["MITCHELL", 5, 26],    # 25
    ["MITCHELL", 3, 35],    # 26
    # Easy/MITCHELL count: 6

    # ROSZIEG
    ["ROSZIEG", 10, 14],    # 27
    ["ROSZIEG", 4, 32],     # 28
    ["ROSZIEG", 6, 25],     # 29
    ["ROSZIEG", 8, 16],     # 30
    ["ROSZIEG", 8, 18],     # 31
    ["ROSZIEG", 6, 21],     # 32
    # Easy/ROSZIEG count: 6

    # HESKIA
    ["HESKIA", 8, 138],     # 33
    ["HESKIA", 3, 342],     # 34
    ["HESKIA", 5, 205],     # 35
    ["HESKIA", 5, 216],     # 36
    ["HESKIA", 4, 256],     # 37
    ["HESKIA", 4, 324],     # 38
    # Easy/HESKIA count: 6

    # Easy families total count: 39

    # Hard families
    # BUXEY
    ["BUXEY", 7, 47],       # 39
    ["BUXEY", 8, 41],       # 40
    ["BUXEY", 11, 33],      # 41
    ["BUXEY", 13, 27],      # 42
    ["BUXEY", 12, 30],      # 43
    ["BUXEY", 7, 54],       # 44
    ["BUXEY", 10, 36],      # 45
    # Hard/BUXEY count: 7

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
    # Hard/SAWYER count: 9

    # GUNTHER
    ["GUNTHER", 9, 54],     # 55
    ["GUNTHER", 9, 61],     # 56
    ["GUNTHER", 14, 41],    # 57
    ["GUNTHER", 12, 44],    # 58
    ["GUNTHER", 11, 49],    # 59
    ["GUNTHER", 8, 69],     # 60
    ["GUNTHER", 7, 81],     # 61
    # Hard/GUNTHER count: 7

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
    # Hard/WARNECKE count: 16

    # LUTZ2
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
    ["LUTZ2", 24, 21],      # 88
    # Hard/LUTZ2 count: 11

    # Hard families total count: 50

    # Total: 89
    ]

file_name2 = [
    # Easy families 
    # MERTENS 
    ["MERTENS", 6, 10, 164],      # 0
    ["MERTENS", 2, 29, 54],     # 1
    # BOWMAN
    ["BOWMAN", 5, 30, 146],      # 2

    # JAESCHKE
    ["JAESCHKE", 8, 10, 173],     # 3
    ["JAESCHKE", 3, 25, 47],    # 4

    # JACKSON
    ["JACKSON", 8, 12, 166],      # 5
    ["JACKSON", 3, 31, 57],     # 6

    # MANSOOR
    ["MANSOOR", 4, 93, 111],     # 7
    ["MANSOOR", 2, 185, 71],     # 8

    # MITCHELL
    ["MITCHELL", 8, 27, 225],    # 9
    ["MITCHELL", 3, 70, 84],    # 10

    # ROSZIEG
    ["ROSZIEG", 10, 25, 242],    # 11
    ["ROSZIEG", 4, 63, 118],     # 12

    # Hard families
    # BUXEY
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
