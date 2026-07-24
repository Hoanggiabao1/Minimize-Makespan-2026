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

#Test 1 số thực nghiệm để kiểm tra tính ổn định của code trước khi chạy hết tất cả các file
file_name = [
    # Buxey
    ["Buxey", 7, 47],      # 0
    ["Buxey", 8, 41],      # 1
    ["Buxey", 9, 37],      # 2
    ["Buxey", 10, 34],     # 3
    ["Buxey", 11, 32],     # 4
    ["Buxey", 12, 28],     # 5
    ["Buxey", 13, 27],     # 6
    ["Buxey", 14, 25],     # 7

    # Gunther
    ["Gunther", 6, 84],    # 8
    ["Gunther", 7, 72],    # 9
    ["Gunther", 8, 63],    # 10
    ["Gunther", 9, 54],    # 11
    ["Gunther", 10, 50],   # 12
    ["Gunther", 11, 48],   # 13
    ["Gunther", 12, 44],   # 14
    ["Gunther", 13, 42],   # 15
    ["Gunther", 14, 40],   # 16
    ["Gunther", 15, 40],   # 17

    # Sawyer
    ["Sawyer", 7, 47],    # 18
    ["Sawyer", 8, 41],    # 19
    ["Sawyer", 9, 37],    # 20
    ["Sawyer", 10, 34],   # 21
    ["Sawyer", 11, 31],   # 22
    ["Sawyer", 12, 28],   # 23
    ["Sawyer", 13, 26],   # 24
    ["Sawyer", 14, 25],   # 25

    # Warnecke
    ["Warnecke", 3, 516],   # 26
    ["Warnecke", 4, 387],   # 27
    ["Warnecke", 5, 310],   # 28
    ["Warnecke", 6, 258],   # 29
    ["Warnecke", 7, 222],   # 30
    ["Warnecke", 8, 194],   # 31
    ["Warnecke", 9, 172],   # 32
    ["Warnecke", 10, 155],  # 33
    ["Warnecke", 11, 142],  # 34
    ["Warnecke", 12, 130],  # 35
    ["Warnecke", 13, 120],  # 36
    ["Warnecke", 14, 111],  # 37
    ["Warnecke", 15, 104],  # 38
    ["Warnecke", 16, 98],   # 39
    ["Warnecke", 17, 92],   # 40
    ["Warnecke", 18, 87],   # 41
    ["Warnecke", 19, 84],   # 42
    ["Warnecke", 20, 79],   # 43
    ["Warnecke", 21, 76],   # 44
    ["Warnecke", 22, 73],   # 45
    ["Warnecke", 23, 69],   # 46
    ["Warnecke", 24, 66],   # 47
    ["Warnecke", 25, 64],   # 48
    ["Warnecke", 26, 64],   # 49
    ["Warnecke", 27, 60],   # 50
    ["Warnecke", 28, 59],   # 51
    ["Warnecke", 29, 56],   # 52

    # Lutz2
    ["Lutz2", 9, 54],      # 53
    ["Lutz2", 10, 49],     # 54
    ["Lutz2", 11, 45],     # 55
    ["Lutz2", 12, 41],     # 56
    ["Lutz2", 13, 38],     # 57
    ["Lutz2", 14, 35],     # 58
    ["Lutz2", 15, 33],     # 59
    ["Lutz2", 16, 31],     # 60
    ["Lutz2", 17, 29],     # 61
    ["Lutz2", 18, 28],     # 62
    ["Lutz2", 19, 26],     # 63
    ["Lutz2", 20, 25],     # 64
    ["Lutz2", 21, 24],     # 65
    ["Lutz2", 22, 23],     # 66
    ["Lutz2", 23, 22],     # 67
    ["Lutz2", 24, 21],     # 68
    ["Lutz2", 25, 20],     # 69
    ["Lutz2", 26, 19],     # 70
    ["Lutz2", 27, 19],     # 71
    ["Lutz2", 28, 18],     # 72
]

TIMEOUT_LIMIT = 3600
INPUT_FOLDER = "Peak_UB_LB"
INPUT_FILE_NAME = INPUT_FOLDER + "/Minimize_makespan_SM_Ti,j_E**.py"
OUTPUT_FILE_NAME = INPUT_FOLDER + "/Output/incremental_SM_Ti,j_E**.csv"

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