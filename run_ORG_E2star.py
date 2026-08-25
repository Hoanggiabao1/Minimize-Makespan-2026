import os
import subprocess
import re

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

TIMEOUT_LIMIT = 3600
INPUT_FOLDER = "AVG_Peak"
INPUT_FILE_NAME = INPUT_FOLDER + "/ORG_E2star.py"
OUTPUT_FILE_NAME = INPUT_FOLDER + "/Output/incremental_E**.csv"

for i, item in enumerate(file_name):
    family = item[0]
    param1 = str(item[1])
    
    print(f"[{i+1}/{len(file_name)}] Đang chạy: {family} {param1}...", end="", flush=True)
    
    cmd = ["python", "-u", INPUT_FILE_NAME, family, param1]
    
    output_data = ""
    status = "SUCCESS"
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_LIMIT
        )
        print(result.stdout)
            
    except subprocess.TimeoutExpired as e:
        status = "TIMEOUT"
    
        # Giải mã dữ liệu từ bytes sang string (thêm .decode('utf-8', errors='ignore'))
        captured_stdout = e.stdout.decode('utf-8', errors='ignore') if e.stdout else ""
        captured_stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr else ""
        
        # Tìm Initial makespan
        initial_makespan_match = re.search(r"Initial makespan:\s*([+-]?\d+(?:\.\d+)?)", captured_stdout)
        initial_makespan = initial_makespan_match.group(1) if initial_makespan_match else "N/A"
    
        # Tìm tất cả các New makespan xuất hiện trong stdout
        makespan_matches = re.findall(r"New makespan:\s*([+-]?\d+(?:\.\d+)?)", captured_stdout)
    
        # Lấy giá trị New makespan cuối cùng tìm được trong list
        last_makespan = makespan_matches[-1] if makespan_matches else "N/A"
    
        # Ghi vào file output
        with open(OUTPUT_FILE_NAME, "a") as f:
            f.write(f"{family}, _, {param1}, {initial_makespan}, {last_makespan}, -, -, -, -, {status}, >3600\n")

print("\n=== TẤT CẢ CÁC FILE ĐÃ ĐƯỢC XỬ LÝ XONG ===")