import pysat
from pysat.solvers import Glucose3
from pysat.pb import PBEnc
from pysat.pb import EncType
import math
import time
import csv

def generate_variables(n, m, c):
    # X[i][s]: task i for station s
    X = [[i*m + s + 1 for s in range(m)] for i in range(n)]
    
    # B[i][t]: task i start at time unit t
    B = [[i*c + t + 1 + X[-1][-1] for t in range(c)] for i in range(n)]
    
    # A[i][t]: task i being executed at time unit t
    A = [[i*c + t + 1 + B[-1][-1] for t in range(c)] for i in range(n)]

    # C[i][t]: task i finish before time unit t
    C = [[i*c + t + 1 + A[-1][-1] + n*c for t in range(c)] for i in range(n)]

    return X, B, A, C

def caculate_UB(n, Ex_Time):
    UB = sum(Ex_Time)
    return UB

def list_constrain(n, m, c, precedence_relations, Ex_Time, W, A, B, X, C, peak):
    clauses = []
    # Each task is assigned to exactly one station
    for i in range(n):
        clause = [X[i][s] for s in range(m)]
        clauses.append(clause)
        for s1 in range(m):
            for s2 in range(s1 + 1, m):
                clauses.append([-X[i][s1], -X[i][s2]])
    
    # Precedence relations between stations
    for (i,j) in precedence_relations:
        for s1 in range(m):
            for s2 in range(s1):  # s2 < s1
                clauses.append([-X[i - 1][s1], -X[j - 1][s2]])

    # Precedence relations within same station
    for (i, j) in precedence_relations:
        for s in range(m):
            for t1 in range(c):
                for t2 in range(t1): # t2 < t1   
                    clauses.append([-X[i - 1][s], -X[j - 1][s], -B[i - 1][t1], -B[j - 1][t2]])
    
    # Each task starts exactly once
    for i in range(n):
        clause = [B[i][t] for t in range(c)]
        clauses.append(clause)
        for t1 in range(c):
            for t2 in range(t1 + 1, c):
                clauses.append([-B[i][t1], -B[i][t2]])
    
    # If task i finishes before time t, it must have started at or before t - Ex_Time[i]
    for i in range(n):  
        for t in range(c):
            if t - Ex_Time[i] >= 0:
                clause = [-C[i][t]] + [B[i][s] for s in range(t - Ex_Time[i] + 1)]
                clauses.append(clause)
            else:
                clauses.append([-C[i][t]])
    
    # If task i finishes before time t, it must finishes begore time t+1
    for i in range(n): 
        for t in range(c - 1):
            clauses.append([-C[i][t], C[i][t + 1]])

    # If task i finishes before time t, it must not process at time t1 > t
    for i in range(n):
        for t in range(c):
            for t1 in range(t, c):
                clauses.append([-C[i][t], -A[i][t1]])

    # Tasks must start within feasible time windows
    feasible_start_times = []
    for i in range(n):
        feasible_start_times.append(list(range(c - Ex_Time[i] + 1)))
    for i in range(n):
        for t in range(c):
            if t not in feasible_start_times[i]:
                clauses.append([-B[i][t]])
    
    # Task activation (B_{i,t} -> A_{i,t+ε} for ε ∈ {0, ..., t_i-1})
    for i in range(n):
        for t in feasible_start_times[i]:
            for epsilon in range(Ex_Time[i]):
                clauses.append([-B[i][t], A[i][t + epsilon]])
           
    # Task execution (A_{i,t} -> X_{i,s} for s ∈ {1, ..., m})
    # Prevent simultaneous execution on same station
    for i in range(n):
        for j in range(i + 1, n):
            for s in range(m):
                for t in range(c):
                    clauses.append([-X[i][s], -X[j][s], -A[i][t], -A[j][t]])
    
    start = C[-1][-1]
    print(int(peak))
    for t in range(c):
        # Build the pseudo-boolean constraint for time unit t
        lits = []
        coeffs = []
        # Add power consumption terms: w_i * A_{i,t}
        for i in range(n):
            lits.append(A[i][t])
            coeffs.append(W[i])
        # Create PB constraint: sum(coeffs[i] * lits[i]) <= UB
        pb_clauses = PBEnc.leq( lits=lits, weights=coeffs, 
                                bound=int(peak), 
                                top_id=start,
                                encoding = EncType.binmerge)
        # Update variable counter for any new variables created by PBEnc
        if pb_clauses.nv > start:
            start = pb_clauses.nv + 1
            
        # Add the encoded clauses to WCNF
        for clause in pb_clauses.clauses:
            clauses.append(clause)

    return clauses, start

