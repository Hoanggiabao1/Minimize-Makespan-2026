import os
import subprocess
import re
import time

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

for file_info in file_name:
    file_name = file_info[0]
    m = file_info[1]
    peak = file_info[3] if len(file_info) > 3 else "INF"
    output_file = ""
    optimal = True
    result = ""
    start_time = time.time()
    try:
        res = subprocess.run(["python", "-u", "Peak_UB_LB/D_SAT.py", file_name, str(m)], 
                   timeout=3600, text=True, capture_output=True)
        result = res.stdout
    except subprocess.TimeoutExpired as e:
        result = e.stdout.decode('utf-8', errors='ignore')
        optimal = False
    
    end_time = time.time() - start_time
    print("="*40)
    print (f"Results for {file_name} with m={m}:")
    output_lines = result.splitlines()
    row_csv = [file_name, str(m)] + ["N/A"] * 5
    for output_line in output_lines:
        print (output_line)
    for line in output_lines:
        if "Optimal makespan" in line and optimal:
            makespan_value = line.split()[-1]
            row_csv[2] = makespan_value
        elif "Better makespan" in line and not optimal:
            makespan_value = line.split()[-1]
            row_csv[2] = makespan_value
        elif "Time taken" in line:
            time_value = line.split()[-2]
            row_csv[3] = str(end_time)
        elif "Peak power consumption" in line:
            peak_value = line.split()[-1]
            row_csv[4] = peak_value
        elif "Number of clauses" in line:
            clauses_value = line.split()[-1]
            row_csv[5] = clauses_value
        elif "Number of variables" in line:
            variables_value = line.split()[-1]
            row_csv[6] = variables_value
        
    # viết row vào output.csv
    if optimal:
        row_csv.append("Optimal")
    else:
        row_csv.append("TIMEOUT")
    with open("Peak_UB_LB/Output/D_SAT.csv", "a") as f:
        row_csv_clean = [str(x) if x is not None else "" for x in row_csv]
        f.write(",".join(row_csv_clean) + "\n")