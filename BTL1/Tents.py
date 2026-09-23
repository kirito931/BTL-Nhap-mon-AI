import tkinter as tk
import time
import tracemalloc
import random
import copy

# --- CẤU HÌNH ĐỀ BÀI (Lưới 5x5) ---
ROWS, COLS = 5, 5
# Danh sách tọa độ các cái cây (row, col)
TREES = [(0, 1), (1, 3), (3, 0), (3, 4), (4, 2)]
# Ràng buộc số lều trên mỗi hàng và cột
ROW_CLUES = [1, 1, 1, 0, 2]
COL_CLUES = [2, 1, 0, 0, 2]

# Các hướng kề cạnh (Lên, Xuống, Trái, Phải)
ADJ_MOVES = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# --- PHẦN 1: LOGIC KIỂM TRA VÀ HEURISTIC ---

def get_valid_tent_spots(r, c):
    """Lấy các vị trí có thể đặt lều xung quanh một cái cây."""
    spots = []
    for dr, dc in ADJ_MOVES:
        nr, nc = r + dr, c + dc
        if 0 <= nr < ROWS and 0 <= nc < COLS and (nr, nc) not in TREES:
            spots.append((nr, nc))
    return spots

def is_touching(tents):
    """Kiểm tra xem có lều nào chạm nhau không (kể cả chéo)."""
    for i, (r1, c1) in enumerate(tents):
        for j, (r2, c2) in enumerate(tents):
            if i != j and abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1:
                return True
    return False

def count_violations(tents):
    """Hàm Heuristic (Đếm lỗi): Tính tổng độ lệch số lều ở hàng/cột và lỗi chạm nhau."""
    if is_touching(tents):
        return 9999 # Lỗi nghiêm trọng

    row_counts = [0] * ROWS
    col_counts = [0] * COLS
    for r, c in tents:
        row_counts[r] += 1
        col_counts[c] += 1

    violations = 0
    for r in range(ROWS):
        violations += abs(row_counts[r] - ROW_CLUES[r])
    for c in range(COLS):
        violations += abs(col_counts[c] - COL_CLUES[c])
        
    return violations

def is_valid_state(tents):
    """Kiểm tra trạng thái đích (Không chạm nhau và khớp clue)."""
    if len(tents) != len(TREES): return False
    return count_violations(tents) == 0

# --- PHẦN 2: CÁC GIẢI THUẬT TÌM KIẾM ---

def solve_dfs():
    """Blind Search: Duyệt đệ quy (Backtracking) từng cây một."""
    path = []
    
    def dfs(tree_idx, current_tents):
        if tree_idx == len(TREES):
            return is_valid_state(current_tents)
            
        tree_r, tree_c = TREES[tree_idx]
        for tr, tc in get_valid_tent_spots(tree_r, tree_c):
            # Tạm thời đặt lều
            new_tents = current_tents + [(tr, tc)]
            path.append((tr, tc, "try", tree_idx))
            
            # Cắt tỉa: Nếu lều chạm nhau hoặc vượt quá clue thì dừng nhánh này
            if is_touching(new_tents):
                path.append((tr, tc, "backtrack", tree_idx))
                continue
                
            row_c = sum(1 for r, _ in new_tents if r == tr)
            col_c = sum(1 for _, c in new_tents if c == tc)
            if row_c > ROW_CLUES[tr] or col_c > COL_CLUES[tc]:
                path.append((tr, tc, "backtrack", tree_idx))
                continue
                
            if dfs(tree_idx + 1, new_tents):
                return True
                
            # Quay lui
            path.append((tr, tc, "backtrack", tree_idx))
            
        return False

    final_tents = []
    dfs(0, final_tents)
    return path

def solve_hill_climbing():
    """Heuristic Search: Leo đồi nhằm giảm dần số lỗi vi phạm (Violations)."""
    path = []
    # Khởi tạo ngẫu nhiên 1 lều cho mỗi cây
    current_tents = []
    for r, c in TREES:
        spots = get_valid_tent_spots(r, c)
        tent = random.choice(spots)
        current_tents.append(tent)
        path.append((tent[0], tent[1], "try", -1))
        
    current_h = count_violations(current_tents)
    
    while current_h > 0:
        neighbors = []
        # Sinh các trạng thái kề bằng cách dời lều của 1 cây sang hướng khác
        for i, (tree_r, tree_c) in enumerate(TREES):
            for new_tent in get_valid_tent_spots(tree_r, tree_c):
                if new_tent != current_tents[i]:
                    candidate_tents = current_tents.copy()
                    candidate_tents[i] = new_tent
                    h = count_violations(candidate_tents)
                    neighbors.append((h, i, new_tent))
                    
        # Chọn trạng thái kề tốt nhất
        neighbors.sort(key=lambda x: x[0])
        best_h, best_idx, best_tent = neighbors[0]
        
        if best_h < current_h:
            # Di chuyển (xóa lều cũ trong UI, đặt lều mới)
            old_tent = current_tents[best_idx]
            path.append((old_tent[0], old_tent[1], "backtrack", best_idx))
            
            current_tents[best_idx] = best_tent
            current_h = best_h
            path.append((best_tent[0], best_tent[1], "try", best_idx))
        else:
            # Random Restart nếu bị kẹt (Local Optimum)
            current_tents = []
            for r, c in TREES:
                spots = get_valid_tent_spots(r, c)
                tent = random.choice(spots)
                current_tents.append(tent)
                path.append((tent[0], tent[1], "try", -1))
            current_h = count_violations(current_tents)
            
    return path

