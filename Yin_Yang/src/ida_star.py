"""
MODULE: ida_star.py
MỤC ĐÍCH: Hiện thực thuật toán tìm kiếm Heuristic IDA* (Iterative Deepening A*)
          kết hợp hàm đánh giá độ phân mảnh liên thông và kiểm soát ngưỡng lặp
          để giải bài toán Yin-Yang (Âm Dương).
NHIỆM VỤ:
- Sử dụng hàm Heuristic h(n) đo mức độ phân mảnh thành phần của Đen và Trắng:
    h(n) = max(0, C_B - 1) + max(0, C_W - 1) + 2x2_tension_penalty
- Duyệt qua các ngưỡng giới hạn (Threshold), cắt tỉa các trạng thái có h(n) > threshold.
- Tự động nới rộng ngưỡng lặp dựa trên giá trị heuristic nhỏ nhất vượt ngưỡng (min_exceeded).
- Áp dụng suy diễn ràng buộc 2x2, định lý chu vi (Perimeter) và cầu nối liên thông (Bridge rule).
- Hỗ trợ cờ ngắt an toàn cancel_event để dừng ngay lập tức khi người dùng yêu cầu.
- Ghi nhận đầy đủ lịch sử bước (history_steps) phục vụ animation Step-by-Step.
- Đo đạc thời gian, bộ nhớ đỉnh (tracemalloc), số node duyệt, số lần backtrack và số vòng lặp.
"""

import os
import sys
import time
import tracemalloc
from collections import deque

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được module board khi chạy trực tiếp file ida_star.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from board import YinYangBoard, load_input_file


