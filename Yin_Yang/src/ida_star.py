"""
MODULE: ida_star.py
MỤC ĐÍCH: Hiện thực thuật toán tìm kiếm Heuristic IDA* (Iterative Deepening A*)
          kết hợp hàm đánh giá độ phân mảnh liên thông và kiểm soát ngưỡng lặp
          để giải bài toán Yin-Yang.
NHIỆM VỤ:
- Sử dụng hàm Heuristic h(n) đo mức độ phân mảnh thành phần của Đen và Trắng:
    h(n) = max(0, C_B - 1) + max(0, C_W - 1) + 2x2_tension_penalty
- Duyệt qua các ngưỡng giới hạn (Threshold), cắt tỉa các trạng thái có h(n) > threshold.
- Tự động nới rộng ngưỡng lặp dựa trên giá trị heuristic nhỏ nhất vượt ngưỡng (min_exceeded).
- Đo đạc thời gian, bộ nhớ đỉnh (tracemalloc), số node duyệt, số lần backtrack và số vòng lặp.
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

# Đảm bảo import được module board khi chạy trực tiếp file ida_star.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from board import YinYangBoard, load_input_file


class IDAStarSolver:
    def __init__(self, board: YinYangBoard, max_nodes: int = None, timeout_sec: float = None, cancel_event=None, step_callback=None):
        self.board = board
        self.max_nodes = max_nodes
        self.timeout_sec = timeout_sec
        self.cancel_event = cancel_event
        self.step_callback = step_callback

        self.nodes_explored = 0  # Số lượng trạng thái đã xét
        self.backtracks = 0      # Số lần phải quay lui
        self.iterations = 0      # Số vòng lặp nâng ngưỡng của IDA*
        self.final_threshold = 0
        self.solved = False
        self.timed_out = False
        self.user_stopped = False
        self.start_time = 0.0

        # Tọa độ các ô trên chu vi đường viền (Perimeter)
        self.border_coords = self._get_border_cells()

    def _notify_step(self, pos: tuple, action: str, h: int = 0):
        if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
            self.user_stopped = True
            return
        if self.step_callback is not None:
            try:
                self.step_callback(self.board, pos, action, self.nodes_explored, self.backtracks, self.iterations, h)
            except Exception:
                pass

    def _get_border_cells(self):
        """Lấy danh sách tọa độ các ô viền theo chiều kim đồng hồ."""
        coords = []
        rows, cols = self.board.rows, self.board.cols
        for c in range(cols):
            coords.append((0, c))
        for r in range(1, rows - 1):
            coords.append((r, cols - 1))
        for c in range(cols - 1, -1, -1):
            coords.append((rows - 1, c))
        for r in range(rows - 2, 0, -1):
            coords.append((r, 0))
        return coords

    def _check_border_valid(self) -> bool:
        """Kiểm tra định lý chu vi: Số lần đổi màu <= 2."""
        grid = self.board.grid
        assigned = [grid[r][c] for r, c in self.border_coords if grid[r][c] in (self.board.BLACK, self.board.WHITE)]
        if not assigned:
            return True
        compressed = [assigned[0]]
        for c in assigned[1:]:
            if c != compressed[-1]:
                compressed.append(c)
        if len(compressed) > 1 and compressed[0] == compressed[-1]:
            compressed.pop()
        return len(compressed) <= 2

    def _propagate_constraints(self):
        """Suy diễn logic tất định 2x2 và ô đơn độc."""
        b = self.board
        made = []
        changed = True
        while changed:
            changed = False
            # 1. Quét 2x2
            for r in range(b.rows - 1):
                for c in range(b.cols - 1):
                    cells = [b.grid[r][c], b.grid[r][c + 1], b.grid[r + 1][c], b.grid[r + 1][c + 1]]
                    e_cnt = cells.count(b.EMPTY)
                    b_cnt = cells.count(b.BLACK)
                    w_cnt = cells.count(b.WHITE)

                    if e_cnt == 0:
                        if b_cnt == 4 or w_cnt == 4:
                            return None
                        if cells[0] == cells[3] and cells[1] == cells[2] and cells[0] != cells[1]:
                            return None
                    elif e_cnt == 1:
                        coords = [(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)]
                        empty_idx = cells.index(b.EMPTY)
                        er, ec = coords[empty_idx]
                        if b_cnt == 3:
                            b.assign(er, ec, b.WHITE, action_type="deduce")
                            made.append((er, ec))
                            changed = True
                        elif w_cnt == 3:
                            b.assign(er, ec, b.BLACK, action_type="deduce")
                            made.append((er, ec))
                            changed = True
                        elif cells[0] == cells[3] and cells[0] != b.EMPTY and empty_idx in (1, 2):
                            opp_idx = 2 if empty_idx == 1 else 1
                            if cells[opp_idx] != b.EMPTY and cells[opp_idx] != cells[0]:
                                b.assign(er, ec, cells[0], action_type="deduce")
                                made.append((er, ec))
                                changed = True
                        elif cells[1] == cells[2] and cells[1] != b.EMPTY and empty_idx in (0, 3):
                            opp_idx = 3 if empty_idx == 0 else 0
                            if cells[opp_idx] != b.EMPTY and cells[opp_idx] != cells[1]:
                                b.assign(er, ec, cells[1], action_type="deduce")
                                made.append((er, ec))
                                changed = True

            # 2. Quét ô đơn độc
            for r in range(b.rows):
                for c in range(b.cols):
                    col = b.grid[r][c]
                    if col in (b.BLACK, b.WHITE):
                        same_cnt = 0
                        empty_neighbors = []
                        for dr, dc in b.ORTHO_DIRS:
                            nr, nc = r + dr, c + dc
                            if b.in_bounds(nr, nc):
                                if b.grid[nr][nc] == col:
                                    same_cnt += 1
                                elif b.grid[nr][nc] == b.EMPTY:
                                    empty_neighbors.append((nr, nc))
                        if same_cnt == 0 and len(empty_neighbors) == 1:
                            er, ec = empty_neighbors[0]
                            b.assign(er, ec, col, action_type="deduce")
                            made.append((er, ec))
                            changed = True

        return made

    def heuristic(self) -> float:
        """
        Hàm heuristic h(n) đo mức độ phân mảnh liên thông:
        - Mỗi thành phần rời rạc dư thừa của Đen/Trắng đóng góp điểm phạt.
        - Trạng thái giải hoàn chỉnh có đúng 1 khối Đen và 1 khối Trắng -> h(n) = 0.
        """
        b = self.board
        b_comps = b.get_components(b.BLACK, include_empty=False)
        w_comps = b.get_components(b.WHITE, include_empty=False)
        nb = len(b_comps)
        nw = len(w_comps)

        h = float(max(0, nb - 1) + max(0, nw - 1))
        return h

    def _select_variable(self):
        """Chọn biến có độ ràng buộc cao nhất (nhiều ô kề đã điền)."""
        b = self.board
        best_cell = None
        max_score = -1

        for r in range(b.rows):
            for c in range(b.cols):
                if b.grid[r][c] == b.EMPTY:
                    score = 0
                    for dr, dc in b.ALL_8_DIRS:
                        nr, nc = r + dr, c + dc
                        if b.in_bounds(nr, nc) and b.grid[nr][nc] != b.EMPTY:
                            score += 1
                    if score > max_score:
                        max_score = score
                        best_cell = (r, c)
        return best_cell

    def _notify_step(self, pos=(-1, -1), action="PLACE", h=0):
        if self.step_callback is not None:
            try:
                self.step_callback(self.board, pos, action, self.nodes_explored, self.backtracks, self.iterations, h)
            except TypeError:
                try:
                    self.step_callback(self.board, pos, action, self.nodes_explored, self.backtracks)
                except TypeError:
                    self.step_callback(self.board)

    def solve(self, max_threshold: int = 50):
        """
        Kích hoạt giải bài toán bằng IDA*, quản lý vòng lặp tăng ngưỡng.
        """
        tracemalloc.start()
        self.start_time = time.perf_counter()

        current_threshold = self.heuristic()
        self.iterations = 0

        while current_threshold <= max_threshold:
            if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
                self.user_stopped = True
                break

            if self.timeout_sec is not None and (time.perf_counter() - self.start_time) > self.timeout_sec:
                self.timed_out = True
                break

            self.iterations += 1
            found, next_threshold = self._search(current_threshold)

            if found:
                self.solved = True
                self.final_threshold = current_threshold
                break

            if next_threshold == float("inf") or next_threshold <= current_threshold:
                # Không còn nhánh nào khả thi vượt ngưỡng
                break

            current_threshold = next_threshold

        end_time = time.perf_counter()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        elapsed_time = end_time - self.start_time
        peak_mem_kb = peak_mem / 1024.0

        return {
            "solved": self.solved,
            "timed_out": self.timed_out,
            "user_stopped": self.user_stopped,
            "execution_time_sec": elapsed_time,
            "peak_memory_kb": peak_mem_kb,
            "nodes_explored": self.nodes_explored,
            "backtracks": self.backtracks,
            "iterations": self.iterations,
            "final_threshold": self.final_threshold,
            "total_steps": len(self.board.history_steps)
        }

    def _search(self, threshold: float):
        """
        Duyệt nhánh DFS có chặn trên bởi ngưỡng Heuristic: h(S) <= threshold.
        Trả về tuple (found: bool, min_exceeded: float).
        """
        if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
            self.user_stopped = True
            return False, float("inf")

        if self.max_nodes is not None and self.nodes_explored >= self.max_nodes:
            self.timed_out = True
            return False, float("inf")

        if self.timeout_sec is not None and (time.perf_counter() - self.start_time) > self.timeout_sec:
            self.timed_out = True
            return False, float("inf")

        self.nodes_explored += 1

        # 1. Suy diễn bắt buộc
        deduced = self._propagate_constraints()
        if deduced is None:
            return False, float("inf")

        # 2. Kiểm tra định lý biên
        if not self._check_border_valid():
            for r, c in reversed(deduced):
                self.board.unassign(r, c)
            return False, float("inf")

        # 3. Kiểm tra tính liên thông tiềm năng
        if not self.board.check_connectivity_potential():
            for r, c in reversed(deduced):
                self.board.unassign(r, c)
            return False, float("inf")

        # 4. Kiểm tra ngưỡng Heuristic
        h = self.heuristic()
        if h > threshold:
            for r, c in reversed(deduced):
                self.board.unassign(r, c)
            return False, h

        # 5. Chọn biến tiếp theo
        cell = self._select_variable()
        if cell is None:
            solved = self.board.is_solved()
            if not solved:
                for r, c in reversed(deduced):
                    self.board.unassign(r, c)
            return solved, threshold

        r, c = cell
        b = self.board

        b_cnt = sum(1 for dr, dc in b.ORTHO_DIRS if b.in_bounds(r + dr, c + dc) and b.grid[r + dr][c + dc] == b.BLACK)
        w_cnt = sum(1 for dr, dc in b.ORTHO_DIRS if b.in_bounds(r + dr, c + dc) and b.grid[r + dr][c + dc] == b.WHITE)
        color_order = [b.BLACK, b.WHITE] if b_cnt >= w_cnt else [b.WHITE, b.BLACK]

        min_exceeded = float("inf")

        for color in color_order:
            if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
                self.user_stopped = True
                break
            if b.can_assign_color(r, c, color):
                b.assign(r, c, color, action_type="assign")
                self._notify_step((r, c), "PLACE", h)

                if self._check_border_valid() and b.check_connectivity_potential():
                    found, t = self._search(threshold)
                    if found:
                        return True, threshold
                    if t < min_exceeded:
                        min_exceeded = t

                b.unassign(r, c, action_type="backtrack")
                self.backtracks += 1
                self._notify_step((r, c), "REMOVE", h)

        for dr, dc in reversed(deduced):
            self.board.unassign(dr, dc, action_type="backtrack")
            self.backtracks += 1
            self._notify_step((dr, dc), "REMOVE", h)

        return False, min_exceeded


if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = os.path.join(os.path.dirname(__file__), "..", "inputs", "6x6_easy_1232640.txt")

    print(f"[*] Đang giải bằng IDA*: {os.path.basename(filepath)}")
    data = load_input_file(filepath)
    board = YinYangBoard(data["rows"], data["cols"], data["grid"], data["initial_clues"])
    solver = IDAStarSolver(board, timeout_sec=30)
    result = solver.solve()

    print("=" * 60)
    print(f" Kết quả: {'THÀNH CÔNG' if result['solved'] else 'THẤT BẠI'}")
    print(f" Thời gian thực thi: {result['execution_time_sec']:.4f} giây")
    print(f" Bộ nhớ tiêu thụ: {result['peak_memory_kb']:.2f} KB")
    print(f" Số trạng thái đã duyệt: {result['nodes_explored']}")
    print(f" Số lần quay lui: {result['backtracks']}")
    print(f" Số vòng lặp IDA*: {result['iterations']}")
    print(f" Ngưỡng cuối: {result['final_threshold']}")
    print("=" * 60)
    if result["solved"]:
        print("Ma trận nghiệm:")
        for row in board.grid:
            print(" ".join(row))
