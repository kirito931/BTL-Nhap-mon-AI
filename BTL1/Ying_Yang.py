import tkinter as tk
from collections import deque
import random
import time
import tracemalloc
import copy

# --- CẤU HÌNH NGÂN HÀNG ĐỀ (PUZZLE POOL) ---
ROWS, COLS = 4, 4

PUZZLE_POOL = [
    # Đề 1 (Mức độ trung bình)
    [
        [0, 0, 1, 0],
        [0, 2, 0, 0],
        [0, 0, 0, 2],
        [1, 0, 0, 0]
    ],
    # Đề 2 (Khó hơn một chút)
    [
        [1, 0, 0, 2],
        [0, 0, 0, 0],
        [0, 1, 2, 0],
        [0, 0, 0, 0]
    ],
    # Đề 3 (Đòi hỏi thuật toán lùi nhiều bước)
    [
        [0, 1, 0, 0],
        [0, 0, 0, 2],
        [1, 0, 0, 0],
        [0, 0, 2, 0]
    ]
]

# --- PHẦN 1: LOGIC VÀ HEURISTIC ---

def count_2x2_errors(grid):
    errors = 0
    for r in range(ROWS - 1):
        for c in range(COLS - 1):
            val = grid[r][c]
            if val != 0 and val == grid[r+1][c] == grid[r][c+1] == grid[r+1][c+1]:
                errors += 1
    return errors

def count_components(grid, color):
    visited = set()
    components = 0
    for r in range(ROWS):
        for c in range(COLS):
            if grid[r][c] == color and (r, c) not in visited:
                components += 1
                queue = deque([(r, c)])
                visited.add((r, c))
                while queue:
                    curr_r, curr_c = queue.popleft()
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = curr_r + dr, curr_c + dc
                        if 0 <= nr < ROWS and 0 <= nc < COLS:
                            if grid[nr][nc] == color and (nr, nc) not in visited:
                                visited.add((nr, nc))
                                queue.append((nr, nc))
    return components

def calculate_heuristic(grid):
    err_2x2 = count_2x2_errors(grid)
    comp_black = count_components(grid, 1)
    err_black = (comp_black - 1) if comp_black > 0 else 0
    comp_white = count_components(grid, 2)
    err_white = (comp_white - 1) if comp_white > 0 else 0
    return err_2x2 + err_black + err_white

def is_fully_valid(grid):
    if any(0 in row for row in grid): return False
    return calculate_heuristic(grid) == 0

# --- PHẦN 2: THUẬT TOÁN TÌM KIẾM ---

def solve_dfs(start_grid):
    path = []
    grid = copy.deepcopy(start_grid)
    
    def dfs(r, c):
        while r < ROWS and start_grid[r][c] != 0:
            c += 1
            if c == COLS:
                c = 0
                r += 1
        if r == ROWS:
            return is_fully_valid(grid)

        next_c = c + 1
        next_r = r
        if next_c == COLS:
            next_c = 0
            next_r += 1

        for color in [1, 2]:
            grid[r][c] = color
            path.append((r, c, color, "try"))
            if count_2x2_errors(grid) == 0:
                if dfs(next_r, next_c):
                    return True
            grid[r][c] = 0
            path.append((r, c, 0, "backtrack"))
        return False

    dfs(0, 0)
    return path, grid

def solve_hill_climbing(start_grid):
    path = []
    while True:
        grid = copy.deepcopy(start_grid)
        for r in range(ROWS):
            for c in range(COLS):
                if grid[r][c] == 0:
                    grid[r][c] = random.choice([1, 2])
                    path.append((r, c, grid[r][c], "try"))

        current_h = calculate_heuristic(grid)
        stuck = False
        while not stuck and current_h > 0:
            neighbors = []
            for r in range(ROWS):
                for c in range(COLS):
                    if start_grid[r][c] == 0:
                        original_color = grid[r][c]
                        new_color = 2 if original_color == 1 else 1
                        grid[r][c] = new_color
                        h = calculate_heuristic(grid)
                        neighbors.append((h, r, c, new_color))
                        grid[r][c] = original_color 
            
            neighbors.sort(key=lambda x: x[0])
            best_h, best_r, best_c, best_color = neighbors[0]
            
            if best_h < current_h:
                grid[best_r][best_c] = best_color
                current_h = best_h
                path.append((best_r, best_c, best_color, "try"))
            else:
                stuck = True 
                
        if current_h == 0:
            return path, grid 

# --- PHẦN 3: GIAO DIỆN VÀ ĐO LƯỜNG (GUI) ---

class YinYangApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Yin-Yang: DFS vs Hill Climbing")
        self.current_puzzle = copy.deepcopy(PUZZLE_POOL[0])
        self.cells = {}
        self.path = []
        self.anim_index = 0
        
        self.create_ui()

    def create_ui(self):
        # Khu vực Canvas (Bản đồ)
        self.canvas = tk.Canvas(self.root, width=COLS*60, height=ROWS*60, bg="#EFEBE9")
        self.canvas.pack(pady=10, padx=10)
        self.draw_grid(self.current_puzzle)
        
        # Dashboard đo lường (Số liệu Báo cáo)
        self.metrics_frame = tk.Frame(self.root)
        self.metrics_frame.pack(pady=5)
        self.lbl_time = tk.Label(self.metrics_frame, text="Time: 0.0000s", font=("Arial", 10, "bold"), fg="#D32F2F")
        self.lbl_time.grid(row=0, column=0, padx=10)
        self.lbl_mem = tk.Label(self.metrics_frame, text="Peak Mem: 0 KB", font=("Arial", 10, "bold"), fg="#1976D2")
        self.lbl_mem.grid(row=0, column=1, padx=10)
        self.lbl_steps = tk.Label(self.metrics_frame, text="Steps: 0", font=("Arial", 10, "bold"), fg="#388E3C")
        self.lbl_steps.grid(row=0, column=2, padx=10)

        # Nút điều khiển (Controls)
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        self.btn_dfs = tk.Button(control_frame, text="Chạy DFS", bg="#FF9800", fg="white", 
                                 command=lambda: self.execute_algo("DFS"), font=("Arial", 10, "bold"), width=12)
        self.btn_dfs.grid(row=0, column=0, padx=5)
        
        self.btn_hc = tk.Button(control_frame, text="Hill Climbing", bg="#9C27B0", fg="white", 
                                command=lambda: self.execute_algo("HC"), font=("Arial", 10, "bold"), width=12)
        self.btn_hc.grid(row=0, column=1, padx=5)

        self.btn_random = tk.Button(control_frame, text="Tạo đề mới", bg="#2196F3", fg="white", 
                                command=self.generate_new_puzzle, font=("Arial", 10, "bold"), width=12)
        self.btn_random.grid(row=0, column=2, padx=5)

    def generate_new_puzzle(self):
        """Lấy một đề ngẫu nhiên từ thư viện đề."""
        new_puzzle = random.choice(PUZZLE_POOL)
        # Đảm bảo không trùng đề hiện tại nếu có thể
        while len(PUZZLE_POOL) > 1 and new_puzzle == self.current_puzzle:
            new_puzzle = random.choice(PUZZLE_POOL)
            
        self.current_puzzle = copy.deepcopy(new_puzzle)
        self.draw_grid(self.current_puzzle)
        
        # Reset các thông số
        self.lbl_time.config(text="Time: 0.0000s")
        self.lbl_mem.config(text="Peak Mem: 0 KB")
        self.lbl_steps.config(text="Steps: 0")

    def draw_grid(self, grid_data):
        self.canvas.delete("all")
        for r in range(ROWS):
            for c in range(COLS):
                x0, y0 = c * 60, r * 60
                x1, y1 = x0 + 60, y0 + 60
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="#8D6E63", width=2)
                
                val = grid_data[r][c]
                if val != 0:
                    fill_color = "#212121" if val == 1 else "#FFFFFF"
                    self.cells[(r, c)] = self.canvas.create_oval(x0+10, y0+10, x1-10, y1-10, fill=fill_color, outline="black")

    def execute_algo(self, algo_name):
        # Khóa nút khi đang chạy
        self.btn_dfs.config(state=tk.DISABLED)
        self.btn_hc.config(state=tk.DISABLED)
        self.btn_random.config(state=tk.DISABLED)
        self.draw_grid(self.current_puzzle)
        self.root.update()
        
        tracemalloc.start()
        start_time = time.time()
        
        if algo_name == "DFS":
            self.path, final_grid = solve_dfs(self.current_puzzle)
        else:
            self.path, final_grid = solve_hill_climbing(self.current_puzzle)
            
        elapsed_time = time.time() - start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Cập nhật số liệu hiển thị
        self.lbl_time.config(text=f"Time: {elapsed_time:.4f}s")
        self.lbl_mem.config(text=f"Peak Mem: {peak / 1024:.2f} KB")
        self.lbl_steps.config(text=f"Steps: {len(self.path)}")
        
        self.anim_index = 0
        self.animate()

    def animate(self):
        if self.anim_index < len(self.path):
            r, c, color, action = self.path[self.anim_index]
            x0, y0 = c * 60, r * 60
            x1, y1 = x0 + 60, y0 + 60
            
            if (r, c) in self.cells:
                self.canvas.delete(self.cells[(r, c)])
                
            if action == "try":
                fill_color = "#212121" if color == 1 else "#FFFFFF"
                self.cells[(r, c)] = self.canvas.create_oval(x0+10, y0+10, x1-10, y1-10, fill=fill_color, outline="red", width=2)
                
            self.anim_index += 1
            
            # Tốc độ diễn hoạt cố định 200ms
            self.root.after(200, self.animate) 
        else:
            # Mở khóa các nút khi chạy xong
            self.btn_dfs.config(state=tk.NORMAL)
            self.btn_hc.config(state=tk.NORMAL)
            self.btn_random.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = YinYangApp(root)
    root.mainloop()