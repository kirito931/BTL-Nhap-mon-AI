"""
MODULE: board.py
MỤC ĐÍCH:
1. Đọc và nạp các file bài toán từ thư mục inputs/.
2. Quản lý trạng thái bàn cờ (TentsBoard).
3. Kiểm tra tính hợp lệ của các nước đi (ràng buộc 8 hướng, số lều hàng/cột).
4. Ghi nhận nhật ký bước đi (history_steps) phục vụ demo Step-by-Step.
5. Cung cấp hàm Heuristic (count_conflicts) cho thuật toán Hill Climbing.
"""

import os


def load_input_file(filepath: str):
    """
    Đọc file .txt định dạng trực quan:
    - Dòng 1: Rows Cols
    - Dòng 2: Chỉ số các cột
    - Dòng 3 trở đi: [Chỉ số hàng] [Các ô trên hàng]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        # Lọc bỏ comment và dòng trống
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if len(lines) < 3:
        raise ValueError(f"File {filepath} không đúng cấu trúc tối thiểu.")

    # 1. Kích thước
    rows, cols = map(int, lines[0].split())

    # 2. Ràng buộc cột
    col_constraints = list(map(int, lines[1].split()))

    # 3. Ràng buộc hàng và ma trận ô cờ
    row_constraints = []
    grid = []
    trees = []

    for r in range(rows):
        tokens = lines[2 + r].split()
        row_clue = int(tokens[0])
        row_constraints.append(row_clue)

        grid_row = tokens[1:]
        grid.append(grid_row)

        for c, cell in enumerate(grid_row):
            if cell == "T":
                trees.append((r, c))

    return {
        "rows": rows,
        "cols": cols,
        "row_constraints": row_constraints,
        "col_constraints": col_constraints,
        "grid": grid,
        "trees": trees,
    }


class TentsBoard:
    EMPTY = "."
    TREE = "T"
    TENT = "A"
    GRASS = "G"

    # 4 hướng trực giao (Lều chỉ được ghép với Cây theo 4 hướng này)
    ORTHO_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    # 8 hướng xung quanh (Hai lều không được chạm nhau ở cả 8 hướng)
    ALL_8_DIRS = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)
    ]

    def __init__(self, rows: int, cols: int, row_constraints: list, col_constraints: list, grid: list, trees: list):
        self.rows = rows
        self.cols = cols
        self.row_constraints = list(row_constraints)
        self.col_constraints = list(col_constraints)
        self.grid = [row[:] for row in grid]
        self.trees = list(trees)

        # Lưu liên kết 1-1 giữa Lều và Cây
        self.tent_to_tree = {}   # (tent_r, tent_c) -> (tree_r, tree_c)
        self.tree_to_tent = {}   # (tree_r, tree_c) -> (tent_r, tent_c)

        # Bộ đếm số lều hiện thời trên từng hàng/cột để kiểm tra O(1)
        self.row_tent_counts = [0] * self.rows
        self.col_tent_counts = [0] * self.cols

        # Nhật ký lưu lại từng bước duyệt phục vụ hiển thị GUI mô phỏng (Animation)
        self.history_steps = []

    def in_bounds(self, r: int, c: int) -> bool:
        """Kiểm tra tọa độ (r, c) có nằm trong lưới không."""
        return 0 <= r < self.rows and 0 <= c < self.cols

    def can_place_tent(self, r: int, c: int) -> bool:
        """
        Kiểm tra nhanh ô (r, c) có thể đặt lều hợp lệ không:
        - Phải là ô đất trống '.'
        - Chưa vượt quá giới hạn lều của hàng và cột
        - Không chạm góc hay cạnh với bất kỳ lều nào khác (8 hướng)
        """
        if not self.in_bounds(r, c) or self.grid[r][c] != self.EMPTY:
            return False

        # Kiểm tra sức chứa của hàng và cột
        if self.row_tent_counts[r] >= self.row_constraints[r]:
            return False
        if self.col_tent_counts[c] >= self.col_constraints[c]:
            return False

        # Kiểm tra khoảng cách an toàn 8 ô bao quanh
        for dr, dc in self.ALL_8_DIRS:
            nr, nc = r + dr, c + dc
            if self.in_bounds(nr, nc) and self.grid[nr][nc] == self.TENT:
                return False

        return True

    MAX_HISTORY_STEPS = 25000  # Giới hạn tối đa bước log để tuyệt đối tránh tràn RAM

    def place_tent(self, r: int, c: int, tree_pos: tuple):
        """Đặt lều vào ô (r, c) phục vụ cho cây tree_pos và ghi log bước đi."""
        self.grid[r][c] = self.TENT
        self.tent_to_tree[(r, c)] = tree_pos
        self.tree_to_tent[tree_pos] = (r, c)
        self.row_tent_counts[r] += 1
        self.col_tent_counts[c] += 1

        if len(self.history_steps) < self.MAX_HISTORY_STEPS:
            self.history_steps.append({
                "action": "PLACE",
                "pos": (r, c),
                "tree": tree_pos
            })

    def remove_tent(self, r: int, c: int):
        """Gỡ lều khỏi ô (r, c) (khi quay lui DFS hoặc đổi vị trí láng giềng) và ghi log."""
        if (r, c) not in self.tent_to_tree:
            return

        tree_pos = self.tent_to_tree.pop((r, c))
        self.tree_to_tent.pop(tree_pos, None)
        self.grid[r][c] = self.EMPTY
        self.row_tent_counts[r] -= 1
        self.col_tent_counts[c] -= 1

        if len(self.history_steps) < self.MAX_HISTORY_STEPS:
            self.history_steps.append({
                "action": "REMOVE",
                "pos": (r, c),
                "tree": tree_pos
            })

    def is_solved(self) -> bool:
        """Kiểm tra bàn cờ đã đạt trạng thái đích (Goal State) hay chưa."""
        # 1. Số lều phải khớp tuyệt đối chỉ số mép hàng và cột
        if self.row_tent_counts != self.row_constraints:
            return False
        if self.col_tent_counts != self.col_constraints:
            return False

        # 2. Toàn bộ các cây đều phải có lều ghép đôi tương ứng
        if len(self.tree_to_tent) != len(self.trees):
            return False

        # 3. Lều phải nằm kề trực giao (khoảng cách Manhattan = 1) với cây của nó
        for (tr, tc), (tent_r, tent_c) in self.tree_to_tent.items():
            if abs(tr - tent_r) + abs(tc - tent_c) != 1:
                return False

        return True

    def count_conflicts(self) -> int:
        """
        Hàm heuristic h(S) cho Hill Climbing (Tính tổng số vi phạm).
        Giá trị càng nhỏ càng tốt; khi h(S) = 0 nghĩa là đã tìm ra lời giải.
        """
        conflicts = 0

        # Độ lệch chỉ số hàng và cột
        conflicts += sum(abs(self.row_tent_counts[r] - self.row_constraints[r]) for r in range(self.rows))
        conflicts += sum(abs(self.col_tent_counts[c] - self.col_constraints[c]) for c in range(self.cols))

        # Đếm các cặp lều chạm nhau ở 8 hướng
        tent_coords = list(self.tent_to_tree.keys())
        for i in range(len(tent_coords)):
            r1, c1 = tent_coords[i]
            for j in range(i + 1, len(tent_coords)):
                r2, c2 = tent_coords[j]
                if max(abs(r1 - r2), abs(c1 - c2)) == 1:
                    conflicts += 1

        return conflicts

    def display(self):
        """In bàn cờ hiện tại ra console trực quan."""
        print("\n    " + " ".join(map(str, self.col_constraints)))
        print("   " + "-" * (self.cols * 2 + 1))
        for r in range(self.rows):
            row_str = " ".join(self.grid[r])
            print(f"{self.row_constraints[r]} | {row_str} |")
        print("   " + "-" * (self.cols * 2 + 1))


# ==============================================================================
# ĐOẠN CODE KIỂM THỬ NHANH MODULE (UNIT TEST)
# ==============================================================================
if __name__ == "__main__":
    test_file = os.path.join(os.path.dirname(__file__), "..", "inputs", "6x6_easy_8729986.txt")

    if not os.path.exists(test_file):
        # Nếu không có đúng file này, lấy thử file đầu tiên có trong thư mục inputs
        inputs_dir = os.path.join(os.path.dirname(__file__), "..", "inputs")
        files = os.listdir(inputs_dir)
        if files:
            test_file = os.path.join(inputs_dir, files[0])

    print(f"[*] Đang nạp thử file: {os.path.basename(test_file)}")
    data = load_input_file(test_file)

    board = TentsBoard(
        rows=data["rows"],
        cols=data["cols"],
        row_constraints=data["row_constraints"],
        col_constraints=data["col_constraints"],
        grid=data["grid"],
        trees=data["trees"],
    )

    print(f"[+] Kích thước: {board.rows}x{board.cols}")
    print(f"[+] Số lượng cây: {len(board.trees)} cây")
    board.display()

    # Thử đặt 1 chiếc lều mẫu vào ô đầu tiên khả dụng của cây đầu tiên
    first_tree = board.trees[0]
    for dr, dc in board.ORTHO_DIRS:
        nr, nc = first_tree[0] + dr, first_tree[1] + dc
        if board.can_place_tent(nr, nc):
            print(f"\n[*] Đặt thử lều tại ({nr}, {nc}) cho cây tại {first_tree}")
            board.place_tent(nr, nc, first_tree)
            break

    board.display()
    print(f"[*] Số bước đã ghi nhận vào history: {len(board.history_steps)}")
    print(f"[*] Điểm xung đột heuristic h(S): {board.count_conflicts()}")