# --- PHẦN 3: GIAO DIỆN TRỰC QUAN (GUI) ---

class TentsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tents and Trees Solver")
        self.cells = {}
        self.path = []
        self.anim_index = 0
        
        self.create_ui()

    def create_ui(self):
        # Khu vực Canvas
        self.canvas = tk.Canvas(self.root, width=(COLS+1)*60, height=(ROWS+1)*60, bg="#E8F5E9")
        self.canvas.pack(pady=10, padx=10)
        self.draw_board()
        
        # Dashboard đo lường
        self.metrics_frame = tk.Frame(self.root)
        self.metrics_frame.pack(pady=5)
        self.lbl_time = tk.Label(self.metrics_frame, text="Time: 0.0000s", font=("Arial", 10, "bold"), fg="#D32F2F")
        self.lbl_time.grid(row=0, column=0, padx=10)
        self.lbl_mem = tk.Label(self.metrics_frame, text="Peak Mem: 0 KB", font=("Arial", 10, "bold"), fg="#1976D2")
        self.lbl_mem.grid(row=0, column=1, padx=10)
        self.lbl_steps = tk.Label(self.metrics_frame, text="Steps: 0", font=("Arial", 10, "bold"), fg="#388E3C")
        self.lbl_steps.grid(row=0, column=2, padx=10)

        # Nút điều khiển
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        self.btn_dfs = tk.Button(control_frame, text="Chạy DFS", bg="#FF9800", fg="white", 
                                 command=lambda: self.execute_algo("DFS"), font=("Arial", 10, "bold"), width=12)
        self.btn_dfs.grid(row=0, column=0, padx=5)
        
        self.btn_hc = tk.Button(control_frame, text="Hill Climbing", bg="#9C27B0", fg="white", 
                                command=lambda: self.execute_algo("HC"), font=("Arial", 10, "bold"), width=12)
        self.btn_hc.grid(row=0, column=1, padx=5)

    def draw_board(self):
        self.canvas.delete("all")
        self.cells.clear()
        
        # Vẽ lưới và Clues
        for r in range(ROWS):
            self.canvas.create_text(20, r*60 + 50, text=str(ROW_CLUES[r]), font=("Arial", 14, "bold"), fill="#1B5E20")
        for c in range(COLS):
            self.canvas.create_text(c*60 + 70, 20, text=str(COL_CLUES[c]), font=("Arial", 14, "bold"), fill="#1B5E20")
            
        for r in range(ROWS):
            for c in range(COLS):
                x0, y0 = c * 60 + 40, r * 60 + 40
                x1, y1 = x0 + 60, y0 + 60
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="#81C784", fill="#C8E6C9", width=2)
                
                # Nếu là cây, vẽ icon cây
                if (r, c) in TREES:
                    self.canvas.create_text(x0+30, y0+30, text="🌲", font=("Arial", 24))
                
                # Lưu text placeholder để vẽ lều
                self.cells[(r, c)] = self.canvas.create_text(x0+30, y0+30, text="", font=("Arial", 24))

    def execute_algo(self, algo_name):
        self.btn_dfs.config(state=tk.DISABLED)
        self.btn_hc.config(state=tk.DISABLED)
        self.draw_board()
        self.root.update()
        
        tracemalloc.start()
        start_time = time.time()
        
        if algo_name == "DFS":
            self.path = solve_dfs()
        else:
            self.path = solve_hill_climbing()
            
        elapsed_time = time.time() - start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        self.lbl_time.config(text=f"Time: {elapsed_time:.4f}s")
        self.lbl_mem.config(text=f"Peak Mem: {peak / 1024:.2f} KB")
        self.lbl_steps.config(text=f"Steps: {len(self.path)}")
        
        self.anim_index = 0
        self.animate()

    def animate(self):
        if self.anim_index < len(self.path):
            r, c, action, _ = self.path[self.anim_index]
            
            if action == "try":
                self.canvas.itemconfig(self.cells[(r, c)], text="⛺")
            elif action == "backtrack":
                self.canvas.itemconfig(self.cells[(r, c)], text="")
                
            self.anim_index += 1
            # Tốc độ diễn hoạt cố định 150ms
            self.root.after(150, self.animate) 
        else:
            self.btn_dfs.config(state=tk.NORMAL)
            self.btn_hc.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = TentsApp(root)
    root.mainloop()