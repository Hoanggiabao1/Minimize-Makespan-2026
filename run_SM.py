import os
import subprocess
import re

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
    ["LUTZ2", 24, 21]       # 88
]

#Test 1 số thực nghiệm để kiểm tra tính ổn định của code trước khi chạy hết tất cả các file
file_name1 = [
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

TIMEOUT_LIMIT = 3600
INPUT_FOLDER = "Peak_UB_LB"
INPUT_FILE_NAME = INPUT_FOLDER + "/Minimize_makespan_SM.py"
OUTPUT_FILE_NAME = INPUT_FOLDER + "/Output/incremental_SM.csv"

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