"""
MODULE: dfs.py
MỤC ĐÍCH: Hiện thực thuật toán Depth-First Search (DFS) kết hợp Backtracking
         và Pruning để giải bài toán Tents.
NHIỆM VỤ:
- Duyệt không gian trạng thái theo từng cây.
- Cắt tỉa các nhánh vi phạm ràng buộc (8 hướng, giới hạn hàng/cột).
- Đo đạc thời gian, bộ nhớ RAM (tracemalloc), số node và số lần backtrack.
"""

import os
import sys
import time
import tracemalloc

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được module board khi chạy trực tiếp file dfs.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from board import TentsBoard, load_input_file


class DFSSolver:
    def __init__(self, board: TentsBoard, max_nodes: int = 150000, timeout_sec: float = 6.0):
        self.board = board
        self.max_nodes = max_nodes
        self.timeout_sec = timeout_sec
        self.nodes_explored = 0  # Số lượng trạng thái/nhánh đã duyệt
        self.backtracks = 0      # Số lần phải quay lui khi vào ngõ cụt
        self.solved = False
        self.timed_out = False
        self.start_time = 0.0

        # Sắp xếp các cây theo số vị trí kề hợp lệ ban đầu tăng dần (MRV Heuristic)
        # Giúp ưu tiên giải các cây bị ràng buộc nhiều nhất trước, giảm bùng nổ tổ hợp
        self.ordered_trees = sorted(
            self.board.trees,
            key=lambda t: sum(1 for dr, dc in self.board.ORTHO_DIRS if self.board.can_place_tent(t[0] + dr, t[1] + dc))
        )

    def solve(self):
        """
        Kích hoạt giải bài toán, tự động đo thời gian và mức tiêu hao RAM.
        Trả về dictionary chứa kết quả và các thông số thực nghiệm.
        """
        tracemalloc.start()
        self.start_time = time.perf_counter()

        # Gọi hàm đệ quy từ cây đầu tiên trong danh sách đã sắp xếp
        self.solved = self._backtrack(tree_index=0)

        end_time = time.perf_counter()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        elapsed_time = end_time - self.start_time
        peak_mem_kb = peak_mem / 1024.0

        return {
            "solved": self.solved,
            "timed_out": self.timed_out,
            "execution_time_sec": elapsed_time,
            "peak_memory_kb": peak_mem_kb,
            "nodes_explored": self.nodes_explored,
            "backtracks": self.backtracks,
            "total_steps": len(self.board.history_steps)
        }

    def _backtrack(self, tree_index: int) -> bool:
        """Duyệt đệ quy theo chiều sâu qua từng cây với kiểm tra an toàn Timeout."""
        # Kiểm tra ngưỡng an toàn để không bao giờ làm đơ ứng dụng hoặc tràn bộ nhớ
        if self.nodes_explored >= self.max_nodes or (time.perf_counter() - self.start_time) > self.timeout_sec:
            self.timed_out = True
            return False

        # TRƯỜNG HỢP CƠ SỞ: Đã gán lều cho toàn bộ K cây
        if tree_index == len(self.ordered_trees):
            return self.board.is_solved()

        self.nodes_explored += 1
        curr_tree = self.ordered_trees[tree_index]
        tr, tc = curr_tree

        # Thử đặt lều tại 4 hướng trực giao (Lên, Xuống, Trái, Phải)
        for dr, dc in self.board.ORTHO_DIRS:
            nr, nc = tr + dr, tc + dc

            # CẮT TỈA (Pruning): Kiểm tra ô (nr, nc) có hợp lệ không
            if self.board.can_place_tent(nr, nc):
                # 1. Đặt lều và lưu lại lịch sử
                self.board.place_tent(nr, nc, curr_tree)

                # 2. Đệ quy giải tiếp cho cây kế tiếp (tree_index + 1)
                if self._backtrack(tree_index + 1):
                    return True

                # 3. Quay lui: gỡ lều ra nếu nhánh phía dưới không tìm thấy nghiệm
                self.board.remove_tent(nr, nc)
                self.backtracks += 1

        # Nếu cả 4 hướng đều không thể đặt hoặc dẫn đến ngõ cụt
        return False


# ==============================================================================
# ĐOẠN CHẠY THỰC NGHIỆM TRỰC TIẾP
# ==============================================================================
if __name__ == "__main__":
    # Chọn test thử một màn từ thư mục inputs
    input_dir = os.path.join(os.path.dirname(__file__), "..", "inputs")
    
    # Ưu tiên lấy file 6x6 hoặc file đầu tiên tìm thấy
    test_files = [f for f in os.listdir(input_dir) if f.endswith(".txt")]
    if not test_files:
        print("[!] Thư mục inputs/ đang trống. Hãy chạy fetch_puzzles.py trước!")
        sys.exit(1)

    target_file = next((f for f in test_files if "6x6_easy" in f), test_files[0])
    filepath = os.path.join(input_dir, target_file)

    print("=" * 65)
    print(f" KIỂM THỬ THUẬT TOÁN DFS TRÊN BÀI TOÁN: {target_file}")
    print("=" * 65)

    # 1. Khởi tạo bài toán
    data = load_input_file(filepath)
    board = TentsBoard(
        rows=data["rows"],
        cols=data["cols"],
        row_constraints=data["row_constraints"],
        col_constraints=data["col_constraints"],
        grid=data["grid"],
        trees=data["trees"]
    )

    print("\n[*] Bảng ban đầu:")
    board.display()

    # 2. Chạy giải thuật
    solver = DFSSolver(board)
    results = solver.solve()

    # 3. Xuất kết quả
    if results["solved"]:
        print("\n[+] TÌM THẤY LỜI GIẢI THÀNH CÔNG!")
        board.display()
    else:
        print("\n[-] Không tìm thấy lời giải hợp lệ cho bài toán.")

    print("\n" + "-" * 40)
    print(" THÔNG SỐ ĐO ĐẠC CHO BÁO CÁO (BENCHMARK):")
    print("-" * 40)
    print(f" • Thời gian thực thi : {results['execution_time_sec']:.6f} giây")
    print(f" • Bộ nhớ RAM đỉnh    : {results['peak_memory_kb']:.2f} KB")
    print(f" • Số node đã duyệt   : {results['nodes_explored']}")
    print(f" • Số lần quay lui    : {results['backtracks']}")
    print(f" • Tổng số bước log   : {results['total_steps']}")
    print("-" * 40)