class IDAStarSolver:
    UNKNOWN = '.'
    WHITE = 'W'
    BLACK = 'B'

    def __init__(self, board: YinYangBoard, max_nodes: int = None, timeout_sec: float = None, cancel_event=None, step_callback=None):
        self.board = board
        self.max_nodes = max_nodes
        self.timeout_sec = timeout_sec
        self.cancel_event = cancel_event
        self.step_callback = step_callback

        self.rows = board.rows
        self.cols = board.cols
        self.grid = board.grid

        self.nodes_explored = 0
        self.backtracks = 0
        self.iterations = 0
        self.final_threshold = 0.0
        self.solved = False
        self.timed_out = False
        self.user_stopped = False
        self.start_time = 0.0

        # Ngăn xếp phục vụ hoàn tác (Backtrack stack)
        self._stack = []

        # Tọa độ các ô trên chu vi đường viền theo chiều kim đồng hồ
        self._peri = (
            [(0, c) for c in range(self.cols)] +
            [(r, self.cols - 1) for r in range(1, self.rows)] +
            [(self.rows - 1, c) for c in range(self.cols - 2, -1, -1)] +
            [(r, 0) for r in range(self.rows - 2, 0, -1)]
        )

        self._visited = [[0] * self.cols for _ in range(self.rows)]
        self._visit_gen = 0

        # Đếm số lượng ô theo màu
        self._wc = 0
        self._bc = 0
        self._uc = 0
        for r in range(self.rows):
            for c in range(self.cols):
                v = self.grid[r][c]
                if v == self.WHITE:
                    self._wc += 1
                elif v == self.BLACK:
                    self._bc += 1
                else:
                    self._uc += 1

    def _notify_step(self, pos=(-1, -1), action="PLACE", h=0):
        if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
            self.user_stopped = True
            return
        if self.step_callback is not None:
            try:
                self.step_callback(self.board, pos, action, self.nodes_explored, self.backtracks, self.iterations, h)
            except Exception:
                pass

    def _snap(self):
        return len(self._stack)

    def _backtrack(self, snap_pos):
        while len(self._stack) > snap_pos:
            r, c, old_v, action = self._stack.pop()
            cur = self.grid[r][c]
            if cur == self.WHITE: self._wc -= 1
            elif cur == self.BLACK: self._bc -= 1
            else: self._uc -= 1

            if old_v == self.WHITE: self._wc += 1
            elif old_v == self.BLACK: self._bc += 1
            else: self._uc += 1

            self.grid[r][c] = old_v
            self.board.history_steps.append(("backtrack", r, c, old_v))
            self.backtracks += 1
            self._notify_step((r, c), "REMOVE", 0)

    def _set(self, r, c, v, action_type="deduce"):
        old = self.grid[r][c]
        if old == v:
            return True
        if old != self.UNKNOWN:
            return False

        if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
            self.user_stopped = True
            return False

        self._stack.append((r, c, old, action_type))
        self._uc -= 1
        if v == self.WHITE:
            self._wc += 1
        else:
            self._bc += 1
        self.grid[r][c] = v
        self.board.history_steps.append((action_type, r, c, v))
        self._notify_step((r, c), "PLACE", 0)

        if not self._rule_2x2_at(r, c):
            return False
        if not self._rule_corner3_at(r, c):
            return False
        if not self._rule_surrounded_at(r, c):
            return False

        opp = self.BLACK if v == self.WHITE else self.WHITE
        if not self._bfs_comp(r, c):
            return False
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == opp:
                if not self._bfs_comp(nr, nc):
                    return False

        if r == 0 or r == self.rows - 1 or c == 0 or c == self.cols - 1:
            if not self._rule_perimeter():
                return False

        return True

    def _batch_set(self, cells, v):
        for r, c in cells:
            if self.grid[r][c] != v:
                if not self._set(r, c, v, action_type="deduce"):
                    return False
        return True

    def _rule_2x2_at(self, r, c):
        grid = self.grid
        for dr in (-1, 0):
            for dc in (-1, 0):
                tr, tc = r + dr, c + dc
                if 0 <= tr < self.rows - 1 and 0 <= tc < self.cols - 1:
                    cells = [(tr, tc), (tr, tc + 1), (tr + 1, tc), (tr + 1, tc + 1)]
                    vv = [grid[x][y] for x, y in cells]

                    if '.' not in vv:
                        if vv[0] == vv[1] == vv[2] == vv[3]:
                            return False
                        if vv[0] == vv[3] and vv[1] == vv[2]:
                            return False
                    else:
                        uk = None
                        wc = bc = 0
                        for i, val in enumerate(vv):
                            if val == '.':
                                uk = i
                            elif val == 'W':
                                wc += 1
                            else:
                                bc += 1

                        if uk is not None and (wc == 3 or bc == 3):
                            uv = 'B' if wc == 3 else 'W'
                            ux, uy = cells[uk]
                            if not self._set(ux, uy, uv, "deduce"):
                                return False

                        v0, v1, v2, v3 = vv
                        if v0 != '.' and v0 == v3:
                            if v1 != '.' and v1 != v0 and v2 == '.':
                                if not self._set(cells[2][0], cells[2][1], v0, "deduce"):
                                    return False
                            if v2 != '.' and v2 != v0 and v1 == '.':
                                if not self._set(cells[1][0], cells[1][1], v0, "deduce"):
                                    return False
                        if v1 != '.' and v1 == v2:
                            if v0 != '.' and v0 != v1 and v3 == '.':
                                if not self._set(cells[3][0], cells[3][1], v1, "deduce"):
                                    return False
                            if v3 != '.' and v3 != v1 and v0 == '.':
                                if not self._set(cells[0][0], cells[0][1], v1, "deduce"):
                                    return False
        return True

    def _rule_corner3_at(self, r, c):
        grid = self.grid
        for dr in (-1, 0):
            for dc in (-2, 0):
                tr, tc = r + dr, c + dc
                if 0 <= tr <= self.rows - 2 and 0 <= tc <= self.cols - 3:
                    corners = [(tr, tc), (tr, tc + 2), (tr + 1, tc), (tr + 1, tc + 2)]
                    cv = [grid[x][y] for x, y in corners]
                    if '.' not in cv:
                        wc = cv.count('W')
                        bc = cv.count('B')
                        if wc == 3 and bc == 1:
                            for (cr, _), val in zip(corners, cv):
                                if val == 'B' and grid[cr][tc + 1] == '.':
                                    if not self._set(cr, tc + 1, 'B', "deduce"):
                                        return False
                                    break
                        elif bc == 3 and wc == 1:
                            for (cr, _), val in zip(corners, cv):
                                if val == 'W' and grid[cr][tc + 1] == '.':
                                    if not self._set(cr, tc + 1, 'W', "deduce"):
                                        return False
                                    break
        for dr in (-2, 0):
            for dc in (-1, 0):
                tr, tc = r + dr, c + dc
                if 0 <= tr <= self.rows - 3 and 0 <= tc <= self.cols - 2:
                    corners = [(tr, tc), (tr + 2, tc), (tr, tc + 1), (tr + 2, tc + 1)]
                    cv = [grid[x][y] for x, y in corners]
                    if '.' not in cv:
                        wc = cv.count('W')
                        bc = cv.count('B')
                        if wc == 3 and bc == 1:
                            for (_, cc), val in zip(corners, cv):
                                if val == 'B' and grid[tr + 1][cc] == '.':
                                    if not self._set(tr + 1, cc, 'B', "deduce"):
                                        return False
                                    break
                        elif bc == 3 and wc == 1:
                            for (_, cc), val in zip(corners, cv):
                                if val == 'W' and grid[tr + 1][cc] == '.':
                                    if not self._set(tr + 1, cc, 'W', "deduce"):
                                        return False
                                    break
        return True

    def _rule_surrounded_at(self, r, c):
        grid = self.grid
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols and grid[nr][nc] == '.':
                color = None
                ok = True
                for ddr, ddc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nnr, nnc = nr + ddr, nc + ddc
                    if 0 <= nnr < self.rows and 0 <= nnc < self.cols:
                        nnv = grid[nnr][nnc]
                        if nnv == '.':
                            ok = False
                            break
                        if color is None:
                            color = nnv
                        elif nnv != color:
                            ok = False
                            break
                if ok and color is not None:
                    if not self._set(nr, nc, color, "deduce"):
                        return False

        for cr, cc in [(r, c)] + [(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                                  if 0 <= r + dr < self.rows and 0 <= c + dc < self.cols and grid[r + dr][c + dc] != '.']:
            cv2 = grid[cr][cc]
            opp2 = 'B' if cv2 == 'W' else 'W'
            unk_pos = None
            valid = True
            for dr2, dc2 in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nnr, nnc = cr + dr2, cc + dc2
                if 0 <= nnr < self.rows and 0 <= nnc < self.cols:
                    nnv = grid[nnr][nnc]
                    if nnv == '.':
                        if unk_pos is None:
                            unk_pos = (nnr, nnc)
                        else:
                            valid = False
                            break
                    elif nnv != opp2:
                        valid = False
                        break
            if valid and unk_pos is not None:
                ur, uc = unk_pos
                if not self._set(ur, uc, cv2, "deduce"):
                    return False
        return True

    def _bfs_comp(self, r, c):
        color = self.grid[r][c]
        if color == '.':
            return True
        total = self._wc if color == 'W' else self._bc

        self._visit_gen += 1
        gen = self._visit_gen
        self._visited[r][c] = gen
        q = deque([(r, c)])
        found = 0
        unknown = None
        candidates = []

        while True:
            while q:
                cr, cc = q.popleft()
                if self.grid[cr][cc] == color:
                    found += 1
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < self.rows and 0 <= nc < self.cols:
                        nv = self.grid[nr][nc]
                        if nv == color and self._visited[nr][nc] != gen:
                            self._visited[nr][nc] = gen
                            q.append((nr, nc))
                        elif nv == '.' and self._visited[nr][nc] != gen:
                            if unknown is None:
                                unknown = (nr, nc)
                            elif unknown != (nr, nc):
                                if candidates:
                                    return self._batch_set(candidates, color)
                                return True
            if found == total:
                if candidates:
                    return self._batch_set(candidates, color)
                return True
            if unknown is None:
                return False

            candidates.append(unknown)
            self._visited[unknown[0]][unknown[1]] = gen
            q.append(unknown)
            unknown = None

    def _rule_perimeter(self):
        peri = self._peri
        P = len(peri)
        colored = [(i, self.grid[r][c]) for i, (r, c) in enumerate(peri) if self.grid[r][c] != '.']
        if not colored:
            return True

        transitions = 0
        wc = bc = 0
        for k in range(len(colored)):
            if colored[k][1] == 'W':
                wc += 1
            else:
                bc += 1
            if colored[k][1] != colored[(k + 1) % len(colored)][1]:
                transitions += 1
        if transitions > 2:
            return False
        if transitions == 0:
            return True

        for color in ('W', 'B'):
            cnt = wc if color == 'W' else bc
            if cnt < 2:
                continue
            opp = 'B' if color == 'W' else 'W'
            idxs = [i for i, v in colored if v == color]
            for k in range(len(idxs)):
                i = idxs[k]
                j = idxs[(k + 1) % len(idxs)]
                if i < j:
                    arc = list(range(i + 1, j))
                else:
                    arc = list(range(i + 1, P)) + list(range(0, j))
                if not arc:
                    continue
                if any(self.grid[peri[a][0]][peri[a][1]] == opp for a in arc):
                    continue
                arc_unknowns = [peri[a] for a in arc if self.grid[peri[a][0]][peri[a][1]] == '.']
                if arc_unknowns:
                    if not self._batch_set(arc_unknowns, color):
                        return False
        return True

    def heuristic(self) -> float:
        """
        Hàm Heuristic h(n) đo mức độ phân mảnh liên thông:
        Số thành phần rời rạc dư thừa của Đen và Trắng + điểm phạt nguy cơ 2x2.
        Khi giải hoàn chỉnh: h(n) = 0.
        """
        visited = [[False] * self.cols for _ in range(self.rows)]
        b_comps = 0
        w_comps = 0
        for r in range(self.rows):
            for c in range(self.cols):
                val = self.grid[r][c]
                if val in (self.BLACK, self.WHITE) and not visited[r][c]:
                    if val == self.BLACK:
                        b_comps += 1
                    else:
                        w_comps += 1
                    visited[r][c] = True
                    q = [(r, c)]
                    head = 0
                    while head < len(q):
                        cr, cc = q[head]
                        head += 1
                        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            nr, nc = cr + dr, cc + dc
                            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                                if self.grid[nr][nc] == val and not visited[nr][nc]:
                                    visited[nr][nc] = True
                                    q.append((nr, nc))

        h = float(max(0, b_comps - 1) + max(0, w_comps - 1))

        # Phạt nguy cơ 2x2 sắp vi phạm
        grid = self.grid
        tension = 0
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                vv = [grid[r][c], grid[r][c + 1], grid[r + 1][c], grid[r + 1][c + 1]]
                if vv.count('.') == 1:
                    if vv.count('B') == 3 or vv.count('W') == 3:
                        tension += 1

        h += tension * 0.5
        return h

    def _pick(self):
        best = None
        best_n = -1
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == '.':
                    n = sum(1 for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                            if 0 <= r + dr < self.rows and 0 <= c + dc < self.cols and self.grid[r + dr][c + dc] != '.')
                    if n > best_n:
                        best_n = n
                        best = (r, c)
                        if n == 4:
                            return best
        return best

    def solve(self, max_threshold: int = 50):
        tracemalloc.start()
        self.start_time = time.perf_counter()

        clues = [(r, c) for r in range(self.rows) for c in range(self.cols) if self.grid[r][c] != '.']
        ok = True
        for r, c in clues:
            if not (self._rule_2x2_at(r, c) and self._rule_corner3_at(r, c) and self._rule_surrounded_at(r, c) and self._bfs_comp(r, c)):
                ok = False
                break

        if ok:
            self._rule_perimeter()
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
                    break
                current_threshold = next_threshold
        else:
            self.solved = False

        end_time = time.perf_counter()
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return {
            "solved": self.solved,
            "timed_out": self.timed_out,
            "user_stopped": self.user_stopped,
            "execution_time_sec": end_time - self.start_time,
            "peak_memory_kb": peak_mem / 1024.0,
            "nodes_explored": self.nodes_explored,
            "backtracks": self.backtracks,
            "iterations": self.iterations,
            "final_threshold": self.final_threshold,
            "total_steps": len(self.board.history_steps)
        }

    def _search(self, threshold: float):
        if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
            self.user_stopped = True
            return False, float("inf")
        if self.max_nodes is not None and self.nodes_explored >= self.max_nodes:
            self.timed_out = True
            return False, float("inf")
        if self.timeout_sec is not None and (time.perf_counter() - self.start_time) > self.timeout_sec:
            self.timed_out = True
            return False, float("inf")

        h = self.heuristic()
        if h > threshold:
            return False, h

        pos = self._pick()
        if pos is None:
            return self.board.is_solved(), threshold

        self.nodes_explored += 1
        r, c = pos

        nb_b = sum(1 for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)) if 0 <= r + dr < self.rows and 0 <= c + dc < self.cols and self.grid[r + dr][c + dc] == 'B')
        nb_w = sum(1 for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)) if 0 <= r + dr < self.rows and 0 <= c + dc < self.cols and self.grid[r + dr][c + dc] == 'W')
        order = ['B', 'W'] if nb_b >= nb_w else ['W', 'B']

        min_exceeded = float("inf")

        for val in order:
            if self.user_stopped or (self.cancel_event is not None and self.cancel_event.is_set()):
                self.user_stopped = True
                return False, float("inf")

            snap = self._snap()
            if self._set(r, c, val, action_type="assign"):
                found, next_t = self._search(threshold)
                if found:
                    return True, threshold
                if next_t < min_exceeded:
                    min_exceeded = next_t
            self._backtrack(snap)

        return False, min_exceeded


if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = os.path.join(os.path.dirname(__file__), "..", "inputs", "10x10_easy_1172076.txt")

    print(f"[*] Đang giải bằng IDA*: {os.path.basename(filepath)}")
    data = load_input_file(filepath)
    board = YinYangBoard(data["rows"], data["cols"], data["grid"], data["initial_clues"])
    solver = IDAStarSolver(board)
    result = solver.solve()

    print("=" * 60)
    print(f" Kết quả: {'THÀNH CÔNG' if result['solved'] else 'THẤT BẠI'}")
    print(f" Thời gian thực thi: {result['execution_time_sec']:.4f} giây")
    print(f" Bộ nhớ tiêu thụ: {result['peak_memory_kb']:.2f} KB")
    print(f" Số trạng thái đã duyệt: {result['nodes_explored']}")
    print(f" Số lần quay lui: {result['backtracks']}")
    print(f" Số vòng lặp IDA*: {result['iterations']}")
    print(f" Ngưỡng cuối: {result['final_threshold']}")
    print(f" Tổng số bước ghi nhận: {result['total_steps']}")
    print("=" * 60)
    if result["solved"]:
        print("Ma trận nghiệm:")
        for row in board.grid:
            print(" ".join(row))
