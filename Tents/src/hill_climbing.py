"""
MODULE: hill_climbing.py
MỤC ĐÍCH: Hiện thực thuật toán Hill Climbing với Random Restart và Sideways Moves
         để giải bài toán Tents.
NHIỆM VỤ:
- Khởi tạo trạng thái hoàn chỉnh (Complete State).
- Định nghĩa hàm Heuristic h(S) đo lường tổng vi phạm xung đột.
- Sinh không gian láng giềng và thực hiện leo đồi dốc đứng (Steepest-Descent).
- Vượt bẫy cực tiểu địa phương bằng Random Restart.
- Đo lường thời gian, RAM tiêu thụ, số lần restart và số trạng thái đã xét.
"""

import os
import sys
import random
import time
import tracemalloc

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from board import TentsBoard, load_input_file


class HillClimbingSolver:
    def __init__(self, board: TentsBoard, max_restarts: int = None, max_steps_per_restart: int = 250, max_sideways: int = 25, timeout_sec: float = None, cancel_event=None, step_callback=None):
        self.board = board
        self.max_restarts = max_restarts
        self.max_steps_per_restart = max_steps_per_restart
        self.max_sideways = max_sideways
        self.timeout_sec = timeout_sec
        self.cancel_event = cancel_event
        self.step_callback = step_callback

        self.trees = board.trees
        self.num_trees = len(self.trees)

        # Tiền xử lý: Tìm danh sách các ô kề hợp lệ cho từng cây (không phải ô chứa cây)
        self.candidate_slots = []
        for tr, tc in self.trees:
            slots = []
            for dr, dc in board.ORTHO_DIRS:
                nr, nc = tr + dr, tc + dc
                if board.in_bounds(nr, nc) and (nr, nc) not in self.trees:
                    slots.append((nr, nc))
            self.candidate_slots.append(slots)

        # Thống kê thực nghiệm
        self.states_evaluated = 0
        self.total_restarts = 0
        self.solved = False
        self.timed_out = False
        self.user_stopped = False

    def _calculate_heuristic(self, state: list) -> int:
        """
        Tính hàm h(S): Tổng mức độ vi phạm luật chơi.
        h(S) = 0 nghĩa là đã đạt trạng thái đích.
        """
        self.states_evaluated += 1
        conflicts = 0

        # 1. Đếm số cặp lều vi phạm (trùng nhau hoặc tiếp xúc nhau ở 8 hướng)
        for i in range(self.num_trees):
            r1, c1 = state[i]
            for j in range(i + 1, self.num_trees):
                r2, c2 = state[j]
                if abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1:
                    conflicts += 1

        # 2. Đếm số lều trên từng hàng và cột
        row_counts = [0] * self.board.rows
        col_counts = [0] * self.board.cols
        for r, c in state:
            row_counts[r] += 1
            col_counts[c] += 1

        # 3. Tính độ lệch so với chỉ số mép
        for r in range(self.board.rows):
            conflicts += abs(row_counts[r] - self.board.row_constraints[r])
        for c in range(self.board.cols):
            conflicts += abs(col_counts[c] - self.board.col_constraints[c])

        return conflicts

    def _generate_random_state(self) -> list:
        """Gieo ngẫu nhiên một trạng thái hợp lệ ban đầu cho toàn bộ cây."""
        state = []
        for i in range(self.num_trees):
            slots = self.candidate_slots[i]
            state.append(random.choice(slots) if slots else self.trees[i])
        return state

    def solve(self):
        """Kích hoạt giải bài toán với bộ đo thời gian và RAM."""
        tracemalloc.start()
        start_time = time.perf_counter()

        best_state = None
        best_score = float("inf")
        current_score = float("inf")  # Khởi tạo trước vòng lặp để tránh cảnh báo unbound variable

        restart_count = 0
        while True:
            if self.cancel_event is not None and self.cancel_event.is_set():
                self.user_stopped = True
                break

            if self.timeout_sec is not None and (time.perf_counter() - start_time) > self.timeout_sec:
                self.timed_out = True
                break

            if self.max_restarts is not None and restart_count >= self.max_restarts:
                break

            restart_count += 1
            self.total_restarts = restart_count
            current_state = self._generate_random_state()
            current_score = self._calculate_heuristic(current_state)

            if self.step_callback:
                self.step_callback("RESTART", current_state, current_score, self.total_restarts, self.states_evaluated, (-1, -1))

            # Cập nhật trạng thái tốt nhất tổng thể
            if current_score < best_score:
                best_score = current_score
                best_state = current_state

            sideways_count = 0

            for _ in range(self.max_steps_per_restart):
                if self.cancel_event is not None and self.cancel_event.is_set():
                    self.user_stopped = True
                    break

                if self.timeout_sec is not None and (time.perf_counter() - start_time) > self.timeout_sec:
                    self.timed_out = True
                    break

                if current_score == 0:
                    best_state = current_state
                    best_score = 0
                    self.solved = True
                    if self.step_callback:
                        self.step_callback("SOLVED", best_state, 0, self.total_restarts, self.states_evaluated, (-1, -1))
                    break

                # Tìm láng giềng tốt nhất (Steepest-Descent)
                best_neighbor = None
                best_neighbor_score = current_score
                best_move_pos = (-1, -1)

                tree_indices = list(range(self.num_trees))
                random.shuffle(tree_indices)

                for i in tree_indices:
                    current_pos = current_state[i]
                    for slot in self.candidate_slots[i]:
                        if slot == current_pos:
                            continue

                        neighbor_state = list(current_state)
                        neighbor_state[i] = slot
                        neighbor_score = self._calculate_heuristic(neighbor_state)

                        if neighbor_score < best_neighbor_score:
                            best_neighbor_score = neighbor_score
                            best_neighbor = neighbor_state
                            best_move_pos = slot
                        elif neighbor_score == best_neighbor_score and best_neighbor is None and sideways_count < self.max_sideways:
                            best_neighbor_score = neighbor_score
                            best_neighbor = neighbor_state
                            best_move_pos = slot

                # Kiểm tra tiến triển leo đồi
                if best_neighbor is not None and best_neighbor_score < current_score:
                    current_state = best_neighbor
                    current_score = best_neighbor_score
                    if current_score < best_score:
                        best_score = current_score
                        best_state = current_state
                    sideways_count = 0
                    if self.step_callback:
                        self.step_callback("MOVE", current_state, current_score, self.total_restarts, self.states_evaluated, best_move_pos)
                elif best_neighbor is not None and best_neighbor_score == current_score and sideways_count < self.max_sideways:
                    current_state = best_neighbor
                    sideways_count += 1
                    if self.step_callback:
                        self.step_callback("SIDEWAYS", current_state, current_score, self.total_restarts, self.states_evaluated, best_move_pos)
                else:
                    # Bị kẹt ở Local Optima hoặc bình nguyên -> Thoát để Restart
                    break

            if self.solved or self.timed_out or self.user_stopped:
                break

        end_time = time.perf_counter()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Áp dụng trạng thái tìm được lên board để đồng bộ dữ liệu
        if self.solved and best_state:
            self._apply_solution_to_board(best_state)

        return {
            "solved": self.solved,
            "timed_out": self.timed_out,
            "user_stopped": self.user_stopped,
            "execution_time_sec": end_time - start_time,
            "peak_memory_kb": peak_mem / 1024.0,
            "states_evaluated": self.states_evaluated,
            "restarts": self.total_restarts,
            "final_heuristic": best_score if best_score != float("inf") else "N/A"  # Luôn trả về điểm tối ưu nhất tìm được
        }

    def _apply_solution_to_board(self, state: list):
        """Cập nhật ma trận board và history_steps sau khi tìm thấy đích."""
        for i in range(self.num_trees):
            r, c = state[i]
            tree_pos = self.trees[i]
            self.board.place_tent(r, c, tree_pos)


