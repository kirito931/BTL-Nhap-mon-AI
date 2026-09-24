"""
MODULE: board.py
MỤC ĐÍCH:
1. Đọc và nạp các file bài toán Yin-Yang từ thư mục inputs/.
2. Quản lý trạng thái bàn cờ YinYangBoard.
3. Kiểm tra tính hợp lệ của trạng thái:
   - Ràng buộc 2x2 không được cùng màu.
   - Ràng buộc không tạo bẫy chéo bàn cờ (Checkerboard 2x2).
   - Kiểm tra liên thông trực giao (Orthogonal 4-connectivity) cho cả Đen và Trắng.
   - Cắt tỉa sớm không gian trạng thái khi phát hiện đảo chết (Dead Islands)
     hoặc các thành phần không thể nối lại với nhau qua các ô trống.
4. Ghi nhận nhật ký bước đi (history_steps) phục vụ demo Step-by-Step.
5. Cung cấp hàm Heuristic h(n) đo mức độ phân mảnh để phục vụ thuật toán IDA*.
"""

import os
from collections import deque


def load_input_file(filepath: str):
    """
    Đọc file .txt định dạng trực quan Yin-Yang:
    - Dòng 1: # Puzzle ID: ... | Category: ...
    - Dòng 2: rows cols
    - Dòng 3 trở đi: Ma trận các ô cờ ('B', 'W', '.')
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if len(lines) < 2:
        raise ValueError(f"File {filepath} không đúng cấu trúc tối thiểu.")

    rows, cols = map(int, lines[0].split())
    grid = []
    initial_clues = set()

    for r in range(rows):
        tokens = lines[1 + r].split()
        if len(tokens) != cols:
            raise ValueError(f"Dòng {r+1} có {len(tokens)} cột, mong đợi {cols}.")
        grid.append(tokens)
        for c, val in enumerate(tokens):
            if val in ('B', 'W'):
                initial_clues.add((r, c))

    return {
        "rows": rows,
        "cols": cols,
        "grid": grid,
        "initial_clues": initial_clues
    }


class YinYangBoard:
    EMPTY = '.'
    BLACK = 'B'
    WHITE = 'W'

    # 4 hướng trực giao
    ORTHO_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    # 8 hướng xung quanh
    ALL_8_DIRS = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)
    ]

    def __init__(self, rows: int, cols: int, grid: list, initial_clues: set = None):
        self.rows = rows
        self.cols = cols
        self.grid = [row[:] for row in grid]
        self.initial_clues = set(initial_clues) if initial_clues is not None else set()

        if not self.initial_clues:
            for r in range(self.rows):
                for c in range(self.cols):
                    if self.grid[r][c] in (self.BLACK, self.WHITE):
                        self.initial_clues.add((r, c))

        # Lưu lịch sử bước thực hiện phục vụ animation Step-by-Step
        # Mỗi phần tử: (action, r, c, color, extra_info)
        self.history_steps = []

    def copy(self):
        """Tạo bản sao độc lập của bàn cờ."""
        new_b = YinYangBoard(self.rows, self.cols, self.grid, self.initial_clues)
        new_b.history_steps = list(self.history_steps)
        return new_b

    def in_bounds(self, r: int, c: int) -> bool:
        """Kiểm tra ô (r, c) có nằm trong lưới không."""
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get_unassigned_cells(self):
        """Danh sách các ô trống chưa được gán màu."""
        cells = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == self.EMPTY:
                    cells.append((r, c))
        return cells

    def count_assigned(self):
        """Đếm số ô đã được gán màu."""
        cnt = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] != self.EMPTY:
                    cnt += 1
        return cnt

    # ==========================================================================
    # KIỂM TRA RÀNG BUỘC CỤC BỘ (2x2 & CHECKERBOARD)
    # ==========================================================================
    def check_2x2_conflict_at(self, r: int, c: int) -> bool:
        """
        Kiểm tra nhanh xem các khối 2x2 chứa ô (r, c) có bị vi phạm không:
        1. Cả 4 ô cùng màu (cấm hoàn toàn 4 Đen hoặc 4 Trắng).
        2. Mẫu cờ ca-rô đối xứng chéo (B W / W B) khiến 2 màu cắt nhau trong mặt phẳng.
        Trả về True nếu CÓ XUNG ĐỘT (vi phạm), False nếu an toàn.
        """
        grid = self.grid
        for top in (r - 1, r):
            for left in (c - 1, c):
                bottom = top + 1
                right = left + 1
                if 0 <= top and bottom < self.rows and 0 <= left and right < self.cols:
                    c1 = grid[top][left]
                    c2 = grid[top][right]
                    c3 = grid[bottom][left]
                    c4 = grid[bottom][right]

                    # Bỏ qua nếu có ô chưa điền
                    if c1 == self.EMPTY or c2 == self.EMPTY or c3 == self.EMPTY or c4 == self.EMPTY:
                        continue

                    # Vi phạm 1: Cùng màu cả 4 ô
                    if c1 == c2 == c3 == c4:
                        return True

                    # Vi phạm 2: Bẫy ca-rô 2x2 (Checkerboard trap)
                    if (c1 == c4 and c2 == c3 and c1 != c2):
                        return True

        return False

    def can_assign_color(self, r: int, c: int, color: str) -> bool:
        """
        Kiểm tra thử xem việc gán 'color' vào (r, c) có vi phạm ràng buộc 2x2
        hoặc cô lập ô đối diện không.
        """
        if self.grid[r][c] != self.EMPTY:
            return False

        orig = self.grid[r][c]
        self.grid[r][c] = color

        conflict = self.check_2x2_conflict_at(r, c)
        if conflict:
            self.grid[r][c] = orig
            return False

        # Kiểm tra nhanh: Ô xung quanh có bị cô lập hoàn toàn không
        opp_color = self.WHITE if color == self.BLACK else self.BLACK
        for dr, dc in self.ORTHO_DIRS:
            nr, nc = r + dr, c + dc
            if self.in_bounds(nr, nc) and self.grid[nr][nc] == opp_color:
                # Kiểm tra ô opp này còn đường thoát (kề ô trống hoặc kề ô cùng màu)
                has_exit = False
                for ddr, ddc in self.ORTHO_DIRS:
                    er, ec = nr + ddr, nc + ddc
                    if self.in_bounds(er, ec):
                        if self.grid[er][ec] == self.EMPTY or self.grid[er][ec] == opp_color:
                            has_exit = True
                            break
                if not has_exit:
                    # Ô opp bị bao vây hoàn toàn!
                    # Nếu trên bàn cờ có ô opp khác thì đây là vi phạm
                    self.grid[r][c] = orig
                    return False

        self.grid[r][c] = orig
        return True

    # ==========================================================================
    # PHÂN TÍCH LIÊN THÔNG VÀ CẮT TỈA KHÔNG GIAN TÌM KIẾM
    # ==========================================================================
    def get_components(self, color: str, include_empty: bool = False):
        """
        Tìm tất cả các thành phần liên thông trực giao (4 hướng) của màu 'color'.
        - include_empty = False: Chỉ xét các ô đã gán 'color'.
        - include_empty = True: Xét các ô đã gán 'color' HOẶC còn trống ('.').
        """
        visited = set()
        components = []
        valid_values = {color, self.EMPTY} if include_empty else {color}

        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] in valid_values and (r, c) not in visited:
                    # BFS tìm vùng liên thông
                    comp = []
                    q = deque([(r, c)])
                    visited.add((r, c))
                    while q:
                        cr, cc = q.popleft()
                        comp.append((cr, cc))
                        for dr, dc in self.ORTHO_DIRS:
                            nr, nc = cr + dr, cc + dc
                            if self.in_bounds(nr, nc) and (nr, nc) not in visited and self.grid[nr][nc] in valid_values:
                                visited.add((nr, nc))
                                q.append((nr, nc))
                    components.append(comp)

        return components

    def check_connectivity_potential(self) -> bool:
        """
        Điều kiện cắt tỉa mạnh (Pruning Condition):
        1. Tất cả các ô Đen hiện thời phải nằm trong CÙNG một thành phần liên thông
           của đồ thị G_B = (các ô Đen + các ô Trống). Nếu Đen bị chia cắt không thể tới nhau, prune!
        2. Tương tự cho Trắng trên G_W = (các ô Trắng + các ô Trống).
        3. Bất kỳ thành phần liên thông Đen nào đã đóng kín (không còn ô trống kề cận)
           mà vẫn còn ô Đen khác ở ngoài, prune! (Đảo chết).
        4. Tương tự cho thành phần liên thông Trắng.
        """
        # Kiểm tra Đen
        black_cells = [(r, c) for r in range(self.rows) for c in range(self.cols) if self.grid[r][c] == self.BLACK]
        if black_cells:
            # 1. Đảo chết: kiểm tra từng component Đen hiện tại
            b_comps = self.get_components(self.BLACK, include_empty=False)
            if len(b_comps) > 1:
                # Nếu có nhiều hơn 1 component Đen, component nào không kề ô trống nào thì chết chắc
                for comp in b_comps:
                    has_empty_neighbor = False
                    for r, c in comp:
                        for dr, dc in self.ORTHO_DIRS:
                            nr, nc = r + dr, c + dc
                            if self.in_bounds(nr, nc) and self.grid[nr][nc] == self.EMPTY:
                                has_empty_neighbor = True
                                break
                        if has_empty_neighbor:
                            break
                    if not has_empty_neighbor:
                        return False

            # 2. Khả năng liên thông qua ô trống
            gb_comps = self.get_components(self.BLACK, include_empty=True)
            # Tìm xem tất cả các ô Đen có nằm trong cùng 1 component của G_B không
            found_comp_idx = None
            for idx, comp in enumerate(gb_comps):
                comp_set = set(comp)
                b_in_comp = sum(1 for cell in black_cells if cell in comp_set)
                if b_in_comp > 0:
                    if b_in_comp == len(black_cells):
                        # Tất cả các ô Đen đều nằm trong component này
                        found_comp_idx = idx
                        break
                    else:
                        # Các ô Đen bị phân tách vào nhiều component khác nhau của G_B!
                        return False
            if found_comp_idx is None:
                return False

        # Kiểm tra Trắng
        white_cells = [(r, c) for r in range(self.rows) for c in range(self.cols) if self.grid[r][c] == self.WHITE]
        if white_cells:
            w_comps = self.get_components(self.WHITE, include_empty=False)
            if len(w_comps) > 1:
                for comp in w_comps:
                    has_empty_neighbor = False
                    for r, c in comp:
                        for dr, dc in self.ORTHO_DIRS:
                            nr, nc = r + dr, c + dc
                            if self.in_bounds(nr, nc) and self.grid[nr][nc] == self.EMPTY:
                                has_empty_neighbor = True
                                break
                        if has_empty_neighbor:
                            break
                    if not has_empty_neighbor:
                        return False

            gw_comps = self.get_components(self.WHITE, include_empty=True)
            found_comp_idx = None
            for idx, comp in enumerate(gw_comps):
                comp_set = set(comp)
                w_in_comp = sum(1 for cell in white_cells if cell in comp_set)
                if w_in_comp > 0:
                    if w_in_comp == len(white_cells):
                        found_comp_idx = idx
                        break
                    else:
                        return False
            if found_comp_idx is None:
                return False

        return True

    def is_solved(self) -> bool:
        """
        Kiểm tra bàn cờ đã được giải hoàn chỉnh và hợp lệ:
        1. Không còn ô trống.
        2. Không có khối 2x2 đơn sắc (4 Đen hoặc 4 Trắng).
        3. Không có bẫy ca-rô 2x2.
        4. Tất cả các ô Đen tạo thành đúng 1 thành phần liên thông trực giao.
        5. Tất cả các ô Trắng tạo thành đúng 1 thành phần liên thông trực giao.
        """
        # 1. Còn ô trống không?
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == self.EMPTY:
                    return False

        # 2 & 3. Quét kiểm tra mọi khối 2x2
        grid = self.grid
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                c1 = grid[r][c]
                c2 = grid[r][c + 1]
                c3 = grid[r + 1][c]
                c4 = grid[r + 1][c + 1]

                if c1 == c2 == c3 == c4:
                    return False
                if c1 == c4 and c2 == c3 and c1 != c2:
                    return False

        # 4. Liên thông Đen
        black_comps = self.get_components(self.BLACK, include_empty=False)
        if len(black_comps) != 1:
            return False

        # 5. Liên thông Trắng
        white_comps = self.get_components(self.WHITE, include_empty=False)
        if len(white_comps) != 1:
            return False

        return True

    # ==========================================================================
    # HÀM HEURISTIC h(n) PHỤC VỤ THUẬT TOÁN IDA*
    # ==========================================================================
    def compute_heuristic(self) -> float:
        """
        Hàm Heuristic h(n) cho bài toán Yin-Yang:
        1. Số thành phần liên thông rời rạc của Đen (C_B) và Trắng (C_W):
           - Để hợp nhất C thành phần lại thành 1 khối duy nhất, tối thiểu cần (C - 1) bước cầu nối.
           - Phạt: (C_B - 1) * 2 + (C_W - 1) * 2.
        2. Khoảng cách Manhattan ngắn nhất giữa các thành phần rời rạc (MST Bridging Distance):
           - Ước lượng số ô tối thiểu cần điền để nối liền các đảo độc lập.
        3. Mức độ căng thẳng 2x2 (Near 2x2 Tension):
           - Đếm số khối 2x2 đã có 3 ô cùng màu (nguy cơ bùng nổ xung đột nếu ô còn lại điền sai).
        Khi bàn cờ đạt trạng thái giải hoàn chỉnh: h(n) = 0.
        """
        h = 0.0

        b_comps = self.get_components(self.BLACK, include_empty=False)
        w_comps = self.get_components(self.WHITE, include_empty=False)

        num_b = len(b_comps)
        num_w = len(w_comps)

        # Phạt số lượng thành phần phân mảnh
        if num_b > 1:
            h += (num_b - 1) * 2.0
            # Khoảng cách Manhattan xấp xỉ giữa các đảo Đen
            min_dist_sum = 0
            for i in range(num_b - 1):
                best_d = float("inf")
                for r1, c1 in b_comps[i]:
                    for r2, c2 in b_comps[i + 1]:
                        d = abs(r1 - r2) + abs(c1 - c2) - 1
                        if d < best_d:
                            best_d = d
                min_dist_sum += best_d
            h += min_dist_sum * 0.5

        if num_w > 1:
            h += (num_w - 1) * 2.0
            min_dist_sum = 0
            for i in range(num_w - 1):
                best_d = float("inf")
                for r1, c1 in w_comps[i]:
                    for r2, c2 in w_comps[i + 1]:
                        d = abs(r1 - r2) + abs(c1 - c2) - 1
                        if d < best_d:
                            best_d = d
                min_dist_sum += best_d
            h += min_dist_sum * 0.5

        # Đếm nguy cơ 2x2 (Near 2x2 tension)
        grid = self.grid
        tension = 0
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                cells = [grid[r][c], grid[r][c + 1], grid[r + 1][c], grid[r + 1][c + 1]]
                b_cnt = cells.count(self.BLACK)
                w_cnt = cells.count(self.WHITE)
                e_cnt = cells.count(self.EMPTY)
                if e_cnt == 1:
                    if b_cnt == 3 or w_cnt == 3:
                        tension += 1
                elif e_cnt == 0:
                    if b_cnt == 4 or w_cnt == 4:
                        tension += 10

        h += tension * 1.0

        return h

    # ==========================================================================
    # CÁC THAO TÁC GÁN / HOÀN TÁC TRÊN BÀN CỜ VÀ GHI LỊCH SỬ
    # ==========================================================================
    def assign(self, r: int, c: int, color: str, action_type: str = "assign"):
        """Gán màu cho ô và lưu lại lịch sử."""
        self.grid[r][c] = color
        self.history_steps.append((action_type, r, c, color))

    def unassign(self, r: int, c: int, action_type: str = "backtrack"):
        """Hoàn tác ô về trạng thái trống và lưu lại lịch sử."""
        self.grid[r][c] = self.EMPTY
        self.history_steps.append((action_type, r, c, self.EMPTY))
