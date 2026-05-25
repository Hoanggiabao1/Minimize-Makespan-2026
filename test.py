# --- 1. Khởi tạo dữ liệu ---
adj = [[0, 1], [1, 2], [2, 3]]
temp = {0: [1], 1: [2], 2: [3], 3: []}
neighbors = {u: {} for u in temp}
reversed_neighbors = {u: {} for u in temp}

for u, v in adj:
    neighbors[u][v] = 1
    reversed_neighbors[v][u] = 1

ran = {u: 0 for u in temp}

# --- 2. Hàm sửa đổi điều kiện append ---
# Thêm tham số root_i để lưu lại đỉnh bắt đầu ban đầu
def delv(i, temp, root_i=None):
    global adj, neighbors, reversed_neighbors, ran
    
    if root_i is None:
        root_i = i
        
    if len(temp[i]) == 0:
        return []
    if ran[i] == 1:
        return temp[i]
        
    for j in temp[i]:
        con = delv(j, temp, root_i)
        if con:
            for k in con:
                if i == root_i: 
                    if [i, k] not in adj:
                        adj.append([i, k])
                        neighbors[i][k] = 1
                        reversed_neighbors[k][i] = 1
                
               if k not in temp[i]:
                    temp[i].append(k)
    ran[i] = 1
    return temp[i]

# --- 3. Kiểm tra kết quả ---
print("Mảng adj BAN ĐẦU: ", adj)

# Gọi hàm với đỉnh bắt đầu là 0
delv(0, temp)

print("Mảng adj SAU KHI CHẠY:", adj)