# ==============================================================================
# KIỂM THỬ TRỰC TIẾP
# ==============================================================================
if __name__ == "__main__":
    input_dir = os.path.join(os.path.dirname(__file__), "..", "inputs")
    test_files = [f for f in os.listdir(input_dir) if f.endswith(".txt")]
    if not test_files:
        print("[!] Không tìm thấy file trong inputs/. Chạy fetch_puzzles.py trước!")
        sys.exit(1)

    target_file = next((f for f in test_files if "6x6_easy" in f), test_files[0])
    filepath = os.path.join(input_dir, target_file)

    print("=" * 65)
    print(f" KIỂM THỬ HILL CLIMBING TRÊN BÀI TOÁN: {target_file}")
    print("=" * 65)

    data = load_input_file(filepath)
    board = TentsBoard(
        rows=data["rows"],
        cols=data["cols"],
        row_constraints=data["row_constraints"],
        col_constraints=data["col_constraints"],
        grid=data["grid"],
        trees=data["trees"]
    )

    solver = HillClimbingSolver(board, max_restarts=150, max_steps_per_restart=400)
    results = solver.solve()

    if results["solved"]:
        print("\n[+] TÌM THẤY LỜI GIẢI BẰNG HILL CLIMBING!")
        board.display()
    else:
        print("\n[-] Không tìm thấy nghiệm sau các lượt restart.")

    print("\n" + "-" * 40)
    print(" THÔNG SỐ ĐO ĐẠC CHO BÁO CÁO (BENCHMARK):")
    print("-" * 40)
    print(f" • Thời gian thực thi  : {results['execution_time_sec']:.6f} giây")
    print(f" • Bộ nhớ RAM đỉnh     : {results['peak_memory_kb']:.2f} KB")
    print(f" • Trạng thái đã đánh giá: {results['states_evaluated']}")
    print(f" • Số lần Random Restart : {results['restarts']}")
    print(f" • Giá trị Heuristic h(S): {results['final_heuristic']}")
    print("-" * 40)