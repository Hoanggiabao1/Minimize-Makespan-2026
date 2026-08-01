from math import inf
import math
import time
import signal
from datetime import datetime
import signal
from numpy import var
from pysat.solvers import Cadical195
import fileinput
from tabulate import tabulate
import webbrowser
import sys
from pysat.pb import PBEnc, EncType
import csv

# Sample input parameters
n = 0
val = 0
cons = 0
sol = 0
solbb = 0
type = 1

# Global variables for tracking results
best_result = None
current_instance_id = 0
start_time_global = 0
neighbors = [[ 0 for i in range(n)] for j in range(n)]
reversed_neighbors = [[ 0 for i in range(n)] for j in range(n)]
visited = [False for i in range(n)]
toposort = []
clauses = []
time_list = []
ran = []
adj = []
forward = [0 for i in range(n)]
var_map = {}
var_counter = 0
W = []

def read_input(filename):
    cnt = 0
    global n, adj, neighbors, reversed_neighbors, time_list, forward, W
    temp = []
    with open('data/' + filename + '.IN2', 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                if cnt == 0:
                    n = int(line)
                    for i in range(n):
                        temp.append([])
                        ran.append(0)
                elif cnt <= n: # type: ignore
                    time_list.append(int(line))
                else:
                    line = line.split(",")
                    if(line[0] != "-1" and line[1] != "-1"):
                        a, b = int(line[0]) - 1, int(line[1]) - 1
                        adj.append([a, b])
                        neighbors[a][b] = 1
                        reversed_neighbors[b][a] = 1
                        temp[a].append(b)
                    else:
                        break
                cnt = cnt + 1
    for i in range(n):
        delv(i, temp)
        
    with open('task_power/' + filename + '.txt', 'r') as k:
        W = [int(line.strip()) for line in k if line.strip()]

def reset(idx):
    global n, m, val, cons, sol, solbb, type, filename, W, neighbors, reversed_neighbors, visited, toposort, clauses, time_list, adj, forward, var_map, var_counter, current_instance_id, ran
    current_instance_id = idx
    m = idx[1]
    val = 0
    cons = 0
    sol = 0
    solbb = 0
    type = 1
    var_counter = 0
    var_map = {}
    W = [int(line.strip()) for line in open('task_power/'+idx[0]+'.txt')]
    neighbors = [[ 0 for i in range(200)] for j in range(200)]
    reversed_neighbors = [[ 0 for i in range(200)] for j in range(200)]
    visited = [False for i in range(200)]
    toposort = []
    clauses = []
    time_list = []
    adj = []
    ran = []
    forward = [0 for i in range(200)]


def delv(i, temp):
    global adj, neighbors, reversed_neighbors, ran
    if len(temp[i]) == 0:
        return []
    if ran[i] == 1:
        return temp[i]
    for j in temp[i]:
        con = delv(j, temp)
        if con:
            for k in con:
                if [i, k] not in adj:
                    adj.append([i, k])
                    neighbors[i][k] = 1
                    reversed_neighbors[k][i] = 1
                    temp[i].append(k)
    ran[i] = 1
    return temp[i]


def generate_variables(n,m,c):
    global var_counter
    x = [[j*m+i+1 for i in range (m)] for j in range(n)]
    a = [[m*n + j*c + i + 1 for i in range (c)] for j in range(n)]
    s = []
    cnt = m*n + c*n + 1
    for j in range(n):
        tmp = []
        for i in range(c - time_list[j] + 1):
            tmp.append(cnt)
            cnt = cnt + 1
        s.append(tmp)
    var_counter = cnt
    return x, a, s

def dfs(v):
    visited[v] = True
    for i in range(n):
        if(neighbors[v][i] == 1 and visited[i] == False):
            dfs(i)
    toposort.append(v)

def preprocess(n,m,c,time_list,adj):
    earliest_start = [[-9999999 for _ in range(m)] for _ in range(n)]
    latest_start = [[99999999 for _ in range(m)] for _ in range(n)]
    ip1 = [[0 for _ in range(m)] for _ in range(n)]
    test_ip1 = [[0 for _ in range(m)] for _ in range(n)]
    ip2 = [[[0 for _ in range(c)] for _ in range(m)] for _ in range(n)]
    # Compute earliest possible starting date and assigned workstation
    for i in range(n):
        if not visited[i]:
            dfs(i)
    toposort.reverse()
    for j in toposort:
        k = 0
        earliest_start[j][k] = 0
        for i in range(n):
            if neighbors[i][j] == 1:

                earliest_start[j][k] = max(earliest_start[j][k], earliest_start[i][k] + time_list[i])

                while(earliest_start[j][k] > c - time_list[j]):
                    ip1[j][k] = 1
                    # print('X '+str(j+1)+' '+str(k+1))
                    k = k + 1
                    earliest_start[j][k] = max(0, earliest_start[i][k] + time_list[i])

                if earliest_start[j][k] <= c - time_list[j] :
                    for t in range(earliest_start[j][k]):
                        
                        if(ip2[j][k][t] == 0):
                            # with open("output.txt", "a") as output_file: 
                            #     sys.stdout = output_file  
                            #     print(j+1, k+1, t, file=output_file) 
                            ip2[j][k][t] = 1
    toposort.reverse()
    for j in toposort:
        k = m-1
        latest_start[j][k] = c - time_list[j]
        for i in range(n):
            if(neighbors[j][i] == 1): 
                latest_start[j][k] = min(latest_start[j][k], latest_start[i][k] - time_list[j])
                while(latest_start[j][k] < 0):
                    ip1[j][k] = 1
                    # print('X '+str(j+1)+' '+str(k+1))
                    k = k - 1
                    latest_start[j][k] = min(c - time_list[j], latest_start[i][k] - time_list[j])
                
                if(latest_start[j][k] >= 0):
                        for t in range(latest_start[j][k] + 1, c):
                            
                            if(ip2[j][k][t] == 0):
                                ip2[j][k][t] = 1
    # for j in range(n):
    #     for k in range(m):
    #         for t in range(c):
                # if(ip1[j][k] == 1):
                #     continue
                # if(j == 11 or j == 14):
                #     print(f"task {j+1} in machine {k+1} time {t+1}: {ip2[j][k][t]}")
                # if(j == 0 and k == 2):
                #     print(f"task {j+1} in machine {k+1} time {t+1}: {ip2[j][k][t]}")
    # print(ip2)
    return ip1,ip2

def get_key(value):
    for key, value in var_map.items():
        if val == value:
            return key
    return None

def get_var(name, *args):
    global var_counter
    key = (name,) + args

    if key not in var_map:
        var_counter += 1
        var_map[key] = var_counter
    return var_map[key]

def set_var(var, name, *args):
    key = (name,) + args
    if key not in var_map:
        var_map[key] = var
    return var_map[key]

def generate_clauses(n,m,c,time_list,adj,ip1,ip2,X,S,A, peak):
    global clauses
    global var_map
    global var_counter

    #Sequencial counter for R[j][k]: R[j][k] is true if task j assigned to any machine from 0 to k
    for j in range(n):
        # X[j][0] <-> R[j][0] cse-1
        set_var(X[j][0], "R", j, 0)
        for k in range(1,m-1):
            if ip1[j][k] == 1:
                # If task j cannot be assigned to machine k, then R[j][k] is equivalent to R[j][k-1]
                set_var(get_var("R", j, k-1), "R", j, k)
            else:
                # R[j][k-1] -> R[j][k] cse-2
                clauses.append([-get_var("R", j, k-1), get_var("R", j, k)])
                # X[j][k] -> R[j][k] cse-3
                clauses.append([-X[j][k], get_var("R", j, k)])
                # X[j][k] -> -R[j][k-1] cse-4
                clauses.append([-X[j][k], -get_var("R", j, k-1)])
                # R[j][k] -> X[j][k] ∨ R[j][k-1] cse-5
                clauses.append([X[j][k], get_var("R", j, k-1), -get_var("R", j, k)])
        
        # last machine
        if ip1[j][m-1] == 1:
            # If task j cannot be assigned to machine m, then task j must be assigned to some machine before m-1
            clauses.append([get_var("R", j, m-2)])
        else:
            # R[j][m-1] v X[j][m] cse-5a
            clauses.append([get_var("R", j, m-2), X[j][m-1]])
            # X[j][m] -> -R[j][m - 1] cse-4 (last machine)
            clauses.append([-get_var("R", j, m-2), -X[j][m-1]])
        

    for (i,j) in adj:
        for k in range(m-1):
            if ip1[i][k+1] == 1:
                continue
            # precedence constraint: (i < j) X[i][k+1] -> -R[j][k] cse-6
            clauses.append([-get_var("R", j, k), -X[i][k+1]])

    # Sequencial counter for T[j][t] represents "task j starts at time t or earlier"
    for j in range(n):
        last_t = c-time_list[j]
        # Special case: Full cycle tasks (only one feasible start time: t=0)
        if last_t == 0:
            # Force the task to start at t=0 (equivalent to original constraint #4)
            clauses.append([S[j][0]])
        else:
            # First time slot S[j][0] <-> T[j][0] cse-7
            set_var(S[j][0], "T", j, 0)
            
            # Intermediate time slots
            for t in range(1, last_t):
                # T[j][t-1] -> T[j][t] cse-8
                clauses.append([-get_var("T", j, t-1), get_var("T", j, t)])
                # S[j][t] -> T[j][t] cse-9
                clauses.append([-S[j][t], get_var("T", j, t)])
                # S[j][t] -> -T[j][t-1] cse-10
                clauses.append([-S[j][t], -get_var("T", j, t-1)])
                # T[j][t] -> (T[j][t-1] ∨ S[j][t]) cse-11
                clauses.append([S[j][t], get_var("T", j, t-1), -get_var("T", j, t)])
            
            # Last time slot (ensures at least one start time)
            # S[j][last_t] V T[j][last_t-1] cse-11a
            clauses.append([get_var("T", j, last_t-1), S[j][last_t]])
            # S[j][last_t] -> T[j][last_t-1] cse-10 (last time slot)
            clauses.append([-get_var("T", j, last_t-1), -S[j][last_t]])

    #S[j][t] -> A[j][t+l] for l in range(time_list[j]) cse-12
    for j in range(n):
        for t in range (c-time_list[j]+1):
            for l in range (time_list[j]):
                #if(time_list[j] >= c/2 and t+l >= c-time_list[j] and t+l < time_list[j]):
                #    continue
                clauses.append([-S[j][t], A[j][t+l]])
    
    # cse-13
    for i,j in adj:
        for k in range(m):
            if ip1[i][k] == 1 or ip1[j][k] == 1:
                continue
            left_bound = time_list[i] - 1
            right_bound = c - time_list[j]

            clauses.append([-X[i][k], -X[j][k], -get_var("T", j, left_bound)])
            for t in range (left_bound + 1, right_bound):
                t_i = t - time_list[i]+1
                # (X[i][k] ^ X[j][k] ^ T[j][t]) -> -S[i][t-d_i+1] cse-13
                clauses.append([-X[i][k], -X[j][k], -get_var("T", j, t), -S[i][t_i]])
            for t in range (max(0,right_bound - time_list[i] + 1), c - time_list[i] + 1):
                # (X[i][k] ^ X[j][k] ^ T[j][c-time_list[j]-1]) -> -S[i][t] cse-13a
                # Như ràng buộc trên nhưng t = last_j
                clauses.append([-X[i][k], -X[j][k], -S[i][t], -get_var("T",j,c-time_list[j]-1)])
    
    #(X[i][k] ^ X[j][k]) -> (A[i][t] ^ A[j][t]) cse-14
    for i in range(n-1):
        for j in range(i+1,n):
            for k in range (m):
                if ip1[i][k] == 1 or ip1[j][k] == 1 :
                    continue
                for t in range(c):
                    clauses.append([-X[i][k], -X[j][k], -A[i][t], -A[j][t]])

    # cse-15-16:
    for j in range(n):
        for k in range(m):
            if ip1[j][k] == 1:
                # -X[j][k] if First(i) > k ∨ Last(i) < k cse-15 
                clauses.append([-X[j][k]])
                continue
            for t in range(c - time_list[j] +1):
                if ip2[j][k][t] == 1:
                    # X[j][k] -> -S[j][t] cse-16
                    clauses.append([-X[j][k], -S[j][t]])

    #cse-17
        for j in range(n):
            if(time_list[j] >= c/2):
                for t in range(c-time_list[j],time_list[j]):
                    clauses.append([A[j][t]])

    # Power peak constraints
    var = var_counter + 1
    for t in range(c):
        variables = []
        weight = []
        for i in range(n):
            variables.append(A[i][t])
            weight.append(W[i])
        pb_clauses = PBEnc.leq( lits=variables, weights=weight, 
                                bound=peak, 
                                top_id=var, encoding=EncType.binmerge)
        # Update variable counter for any new variables created by PBEnc
        if pb_clauses.nv > var:
            var = pb_clauses.nv + 1
            
        # Add the encoded clauses
        for clause in pb_clauses.clauses:
            clauses.append(clause)
            
    return clauses

def solve(solver):
    if solver.solve():
        model = solver.get_model()
        return model
    else:
        return None

def get_value(solution, c):
    if solution is None:
        return 100, []
    else:
        x = [[  solution[j*m+i] for i in range (m)] for j in range(n)]
        a = [[  solution[m*n + j*c + i ] for i in range (c)] for j in range(n)]
        s = []
        cnt = m*n + c*n
        for j in range(n):
            tmp = []
            for i in range(c - time_list[j] + 1):
                tmp.append(solution[cnt])
                cnt += 1
            for i in range(c - time_list[j] + 1, c):
                tmp.append(-1)
            s.append(tmp)
        
        value = 0
        table = [[0 for t in range(c)] for k in range(m + 1)]
        for k in range(m):
            for t in range(c):
                for j in range(n):
                    if x[j][k] > 0 and s[j][t] > 0:
                        for l in range(time_list[j]):
                            table[k][t+l] += W[j]
                        print(f"Task {j+1} assigned to machine {k+1} at time {t}")
                        value = max(value, t + time_list[j])
        
        table[m] = [sum(table[j][t] for j in range(m)) for t in range(c)]

        return value, [table[i][:value] for i in range(m)]

def optimal(X, S, A, n, m, makespan, sol, start_time, peak):
    global filename
    
    ip1, ip2 = preprocess(n, m, makespan, time_list, adj)
    clauses = generate_clauses(n, m, makespan, time_list, adj, ip1, ip2, X, S, A, peak)

    solver = Cadical195()
    print("Initial makespan:", makespan)
    print("Max peak:", peak)
    for clause in clauses:
        solver.add_clause(clause)

    model = solve(solver)
    sol += 1
    if model is None:
        print("Initial solve timed out!")
        return 0, [], var_counter, clauses, "TIMEOUT", sol
     
    result = get_value(model, makespan)
    bestValue, ansmap = result
    print("New makespan:", bestValue, end="\r")
    
    while (True):
        for i in range(n):
            if bestValue - time_list[i] - 1 < 0:
                print("Optimal solution found.")
                return bestValue, ansmap, var_counter, clauses, "Optimal", sol
            solver.add_clause([get_var("T", i, bestValue - time_list[i] - 1)])
        
        model = solve(solver)        
        sol += 1
        if model is None:
            print("No better solution found.")
            return bestValue, ansmap, var_counter, clauses, "Optimal", sol
        
        bestValue, ansmap = get_value(model, makespan)
        print("New makespan:", bestValue, end="\r") 

def write_fancy_table_to_csv(ins, n, m, c, val, cons, sol, makespan, peak, status, time_elapsed, filename="incremental_binary_merger.csv"):
    global best_result
    
    # Write to CSV
    with open("Peak_UB_LB/Output/" + filename, "a", newline='') as f:
        writer = csv.writer(f)
        row = []
        row.append(ins)
        row.append(str(n))
        row.append(str(m))
        row.append(str(c))
        row.append(str(makespan))
        row.append(str(peak))
        row.append(str(val))
        row.append(str(cons))
        row.append(str(sol))
        row.append(status)
        row.append(str(time_elapsed))
        writer.writerow(row)

def calculate_peak():
    W_sorted = sorted(W, reverse=True)
    UB = sum(W_sorted[i] for i in range(m))
    AVG = (sum(W_sorted[i] for i in range(n)) / n) * m
    LB = max(W_sorted)
    peak = (UB + LB) / 2
    makespan = max(max(time_list), (sum(time_list[i] for i in range(n)) // m)*2)
    return int(peak), makespan

if __name__ == "__main__":
    filename = sys.argv[1]
    m = int(sys.argv[2])
    reset([filename, m])
    read_input(filename)
    sol = 0
    startime = time.time()
    peak, makespan = calculate_peak()
    X, A, S = generate_variables(n,m,makespan)
    bestValue, ansmap, var, clauses, status, sol = optimal(X,S,A,n,m,makespan,sol,startime, peak)
    for line in ansmap:
        print(line)
    endtime = time.time()
    if status == "Optimal":
        print(f"Optimal makespan: {bestValue}")
        write_fancy_table_to_csv(filename, n, m, makespan, var, len(clauses), sol, bestValue, peak, status, endtime - startime)
    else:
        print("No optimal solution found.")
        write_fancy_table_to_csv(filename, n, m, makespan, var, len(clauses), sol, bestValue, peak, status, endtime - startime)