def generate_peak(W, n, m):
    W_sorted = sorted(W, reverse=True)
    UB = sum(W_sorted[i] for i in range(m))
    peak = sum(W_sorted[i] for i in range(n))/n
    return (UB + max(W))/2

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
    ex_time_count = 0
    for line in lines[1:]:
        line = line.strip()
        if not line:  # Skip empty lines
            continue
        
        if ex_time_count < n:
            Ex_Time.append(int(line))
            ex_time_count += 1
        else:
            pair = tuple(map(int, line.split(',')))
            if pair == (-1, -1):
                break
            precedence_relations.add(pair)
    
    return n, W, precedence_relations, Ex_Time

def get_value(n, m, c, model, W, Ex_Time):
    ans_map = [[0 for _ in range(c)] for _ in range(m + 1)]
    start_B = n*m
    start_A = start_B + n*c
    makespan = 0
    for i in range(m):
        for j in range(c):
            for k in range(n):
                if ((model[k*m  + i] > 0) and model[start_B + k*c + j] > 0):
                    for epsilon in range(Ex_Time[k]):
                        ans_map[i][j + epsilon] = W[k]
                    makespan = max(makespan, j + Ex_Time[k])

    for i in range(c):
        ans_map[m][i] = sum(ans_map[j][i] for j in range(m))
    peak = max(ans_map[m][i] for i in range(c))
    return ans_map, peak, makespan

if __name__ == "__main__":
    print("Minimizing Makespan with Peak Power Constraint using SAT Solver")
    import sys
    m = int(sys.argv[2])
    file_name = sys.argv[1]

    n, W, precedence_relations, Ex_Time = input_file(file_name)
    c = max(max(Ex_Time), 2*int(sum(Ex_Time) / m))
    peak = generate_peak(W, n, m)
    print(f"Generated peak power consumption limit: {peak}")
    X, B, A, C = generate_variables(n, m, c)
    clauses, var = list_constrain(n, m, c, precedence_relations, Ex_Time, W, A, B, X, C, peak)
    num_clauses = len(clauses)
    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(clause)

    start_time = time.time()
    is_satisfiable = solver.solve()
    if is_satisfiable:
        model = solver.get_model()
        ans_map, new_peak, makespan = get_value(n, m, c, model, W, Ex_Time)
        print(f"Initial makespan: {makespan} with peak {new_peak}")
        while True:
            for i in range(n):
                solver.add_clause([C[i][makespan - 1]])
            num_clauses += n
            if solver.solve():
                model = solver.get_model()
                ans_map, new_peak, makespan = get_value(n, m, c, model, W, Ex_Time)
                end_time = time.time()
                print(f"Better makespan: {makespan}")
                print(f"Time taken: {end_time - start_time} seconds")
                print(f"Peak power consumption: {new_peak}")
                print("Number of clauses:", num_clauses)
                print("Number of variables:", var)
            else:    
                break
        
        end_time = time.time()
        print(f"Optimal makespan: {makespan}")
        print(f"Time taken: {end_time - start_time} seconds")
        print(f"Peak power consumption: {new_peak}")
        print("Number of clauses:", num_clauses)
        print("Number of variables:", var)
        for line in ans_map:
            print(line[:makespan])
    else:
        print("No solution found within the given peak power constraint.")
        print(f"Time taken: {time.time() - start_time} seconds")
        print("Number of clauses:", num_clauses)
        print("Number of variables:", var)
    solver.delete()