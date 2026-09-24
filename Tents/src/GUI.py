"""
MODULE: GUI.py
CÔNG NGHỆ: 100% Python kết hợp Pygame (Đồ họa trực quan 60 FPS)
           và Tkinter (Bộ chọn file native, xuất báo cáo).

TÍNH NĂNG CHÍNH:
1. Đồ họa Vector (Vector Sprites) tự vẽ 100% sắc nét cho Cây thông, Lều cắm trại, Cỏ.
2. Đa luồng (Multi-threading): Chạy thuật toán AI trên luồng nền (Worker Thread),
   tuyệt đối KHÔNG BAO GIỜ bị đơ cửa sổ hoặc "(Not Responding)" ngay cả trên map 30x30.
3. Cơ chế kiểm soát an toàn (Safety Bounds): Giới hạn bước lưu vết và thời gian tìm kiếm
   (Timeout) để ngăn chặn tuyệt đối tình trạng tràn bộ nhớ RAM.
4. Trình diễn Step-by-Step linh hoạt (Play, Pause, Step Next/Prev, Jump First/Last, Scrub Bar).
5. Chế độ So sánh Side-by-side (Benchmark Mode) xuất file báo cáo TXT.
6. Chế độ Tự chơi (Manual Play Mode) kiểm tra luật thời gian thực.
"""

import os
import sys
import time
import math
import random
import copy
import tracemalloc
import threading
import pygame
import tkinter as tk
from tkinter import filedialog, messagebox

# Thiết lập UTF-8 cho console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được các module trong thư mục src/
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "inputs"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from board import TentsBoard, load_input_file
from dfs import DFSSolver
from hill_climbing import HillClimbingSolver


# ==============================================================================
# HẰNG SỐ MÀU SẮC VÀ THIẾT KẾ (COLOR PALETTE & THEME)
# ==============================================================================
WINDOW_WIDTH = 1300
WINDOW_HEIGHT = 820
FPS = 60

# Palette màu giao diện hiện đại (Modern Dark Dashboard)
COLOR_BG = (15, 20, 32)
COLOR_PANEL = (24, 31, 48)
COLOR_CARD = (32, 42, 64)
COLOR_CARD_BORDER = (46, 60, 92)
COLOR_CARD_HOVER = (40, 52, 80)

# Chữ và nhãn
COLOR_TEXT_WHITE = (245, 248, 255)
COLOR_TEXT_MUTED = (145, 158, 185)
COLOR_TEXT_GOLD = (255, 209, 102)

# Màu chủ đạo bàn cờ (Forest Grass Theme)
COLOR_BOARD_BG = (238, 247, 238)
COLOR_CELL_LIGHT = (232, 245, 233)
COLOR_CELL_DARK = (219, 237, 220)
COLOR_GRID_LINE = (185, 215, 185)
COLOR_CELL_HOVER = (255, 245, 157)
COLOR_ACTIVE_CELL = (0, 230, 118)
COLOR_CONFLICT_CELL = (255, 205, 210)

# Màu các nút chức năng và thuật toán
COLOR_DFS = (255, 140, 0)          # Cam hổ phách
COLOR_DFS_HOVER = (255, 167, 38)
COLOR_HC = (156, 39, 176)          # Tím hoàng gia
COLOR_HC_HOVER = (186, 104, 200)
COLOR_COMPARE = (0, 184, 212)      # Cyan sáng
COLOR_COMPARE_HOVER = (38, 198, 218)
COLOR_SUCCESS = (46, 204, 113)     # Xanh lục thành công
COLOR_DANGER = (235, 87, 87)       # Đỏ cảnh báo / Quay lui
COLOR_INFO = (52, 152, 219)        # Xanh lam thông tin


# ==============================================================================
# BỘ GIẢI STEP-BY-STEP DÀNH CHO HILL CLIMBING (CÓ GIỚI HẠN AN TOÀN)
# ==============================================================================
class SteppedHillClimbingSolver(HillClimbingSolver):
    """
    Kế thừa HillClimbingSolver, bổ sung chức năng ghi nhận lại các bước
    chuyển dịch trạng thái để phục vụ diễn hoạt Step-by-Step và kiểm soát timeout.
    """
    def __init__(self, board: TentsBoard, max_restarts: int = 100, max_steps_per_restart: int = 250, max_sideways: int = 20, timeout_sec: float = 6.0):
        super().__init__(board, max_restarts, max_steps_per_restart, max_sideways, timeout_sec)
        self.recorded_steps = []
        self.timed_out = False

    def solve_recorded(self):
        tracemalloc.start()
        start_time = time.perf_counter()

        best_state = None
        best_score = float("inf")
        self.recorded_steps = []
        MAX_STEPS_CAP = 5000

        for restart_count in range(self.max_restarts):
            if (time.perf_counter() - start_time) > self.timeout_sec:
                self.timed_out = True
                break

            self.total_restarts = restart_count + 1
            current_state = self._generate_random_state()
            current_score = self._calculate_heuristic(current_state)

            if len(self.recorded_steps) < MAX_STEPS_CAP:
                self.recorded_steps.append({
                    "action": "HC_RESTART",
                    "restart_num": self.total_restarts,
                    "state": list(current_state),
                    "score": current_score,
                    "log": f"Khoi tao ngau nhien #{self.total_restarts} (Diem vi pham h = {current_score})"
                })

            if current_score < best_score:
                best_score = current_score
                best_state = current_state

            sideways_count = 0

            for _ in range(self.max_steps_per_restart):
                if current_score == 0:
                    best_state = current_state
                    best_score = 0
                    self.solved = True
                    break

                best_neighbor = None
                best_neighbor_score = current_score
                best_move_info = None

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
                            best_move_info = (i, current_pos, slot)
                        elif neighbor_score == best_neighbor_score and best_neighbor is None and sideways_count < self.max_sideways:
                            best_neighbor_score = neighbor_score
                            best_neighbor = neighbor_state
                            best_move_info = (i, current_pos, slot)

                if best_neighbor is not None and best_neighbor_score < current_score:
                    tree_idx, old_pos, new_pos = best_move_info
                    current_state = best_neighbor
                    prev_score = current_score
                    current_score = best_neighbor_score
                    if current_score < best_score:
                        best_score = current_score
                        best_state = current_state
                    sideways_count = 0

                    if len(self.recorded_steps) < MAX_STEPS_CAP:
                        self.recorded_steps.append({
                            "action": "HC_MOVE",
                            "tree_idx": tree_idx,
                            "old_pos": old_pos,
                            "new_pos": new_pos,
                            "state": list(current_state),
                            "score": current_score,
                            "log": f"Doi leu cay #{tree_idx+1} tu {old_pos} -> {new_pos} (h: {prev_score} -> {current_score})"
                        })

                elif best_neighbor is not None and best_neighbor_score == current_score and sideways_count < self.max_sideways:
                    tree_idx, old_pos, new_pos = best_move_info
                    current_state = best_neighbor
                    sideways_count += 1

                    if len(self.recorded_steps) < MAX_STEPS_CAP:
                        self.recorded_steps.append({
                            "action": "HC_SIDEWAYS",
                            "tree_idx": tree_idx,
                            "old_pos": old_pos,
                            "new_pos": new_pos,
                            "state": list(current_state),
                            "score": current_score,
                            "log": f"Buoc di ngang (Sideways #{sideways_count}) leu cay #{tree_idx+1} -> {new_pos} (h = {current_score})"
                        })
                else:
                    if len(self.recorded_steps) < MAX_STEPS_CAP:
                        self.recorded_steps.append({
                            "action": "HC_STUCK",
                            "state": list(current_state),
                            "score": current_score,
                            "log": f"Ket tai Cuc tieu dia phuong (h = {current_score}) -> Chuan bi Restart!"
                        })
                    break

            if self.solved:
                self.recorded_steps.append({
                    "action": "HC_SOLVED",
                    "state": list(best_state),
                    "score": 0,
                    "log": f"DA TIM THAY LOI GIAI TOI UU (h = 0) sau {self.total_restarts} lan Restart!"
                })
                break

        end_time = time.perf_counter()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        if self.solved and best_state:
            self._apply_solution_to_board(best_state)

        return {
            "solved": self.solved,
            "timed_out": self.timed_out,
            "execution_time_sec": end_time - start_time,
            "peak_memory_kb": peak_mem / 1024.0,
            "states_evaluated": self.states_evaluated,
            "restarts": self.total_restarts,
            "final_heuristic": best_score,
            "steps": self.recorded_steps
        }


# ==============================================================================
# HÀM VẼ ĐỒ HỌA VECTOR NÉT CAO (HIGH-DPI VECTOR SPRITES & ICONS)
# ==============================================================================
class VectorSprites:
    """Vẽ các biểu tượng Cây, Lều, Cỏ và Icon điều khiển hoàn toàn bằng hình học vector."""

    @staticmethod
    def draw_tree(surface: pygame.Surface, cx: int, cy: int, size: int):
        """Vẽ cây thông xanh với 3 tầng tán lá và thân gỗ."""
        scale = size / 50.0

        # 1. Thân cây
        trunk_w = max(4, int(10 * scale))
        trunk_h = max(6, int(14 * scale))
        trunk_x = cx - trunk_w // 2
        trunk_y = cy + int(12 * scale)
        pygame.draw.rect(surface, (93, 64, 55), (trunk_x, trunk_y, trunk_w, trunk_h), border_radius=2)
        pygame.draw.rect(surface, (62, 39, 35), (trunk_x, trunk_y, trunk_w, trunk_h), 1, border_radius=2)

        # 2. Ba tầng tán lá cây thông (Dưới -> Giữa -> Đỉnh)
        tiers = [
            (cy + int(14 * scale), int(22 * scale), int(16 * scale), (39, 134, 49)),
            (cy + int(3 * scale),  int(18 * scale), int(15 * scale), (46, 160, 58)),
            (cy - int(8 * scale),  int(14 * scale), int(14 * scale), (56, 185, 70)),
        ]

        for base_y, half_w, height, color in tiers:
            top_y = base_y - height
            pts = [
                (cx, top_y),
                (cx - half_w, base_y),
                (cx + half_w, base_y)
            ]
            pygame.draw.polygon(surface, color, pts)
            pygame.draw.polygon(surface, (27, 94, 32), pts, 1)

            highlight_pts = [
                (cx, top_y),
                (cx, base_y),
                (cx + half_w, base_y)
            ]
            bright_color = (min(255, color[0] + 15), min(255, color[1] + 15), min(255, color[2] + 15))
            pygame.draw.polygon(surface, bright_color, highlight_pts)

    @staticmethod
    def draw_tent(surface: pygame.Surface, cx: int, cy: int, size: int, active: bool = False):
        """Vẽ lều trại phong cách cắm trại với cửa lều và dây neo."""
        scale = size / 50.0

        if active:
            glow_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 215, 0, 90), (size // 2, size // 2), int(22 * scale))
            surface.blit(glow_surf, (cx - size // 2, cy - size // 2))

        peg_l = (cx - int(21 * scale), cy + int(15 * scale))
        peg_r = (cx + int(21 * scale), cy + int(15 * scale))
        top_pt = (cx, cy - int(16 * scale))

        pygame.draw.line(surface, (120, 120, 120), top_pt, peg_l, max(1, int(1.5 * scale)))
        pygame.draw.line(surface, (120, 120, 120), top_pt, peg_r, max(1, int(1.5 * scale)))

        front_left = (cx - int(15 * scale), cy + int(14 * scale))
        front_right = (cx + int(5 * scale), cy + int(14 * scale))
        back_right = (cx + int(17 * scale), cy + int(10 * scale))

        roof_side_pts = [top_pt, front_right, back_right]
        pygame.draw.polygon(surface, (230, 74, 25), roof_side_pts)
        pygame.draw.polygon(surface, (191, 54, 12), roof_side_pts, 1)

        tent_front_pts = [top_pt, front_left, front_right]
        pygame.draw.polygon(surface, (255, 112, 67), tent_front_pts)
        pygame.draw.polygon(surface, (216, 67, 21), tent_front_pts, 1)

        door_top = (cx - int(3 * scale), cy - int(2 * scale))
        door_l = (cx - int(10 * scale), cy + int(14 * scale))
        door_r = (cx + int(2 * scale), cy + int(14 * scale))
        pygame.draw.polygon(surface, (120, 20, 0), [door_top, door_l, door_r])

        pygame.draw.circle(surface, (80, 80, 80), peg_l, max(2, int(2.5 * scale)))
        pygame.draw.circle(surface, (80, 80, 80), peg_r, max(2, int(2.5 * scale)))

    @staticmethod
    def draw_grass(surface: pygame.Surface, cx: int, cy: int, size: int):
        """Vẽ biểu tượng cỏ/dấu chéo màu xanh lá trang nhã."""
        scale = size / 50.0
        r = max(3, int(6 * scale))

        pygame.draw.line(surface, (129, 199, 132), (cx - r, cy - r), (cx + r, cy + r), max(2, int(2.5 * scale)))
        pygame.draw.line(surface, (129, 199, 132), (cx + r, cy - r), (cx - r, cy + r), max(2, int(2.5 * scale)))
        pygame.draw.circle(surface, (165, 214, 167), (cx, cy), max(2, int(2 * scale)))

    @staticmethod
    def draw_icon_first(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pygame.draw.rect(surface, color, (cx - 7, cy - 6, 3, 12))
        pts = [(cx + 6, cy - 6), (cx + 6, cy + 6), (cx - 3, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_prev(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx + 4, cy - 6), (cx + 4, cy + 6), (cx - 4, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_next(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 4, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_last(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx - 6, cy - 6), (cx - 6, cy + 6), (cx + 3, cy)]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.rect(surface, color, (cx + 5, cy - 6, 3, 12))

    @staticmethod
    def draw_icon_play(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 6, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_pause(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pygame.draw.rect(surface, color, (cx - 5, cy - 6, 3, 12))
        pygame.draw.rect(surface, color, (cx + 2, cy - 6, 3, 12))


# ==============================================================================
# HỆ THỐNG GIAO DIỆN NGƯỜI DÙNG WIDGETS
# ==============================================================================
class Button:
    def __init__(self, rect: tuple, text: str, bg_color: tuple, hover_color: tuple, text_color: tuple = COLOR_TEXT_WHITE, font_size: int = 14, icon_type: str = ""):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.font_size = font_size
        self.icon_type = icon_type
        self.is_hovered = False
        self.enabled = True

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        color = self.hover_color if (self.is_hovered and self.enabled) else self.bg_color
        if not self.enabled:
            color = (50, 58, 76)

        shadow_rect = self.rect.move(0, 2)
        pygame.draw.rect(surface, (10, 14, 22), shadow_rect, border_radius=6)

        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        border_color = (255, 255, 255, 45) if self.is_hovered else (0, 0, 0, 45)
        pygame.draw.rect(surface, border_color, self.rect, 1, border_radius=6)

        icon_color = self.text_color if self.enabled else (100, 110, 130)

        if self.icon_type == "first":
            VectorSprites.draw_icon_first(surface, self.rect, icon_color)
        elif self.icon_type == "prev":
            VectorSprites.draw_icon_prev(surface, self.rect, icon_color)
        elif self.icon_type == "next":
            VectorSprites.draw_icon_next(surface, self.rect, icon_color)
        elif self.icon_type == "last":
            VectorSprites.draw_icon_last(surface, self.rect, icon_color)
        elif self.icon_type == "play":
            if self.text:
                icon_rect = pygame.Rect(self.rect.x + 10, self.rect.y, 16, self.rect.height)
                VectorSprites.draw_icon_play(surface, icon_rect, icon_color)
                text_surf = font.render(self.text, True, icon_color)
                surface.blit(text_surf, (self.rect.x + 30, self.rect.centery - text_surf.get_height() // 2))
            else:
                VectorSprites.draw_icon_play(surface, self.rect, icon_color)
        elif self.icon_type == "pause":
            if self.text:
                icon_rect = pygame.Rect(self.rect.x + 10, self.rect.y, 16, self.rect.height)
                VectorSprites.draw_icon_pause(surface, icon_rect, icon_color)
                text_surf = font.render(self.text, True, icon_color)
                surface.blit(text_surf, (self.rect.x + 30, self.rect.centery - text_surf.get_height() // 2))
            else:
                VectorSprites.draw_icon_pause(surface, self.rect, icon_color)
        else:
            if self.text:
                text_surf = font.render(self.text, True, icon_color)
                text_rect = text_surf.get_rect(center=self.rect.center)
                surface.blit(text_surf, text_rect)

    def check_hover(self, mouse_pos: tuple):
        self.is_hovered = self.rect.collidepoint(mouse_pos)
        return self.is_hovered

    def is_clicked(self, mouse_pos: tuple, event_type: int):
        return self.enabled and self.rect.collidepoint(mouse_pos) and event_type == pygame.MOUSEBUTTONDOWN


class ScrubBar:
    """Thanh trượt timeline điều hướng bước đi AI."""
    def __init__(self, rect: tuple):
        self.rect = pygame.Rect(rect)
        self.progress = 0.0
        self.is_dragging = False

    def draw(self, surface: pygame.Surface, current_step: int, total_steps: int):
        pygame.draw.rect(surface, (45, 55, 80), self.rect, border_radius=4)

        fill_width = int(self.rect.width * self.progress)
        if fill_width > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            pygame.draw.rect(surface, COLOR_SUCCESS, fill_rect, border_radius=4)

        thumb_x = self.rect.x + fill_width
        thumb_y = self.rect.centery
        pygame.draw.circle(surface, (255, 255, 255), (thumb_x, thumb_y), 8)
        pygame.draw.circle(surface, COLOR_PANEL, (thumb_x, thumb_y), 4)

    def handle_event(self, event, total_steps: int):
        if total_steps <= 1:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) or abs(event.pos[0] - (self.rect.x + self.rect.width * self.progress)) < 15:
                self.is_dragging = True
                return self._update_from_mouse(event.pos[0], total_steps)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.is_dragging = False

        elif event.type == pygame.MOUSEMOTION and self.is_dragging:
            return self._update_from_mouse(event.pos[0], total_steps)

        return None

    def _update_from_mouse(self, mouse_x: int, total_steps: int) -> int:
        clamped_x = max(self.rect.x, min(mouse_x, self.rect.right))
        self.progress = (clamped_x - self.rect.x) / float(self.rect.width)
        step_idx = int(round(self.progress * (total_steps - 1)))
        return step_idx

    def set_step(self, step_idx: int, total_steps: int):
        if total_steps > 1:
            self.progress = max(0.0, min(1.0, step_idx / float(total_steps - 1)))
        else:
            self.progress = 0.0


# ==============================================================================
# LỚP ỨNG DỤNG GIAO DIỆN CHÍNH (MAIN GUI CONTROLLER)
# ==============================================================================
class TentsGameGUI:
    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Tents & Trees AI Solver - BTL1 Mon Tri Tue Nhan Tao")
        self.clock = pygame.time.Clock()

        # Khởi tạo Phông chữ hệ thống
        self.font_title = pygame.font.SysFont(["Segoe UI", "Arial", "sans-serif"], 19, bold=True)
        self.font_bold = pygame.font.SysFont(["Segoe UI", "Arial", "sans-serif"], 13, bold=True)
        self.font_medium = pygame.font.SysFont(["Segoe UI", "Arial", "sans-serif"], 12)
        self.font_small = pygame.font.SysFont(["Segoe UI", "Arial", "sans-serif"], 11)
        self.font_badge = pygame.font.SysFont(["Segoe UI", "Arial", "sans-serif"], 13, bold=True)
        self.font_large = pygame.font.SysFont(["Segoe UI", "Arial", "sans-serif"], 22, bold=True)

        # Quét danh sách các câu đố
        self.all_puzzle_files = self._scan_puzzle_files()
        self.active_category = "ALL"
        self.filtered_puzzle_files = list(self.all_puzzle_files)
        self.current_puzzle_index = 0
        self.current_filepath = ""
        self.puzzle_data = None
        self.board = None

        # Trạng thái diễn hoạt Step-by-Step AI
        self.history_steps = []
        self.current_step_index = -1
        self.is_playing = False
        self.current_algo = "NONE"
        self.playback_speed_idx = 1
        self.speeds = [
            ("0.5x", 400),
            ("1.0x", 180),
            ("2.0x", 80),
            ("5.0x", 25),
            ("10.0x", 8),
            ("Max", 0)
        ]
        self.last_step_tick = 0

        # Trạng thái luồng chạy nền (Worker Thread)
        self.is_solving = False
        self.solving_algo_name = ""
        self.solving_start_time = 0.0
        self.solver_thread = None

        # Thông số đo đạc Benchmark
        self.metrics = {
            "time_sec": 0.0,
            "peak_mem_kb": 0.0,
            "nodes_or_states": 0,
            "backtracks_or_restarts": 0,
            "solved": False,
            "timed_out": False,
            "algo_name": ""
        }

        # Trạng thái Chế độ Tự chơi
        self.manual_mode = False
        self.player_grid = []
        self.player_won = False

        # Trạng thái Cửa sổ Modal So sánh Side-by-side
        self.show_compare_modal = False
        self.compare_results = None

        # Khởi tạo các nút bấm giao diện
        self._init_buttons()

        # Nạp câu đố đầu tiên
        if self.filtered_puzzle_files:
            self.load_puzzle(self.filtered_puzzle_files[0])

    def _scan_puzzle_files(self) -> list:
        if not os.path.exists(INPUTS_DIR):
            os.makedirs(INPUTS_DIR, exist_ok=True)
            return []

        all_files = [
            os.path.join(INPUTS_DIR, f)
            for f in sorted(os.listdir(INPUTS_DIR))
            if f.endswith(".txt")
        ]
        return all_files

    def set_category_filter(self, category_key: str):
        if self.is_solving:
            return
        self.active_category = category_key
        if category_key == "ALL":
            self.filtered_puzzle_files = list(self.all_puzzle_files)
        elif category_key == "6x6":
            self.filtered_puzzle_files = [f for f in self.all_puzzle_files if "6x6" in os.path.basename(f)]
        elif category_key == "8x8":
            self.filtered_puzzle_files = [f for f in self.all_puzzle_files if "8x8" in os.path.basename(f)]
        elif category_key == "10x10":
            self.filtered_puzzle_files = [f for f in self.all_puzzle_files if "10x10" in os.path.basename(f)]
        elif category_key == "15x15":
            self.filtered_puzzle_files = [f for f in self.all_puzzle_files if "15x15" in os.path.basename(f)]
        elif category_key == "SPECIAL":
            self.filtered_puzzle_files = [f for f in self.all_puzzle_files if "special" in os.path.basename(f)]

        if self.filtered_puzzle_files:
            self.current_puzzle_index = 0
            self.load_puzzle(self.filtered_puzzle_files[0])

    def _init_buttons(self):
        panel_x = 750

        # Tabs bộ lọc kích thước
        self.filter_buttons = [
            Button((panel_x + 10, 78, 65, 26), "Tat ca", (50, 60, 85), (70, 85, 120), font_size=11),
            Button((panel_x + 80, 78, 60, 26), "6x6", (50, 60, 85), (70, 85, 120), font_size=11),
            Button((panel_x + 145, 78, 60, 26), "8x8", (50, 60, 85), (70, 85, 120), font_size=11),
            Button((panel_x + 210, 78, 65, 26), "10x10", (50, 60, 85), (70, 85, 120), font_size=11),
            Button((panel_x + 280, 78, 65, 26), "15x15", (50, 60, 85), (70, 85, 120), font_size=11),
            Button((panel_x + 350, 78, 70, 26), "Special", (50, 60, 85), (70, 85, 120), font_size=11),
        ]

        # CARD 1: Điều hướng đề
        btn_row_y = 142
        self.btn_prev_puzzle = Button((panel_x + 10, btn_row_y, 85, 32), "< Truoc", (45, 55, 80), (60, 75, 105), font_size=12)
        self.btn_next_puzzle = Button((panel_x + 102, btn_row_y, 85, 32), "Sau >", (45, 55, 80), (60, 75, 105), font_size=12)
        self.btn_random_puzzle = Button((panel_x + 194, btn_row_y, 105, 32), "Ngau nhien", (45, 55, 80), (60, 75, 105), font_size=12)
        self.btn_browse = Button((panel_x + 306, btn_row_y, 105, 32), "Mo file...", (41, 128, 185), (52, 152, 219), font_size=12)
        self.btn_reset_board = Button((panel_x + 418, btn_row_y, 85, 32), "Dat lai", (60, 70, 95), (80, 95, 125), font_size=12)

        # CARD 2: Chọn thuật toán & chế độ
        self.btn_run_dfs = Button((panel_x + 10, 225, 155, 36), "Chay DFS", COLOR_DFS, COLOR_DFS_HOVER, font_size=13)
        self.btn_run_hc = Button((panel_x + 175, 225, 165, 36), "Hill Climbing", COLOR_HC, COLOR_HC_HOVER, font_size=13)
        self.btn_compare = Button((panel_x + 350, 225, 155, 36), "So sanh AI", COLOR_COMPARE, COLOR_COMPARE_HOVER, font_size=13)
        self.btn_toggle_manual = Button((panel_x + 10, 270, 495, 32), "Chuyen sang Che do Tu choi (Manual Mode)", (46, 125, 50), (56, 142, 60), font_size=12)

        # CARD 3: Điều khiển hoạt cảnh
        btn_y = 352
        self.btn_step_first = Button((panel_x + 10, btn_y, 45, 30), "", (45, 55, 80), (65, 80, 110), icon_type="first")
        self.btn_step_prev = Button((panel_x + 62, btn_y, 45, 30), "", (45, 55, 80), (65, 80, 110), icon_type="prev")
        self.btn_play_pause = Button((panel_x + 114, btn_y, 90, 30), "Phat", COLOR_SUCCESS, (56, 220, 125), icon_type="play")
        self.btn_step_next = Button((panel_x + 211, btn_y, 45, 30), "", (45, 55, 80), (65, 80, 110), icon_type="next")
        self.btn_step_last = Button((panel_x + 263, btn_y, 45, 30), "", (45, 55, 80), (65, 80, 110), icon_type="last")
        self.btn_speed = Button((panel_x + 318, btn_y, 85, 30), "1.0x", (60, 70, 95), (80, 95, 125))
        self.btn_clear_step = Button((panel_x + 410, btn_y, 95, 30), "Huy buoc", (198, 40, 40), (229, 57, 53))

        # Thanh kéo Scrub Bar
        self.scrub_bar = ScrubBar((panel_x + 10, 395, 495, 12))

        # Nút Hủy tính toán khi đang chạy
        self.btn_cancel_solve = Button((570, 420, 160, 36), "Huy tim kiem", (198, 40, 40), (229, 57, 53))

        # Modal So sánh Buttons
        self.btn_modal_export = Button((940, 680, 160, 38), "Xuat file Bao cao", COLOR_SUCCESS, (56, 220, 125))
        self.btn_modal_close = Button((1115, 680, 100, 38), "Dong", (100, 110, 130), (130, 140, 160))

    def reset_board_state(self):
        """Xoa sach hoan toan trang thai leu cua bat ky giai thuat nao truoc do."""
        self.is_playing = False
        self.btn_play_pause.text = "Phat"
        self.btn_play_pause.icon_type = "play"
        self.history_steps = []
        self.current_step_index = -1
        self.scrub_bar.set_step(0, 1)

        if self.puzzle_data:
            self.board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            self.player_grid = [row[:] for row in self.puzzle_data["grid"]]
            self.player_won = False

    def load_puzzle(self, filepath: str):
        if self.is_solving:
            return
        try:
            self.puzzle_data = load_input_file(filepath)
            self.current_filepath = filepath
            if filepath in self.filtered_puzzle_files:
                self.current_puzzle_index = self.filtered_puzzle_files.index(filepath)

            self.reset_board_state()
            self.current_algo = "NONE"

            self.metrics = {
                "time_sec": 0.0,
                "peak_mem_kb": 0.0,
                "nodes_or_states": 0,
                "backtracks_or_restarts": 0,
                "solved": False,
                "timed_out": False,
                "algo_name": ""
            }
        except Exception as e:
            print(f"[!] Loi khi nap file {filepath}: {e}")

    # ==================== CƠ CHẾ ĐA LUỒNG CHO SOLVER ====================
    def run_dfs(self):
        if self.is_solving or not self.puzzle_data:
            return

        self.reset_board_state()
        self.is_solving = True
        self.solving_algo_name = "DFS"
        self.solving_start_time = time.time()
        self.current_algo = "DFS"
        self.manual_mode = False

        self.solver_thread = threading.Thread(target=self._worker_run_dfs, daemon=True)
        self.solver_thread.start()

    def _worker_run_dfs(self):
        try:
            worker_board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            solver = DFSSolver(worker_board, max_nodes=120000, timeout_sec=5.0)
            res = solver.solve()

            self.history_steps = list(worker_board.history_steps)
            self.metrics = {
                "time_sec": res["execution_time_sec"],
                "peak_mem_kb": res["peak_memory_kb"],
                "nodes_or_states": res["nodes_explored"],
                "backtracks_or_restarts": res["backtracks"],
                "solved": res["solved"],
                "timed_out": res.get("timed_out", False),
                "algo_name": "DFS (Depth-First Search)"
            }

            self.board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            self.current_step_index = -1
            self.is_playing = res["solved"]
            self.btn_play_pause.text = "Tam dung" if self.is_playing else "Phat"
            self.btn_play_pause.icon_type = "pause" if self.is_playing else "play"
        finally:
            self.is_solving = False

    def run_hill_climbing(self):
        if self.is_solving or not self.puzzle_data:
            return

        self.reset_board_state()
        self.is_solving = True
        self.solving_algo_name = "HILL CLIMBING"
        self.solving_start_time = time.time()
        self.current_algo = "HILL_CLIMBING"
        self.manual_mode = False

        self.solver_thread = threading.Thread(target=self._worker_run_hc, daemon=True)
        self.solver_thread.start()

    def _worker_run_hc(self):
        try:
            worker_board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            solver = SteppedHillClimbingSolver(worker_board, max_restarts=80, max_steps_per_restart=200, timeout_sec=5.0)
            res = solver.solve_recorded()

            self.history_steps = list(res["steps"])
            self.metrics = {
                "time_sec": res["execution_time_sec"],
                "peak_mem_kb": res["peak_memory_kb"],
                "nodes_or_states": res["states_evaluated"],
                "backtracks_or_restarts": res["restarts"],
                "solved": res["solved"],
                "timed_out": res.get("timed_out", False),
                "algo_name": "Hill Climbing (Random Restart)"
            }

            self.board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            self.current_step_index = -1
            self.is_playing = res["solved"]
            self.btn_play_pause.text = "Tam dung" if self.is_playing else "Phat"
            self.btn_play_pause.icon_type = "pause" if self.is_playing else "play"
        finally:
            self.is_solving = False

    def run_comparison(self):
        if self.is_solving or not self.puzzle_data:
            return

        self.reset_board_state()
        self.is_solving = True
        self.solving_algo_name = "SO SANH (BENCHMARK)"
        self.solving_start_time = time.time()

        self.solver_thread = threading.Thread(target=self._worker_run_compare, daemon=True)
        self.solver_thread.start()

    def _worker_run_compare(self):
        try:
            board_dfs = TentsBoard(
                self.puzzle_data["rows"], self.puzzle_data["cols"],
                self.puzzle_data["row_constraints"], self.puzzle_data["col_constraints"],
                self.puzzle_data["grid"], self.puzzle_data["trees"]
            )
            dfs_solver = DFSSolver(board_dfs, max_nodes=100000, timeout_sec=5.0)
            dfs_res = dfs_solver.solve()

            board_hc = TentsBoard(
                self.puzzle_data["rows"], self.puzzle_data["cols"],
                self.puzzle_data["row_constraints"], self.puzzle_data["col_constraints"],
                self.puzzle_data["grid"], self.puzzle_data["trees"]
            )
            hc_solver = HillClimbingSolver(board_hc, max_restarts=80, max_steps_per_restart=200, timeout_sec=5.0)
            hc_res = hc_solver.solve()

            self.compare_results = {
                "filename": os.path.basename(self.current_filepath),
                "size": f"{self.puzzle_data['rows']}x{self.puzzle_data['cols']}",
                "trees": len(self.puzzle_data["trees"]),
                "dfs": dfs_res,
                "hc": hc_res
            }
            self.show_compare_modal = True
        finally:
            self.is_solving = False

    def export_benchmark_file(self):
        if not self.compare_results:
            return

        report_path = os.path.join(SRC_DIR, "benchmark_report.txt")
        c = self.compare_results
        dfs = c["dfs"]
        hc = c["hc"]

        content = f"""================================================================================
BAO CAO THUC NGHIEM DOI SANH THUAT TOAN - PUZZLE TENTS & TREES
================================================================================
Bai toan kiem thu      : {c['filename']}
Kich thuoc luoi co     : {c['size']}
Tong so cay / so leu   : {c['trees']} cay
Thoi diem thuc hien    : {time.strftime('%Y-%m-%d %H:%M:%S')}
--------------------------------------------------------------------------------
THONG SO DO DAC                    DFS (Blind Search)         Hill Climbing (Heuristic)
--------------------------------------------------------------------------------
Trang thai giai thanh cong         {'CO (Thanh cong)' if dfs['solved'] else 'KHONG'}                  {'CO (Thanh cong)' if hc['solved'] else 'KHONG'}
Thoi gian thuc thi (giay)          {dfs['execution_time_sec']:.6f} s                 {hc['execution_time_sec']:.6f} s
Bo nho RAM dinh (KB)               {dfs['peak_memory_kb']:.2f} KB                   {hc['peak_memory_kb']:.2f} KB
So node / trang thai da duyet      {dfs['nodes_explored']} nodes                    {hc['states_evaluated']} states
So lan quay lui / Restart          {dfs['backtracks']} lan quay lui               {hc['restarts']} lan restart
Gia tri xung dot Heuristic h(S)    0                          {hc['final_heuristic']}
--------------------------------------------------------------------------------
DANH GIA VA NHAN XET:
1. Thuat toan DFS ket hop Backtracking va Cat tia (Pruning) bao dam tinh day du
   (Completeness), tim ra nghiem chac chan khi ton tai va tieu ton rat it bo nho.
2. Thuat toan Hill Climbing dua tren ham Heuristic dem xung dot h(S) ket hop Random
   Restart giup giai phong bay cuc tieu dia phuong, toc do hoi tu nhanh tren cac
   bai toan vua va nho.
================================================================================
"""
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(content)
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Thanh cong", f"Da xuat bao cao thanh cong ra file:\n{report_path}")
            root.destroy()
        except Exception as e:
            print(f"[!] Loi xuat file: {e}")

    def browse_custom_file(self):
        if self.is_solving:
            return
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Chon file bai toan Tents (.txt)",
            initialdir=INPUTS_DIR,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        root.destroy()
        if selected and os.path.exists(selected):
            self.load_puzzle(selected)

    def step_forward(self):
        if not self.history_steps or self.current_step_index >= len(self.history_steps) - 1:
            self.is_playing = False
            self.btn_play_pause.text = "Phat"
            self.btn_play_pause.icon_type = "play"
            return

        self.current_step_index += 1
        self._apply_current_step()
        self.scrub_bar.set_step(self.current_step_index, len(self.history_steps))

    def step_backward(self):
        if not self.history_steps or self.current_step_index <= 0:
            return

        self.current_step_index -= 1
        self._replay_up_to_step(self.current_step_index)
        self.scrub_bar.set_step(self.current_step_index, len(self.history_steps))

    def jump_to_step(self, target_idx: int):
        if not self.history_steps:
            return
        target_idx = max(0, min(target_idx, len(self.history_steps) - 1))
        self.current_step_index = target_idx
        self._replay_up_to_step(self.current_step_index)
        self.scrub_bar.set_step(self.current_step_index, len(self.history_steps))

    def _apply_current_step(self):
        if not self.history_steps or self.current_step_index < 0:
            return
        self._replay_up_to_step(self.current_step_index)

    def _replay_up_to_step(self, target_idx: int):
        self.board.grid = [row[:] for row in self.puzzle_data["grid"]]
        self.board.row_tent_counts = [0] * self.board.rows
        self.board.col_tent_counts = [0] * self.board.cols
        self.board.tent_to_tree.clear()
        self.board.tree_to_tent.clear()

        if not self.history_steps or target_idx < 0:
            return

        target_idx = max(0, min(target_idx, len(self.history_steps) - 1))

        if self.current_algo == "DFS":
            for i in range(target_idx + 1):
                step = self.history_steps[i]
                r, c = step["pos"]
                tree_pos = step["tree"]
                if step["action"] == "PLACE":
                    self.board.grid[r][c] = TentsBoard.TENT
                    self.board.row_tent_counts[r] += 1
                    self.board.col_tent_counts[c] += 1
                    self.board.tent_to_tree[(r, c)] = tree_pos
                    self.board.tree_to_tent[tree_pos] = (r, c)
                elif step["action"] == "REMOVE":
                    self.board.grid[r][c] = TentsBoard.EMPTY
                    self.board.row_tent_counts[r] -= 1
                    self.board.col_tent_counts[c] -= 1
                    self.board.tent_to_tree.pop((r, c), None)
                    self.board.tree_to_tent.pop(tree_pos, None)

        elif self.current_algo == "HILL_CLIMBING":
            step = self.history_steps[target_idx]
            new_grid = [row[:] for row in self.puzzle_data["grid"]]
            state = step.get("state", [])
            for i, (r, c) in enumerate(state):
                if 0 <= r < self.board.rows and 0 <= c < self.board.cols:
                    new_grid[r][c] = TentsBoard.TENT
                    self.board.row_tent_counts[r] += 1
                    self.board.col_tent_counts[c] += 1
                    if i < len(self.puzzle_data["trees"]):
                        tree_pos = self.puzzle_data["trees"][i]
                        self.board.tent_to_tree[(r, c)] = tree_pos
                        self.board.tree_to_tent[tree_pos] = (r, c)
            self.board.grid = new_grid

    def handle_manual_click(self, r: int, c: int, button: int):
        if not self.manual_mode or not self.puzzle_data or self.is_solving:
            return

        if self.puzzle_data["grid"][r][c] == TentsBoard.TREE:
            return

        current_val = self.player_grid[r][c]

        if button == 1:
            if current_val == TentsBoard.EMPTY:
                self.player_grid[r][c] = TentsBoard.TENT
            elif current_val == TentsBoard.TENT:
                self.player_grid[r][c] = TentsBoard.GRASS
            else:
                self.player_grid[r][c] = TentsBoard.EMPTY
        elif button == 3:
            if current_val == TentsBoard.GRASS:
                self.player_grid[r][c] = TentsBoard.EMPTY
            else:
                self.player_grid[r][c] = TentsBoard.GRASS

        self._check_player_win()

    def _check_player_win(self):
        rows = self.puzzle_data["rows"]
        cols = self.puzzle_data["cols"]
        tents = []

        for r in range(rows):
            for c in range(cols):
                if self.player_grid[r][c] == TentsBoard.TENT:
                    tents.append((r, c))

        if len(tents) != len(self.puzzle_data["trees"]):
            self.player_won = False
            return

        for i in range(len(tents)):
            r1, c1 = tents[i]
            for j in range(i + 1, len(tents)):
                r2, c2 = tents[j]
                if max(abs(r1 - r2), abs(c1 - c2)) <= 1:
                    self.player_won = False
                    return

        row_counts = [0] * rows
        col_counts = [0] * cols
        for r, c in tents:
            row_counts[r] += 1
            col_counts[c] += 1

        if row_counts != self.puzzle_data["row_constraints"] or col_counts != self.puzzle_data["col_constraints"]:
            self.player_won = False
            return

        for tr, tc in self.puzzle_data["trees"]:
            has_adj_tent = any(abs(tr - tr2) + abs(tc - tc2) == 1 for tr2, tc2 in tents)
            if not has_adj_tent:
                self.player_won = False
                return

        self.player_won = True

    # ==================== RENDERING PIPELINE ====================
    def draw(self):
        self.screen.fill(COLOR_BG)

        self._draw_header()
        self._draw_board()
        self._draw_controls()

        if self.manual_mode and self.player_won:
            self._draw_victory_banner()

        if self.show_compare_modal and self.compare_results:
            self._draw_compare_modal()

        # Hiển thị overlay tính toán khi Worker Thread đang giải
        if self.is_solving:
            self._draw_solving_overlay()

        pygame.display.flip()

    def _draw_header(self):
        header_rect = pygame.Rect(0, 0, WINDOW_WIDTH, 56)
        pygame.draw.rect(self.screen, COLOR_PANEL, header_rect)
        pygame.draw.line(self.screen, COLOR_CARD_BORDER, (0, 56), (WINDOW_WIDTH, 56), 1)

        title_surf = self.font_title.render("TENTS & TREES AI SOLVER", True, COLOR_TEXT_WHITE)
        self.screen.blit(title_surf, (35, 15))

        subtitle_surf = self.font_small.render("BTL1 - MON TRI TUE NHAN TAO | BLIND SEARCH (DFS) vs HEURISTIC (HILL CLIMBING)", True, COLOR_TEXT_MUTED)
        self.screen.blit(subtitle_surf, (310, 21))

        mode_str = "CHE DO: NGUOI CHOI (MANUAL)" if self.manual_mode else f"CHE DO: AI ({self.current_algo})"
        mode_color = COLOR_SUCCESS if self.manual_mode else COLOR_INFO
        badge_surf = self.font_badge.render(mode_str, True, mode_color)
        badge_rect = badge_surf.get_rect(right=WINDOW_WIDTH - 35, centery=28)
        self.screen.blit(badge_surf, badge_rect)

    def _draw_board(self):
        if not self.puzzle_data:
            return

        rows = self.puzzle_data["rows"]
        cols = self.puzzle_data["cols"]

        card_rect = pygame.Rect(35, 75, 690, 715)
        pygame.draw.rect(self.screen, COLOR_PANEL, card_rect, border_radius=10)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card_rect, 1, border_radius=10)

        available_w = 600
        available_h = 600
        cell_size = min(available_w // (cols + 1), available_h // (rows + 1))
        cell_size = max(18, min(cell_size, 65))

        grid_w = cols * cell_size
        grid_h = rows * cell_size
        start_x = card_rect.x + (card_rect.width - grid_w + cell_size) // 2
        start_y = card_rect.y + (card_rect.height - grid_h + cell_size) // 2 - 15

        active_grid = self.player_grid if self.manual_mode else self.board.grid
        curr_row_counts = [0] * rows
        curr_col_counts = [0] * cols

        for r in range(rows):
            for c in range(cols):
                if active_grid[r][c] == TentsBoard.TENT:
                    curr_row_counts[r] += 1
                    curr_col_counts[c] += 1

        # Cột chỉ số trên
        for c in range(cols):
            cx = start_x + c * cell_size
            cy = start_y - cell_size + 4
            clue = self.puzzle_data["col_constraints"][c]
            curr_c = curr_col_counts[c]

            badge_color = (45, 55, 80)
            if curr_c == clue:
                badge_color = COLOR_SUCCESS
            elif curr_c > clue:
                badge_color = COLOR_DANGER

            badge_rect = pygame.Rect(cx + max(1, cell_size // 10), cy, max(14, cell_size - max(2, cell_size // 5)), max(14, cell_size - max(2, cell_size // 5)))
            pygame.draw.rect(self.screen, badge_color, badge_rect, border_radius=max(2, cell_size // 10))
            clue_surf = self.font_small.render(str(clue), True, COLOR_TEXT_WHITE)
            self.screen.blit(clue_surf, clue_surf.get_rect(center=badge_rect.center))

        # Hàng chỉ số trái
        for r in range(rows):
            cx = start_x - cell_size + 4
            cy = start_y + r * cell_size
            clue = self.puzzle_data["row_constraints"][r]
            curr_r = curr_row_counts[r]

            badge_color = (45, 55, 80)
            if curr_r == clue:
                badge_color = COLOR_SUCCESS
            elif curr_r > clue:
                badge_color = COLOR_DANGER

            badge_rect = pygame.Rect(cx, cy + max(1, cell_size // 10), max(14, cell_size - max(2, cell_size // 5)), max(14, cell_size - max(2, cell_size // 5)))
            pygame.draw.rect(self.screen, badge_color, badge_rect, border_radius=max(2, cell_size // 10))
            clue_surf = self.font_small.render(str(clue), True, COLOR_TEXT_WHITE)
            self.screen.blit(clue_surf, clue_surf.get_rect(center=badge_rect.center))

        # Vẽ các ô cờ
        mouse_pos = pygame.mouse.get_pos()
        last_changed_pos = (-1, -1)
        if not self.manual_mode and 0 <= self.current_step_index < len(self.history_steps):
            step = self.history_steps[self.current_step_index]
            if "pos" in step:
                last_changed_pos = step["pos"]
            elif "new_pos" in step:
                last_changed_pos = step["new_pos"]

        for r in range(rows):
            for c in range(cols):
                rect = pygame.Rect(start_x + c * cell_size, start_y + r * cell_size, cell_size, cell_size)
                bg_col = COLOR_CELL_LIGHT if (r + c) % 2 == 0 else COLOR_CELL_DARK

                if rect.collidepoint(mouse_pos):
                    bg_col = COLOR_CELL_HOVER

                pygame.draw.rect(self.screen, bg_col, rect)
                pygame.draw.rect(self.screen, COLOR_GRID_LINE, rect, 1)

                if (r, c) == last_changed_pos:
                    pygame.draw.rect(self.screen, COLOR_ACTIVE_CELL, rect, max(2, cell_size // 12))

                cell_val = active_grid[r][c]
                center = rect.center

                if cell_val == TentsBoard.TREE:
                    VectorSprites.draw_tree(self.screen, center[0], center[1], cell_size)
                elif cell_val == TentsBoard.TENT:
                    is_active = ((r, c) == last_changed_pos)
                    VectorSprites.draw_tent(self.screen, center[0], center[1], cell_size, active=is_active)
                elif cell_val == TentsBoard.GRASS:
                    VectorSprites.draw_grass(self.screen, center[0], center[1], cell_size)

        self.grid_render_info = {
            "start_x": start_x,
            "start_y": start_y,
            "cell_size": cell_size,
            "rows": rows,
            "cols": cols
        }

    def _draw_controls(self):
        panel_x = 750
        panel_w = 515

        # CARD 1: Bộ chọn đề
        card1_rect = pygame.Rect(panel_x, 75, panel_w, 108)
        pygame.draw.rect(self.screen, COLOR_PANEL, card1_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card1_rect, 1, border_radius=8)

        for btn in self.filter_buttons:
            if (btn.text == "Tat ca" and self.active_category == "ALL") or \
               (btn.text == self.active_category) or \
               (btn.text == "Special" and self.active_category == "SPECIAL"):
                btn.bg_color = COLOR_INFO
            else:
                btn.bg_color = (45, 55, 78)
            btn.draw(self.screen, self.font_small)

        fname = os.path.basename(self.current_filepath) if self.current_filepath else "Chua chon file"
        idx_str = f"Man {self.current_puzzle_index + 1}/{len(self.filtered_puzzle_files)}"
        dim_str = f"{self.puzzle_data['rows']}x{self.puzzle_data['cols']}" if self.puzzle_data else ""
        trees_str = f"{len(self.puzzle_data['trees'])} Cay" if self.puzzle_data else ""
        info_text = f"File: {fname} ({idx_str}) | Luoi: {dim_str} | {trees_str}"
        self.screen.blit(self.font_bold.render(info_text, True, COLOR_TEXT_GOLD), (panel_x + 12, 115))

        self.btn_prev_puzzle.draw(self.screen, self.font_bold)
        self.btn_next_puzzle.draw(self.screen, self.font_bold)
        self.btn_random_puzzle.draw(self.screen, self.font_bold)
        self.btn_browse.draw(self.screen, self.font_bold)
        self.btn_reset_board.draw(self.screen, self.font_bold)

        # CARD 2: Thuật toán & Chế độ
        card2_rect = pygame.Rect(panel_x, 193, panel_w, 118)
        pygame.draw.rect(self.screen, COLOR_PANEL, card2_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card2_rect, 1, border_radius=8)

        card2_title = self.font_bold.render("LUA CHON THUAT TOAN TIM KIEM", True, COLOR_TEXT_MUTED)
        self.screen.blit(card2_title, (panel_x + 15, 203))

        self.btn_run_dfs.draw(self.screen, self.font_bold)
        self.btn_run_hc.draw(self.screen, self.font_bold)
        self.btn_compare.draw(self.screen, self.font_bold)
        self.btn_toggle_manual.draw(self.screen, self.font_bold)

        # CARD 3: Step-by-Step
        card3_rect = pygame.Rect(panel_x, 320, panel_w, 142)
        pygame.draw.rect(self.screen, COLOR_PANEL, card3_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card3_rect, 1, border_radius=8)

        title3 = self.font_bold.render("DIEU KHIEN HOAT CANH (STEP-BY-STEP)", True, COLOR_TEXT_WHITE)
        self.screen.blit(title3, (panel_x + 15, 330))

        total_s = len(self.history_steps)
        curr_s = max(0, self.current_step_index + 1)
        step_counter_text = f"Buoc: {curr_s} / {total_s}"
        self.screen.blit(self.font_medium.render(step_counter_text, True, COLOR_TEXT_GOLD), (panel_x + 380, 330))

        self.btn_step_first.draw(self.screen, self.font_bold)
        self.btn_step_prev.draw(self.screen, self.font_bold)
        self.btn_play_pause.draw(self.screen, self.font_bold)
        self.btn_step_next.draw(self.screen, self.font_bold)
        self.btn_step_last.draw(self.screen, self.font_bold)
        self.btn_speed.draw(self.screen, self.font_bold)
        self.btn_clear_step.draw(self.screen, self.font_bold)

        self.scrub_bar.draw(self.screen, curr_s, total_s)

        log_msg = "San sang. Nhan 'Chay DFS' hoac 'Hill Climbing' de quan sat giai thuat."
        if 0 <= self.current_step_index < len(self.history_steps):
            st = self.history_steps[self.current_step_index]
            if "log" in st:
                log_msg = st["log"]
            elif st.get("action") == "PLACE":
                log_msg = f"[DAT LEU] tai hang {st['pos'][0]}, cot {st['pos'][1]} cho Cay tai {st['tree']}"
            elif st.get("action") == "REMOVE":
                log_msg = f"[QUAY LUI] Rut leu tai hang {st['pos'][0]}, cot {st['pos'][1]} (Vao ngo cut)"

        log_surf = self.font_small.render(f"> {log_msg}", True, (200, 220, 255))
        self.screen.blit(log_surf, (panel_x + 15, 415))

        # CARD 4: Benchmark HUD
        card4_rect = pygame.Rect(panel_x, 472, panel_w, 238)
        pygame.draw.rect(self.screen, COLOR_PANEL, card4_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card4_rect, 1, border_radius=8)

        title4 = self.font_bold.render("SO LIEU THUC NGHIEM DO DAC (BENCHMARK HUD)", True, COLOR_TEXT_WHITE)
        self.screen.blit(title4, (panel_x + 15, 482))

        status_str = "CHUA CHAY GIAI THUAT"
        status_col = COLOR_TEXT_MUTED
        if self.metrics["algo_name"]:
            if self.metrics["solved"]:
                status_str = f"TIM THAY LOI GIAI ({self.metrics['algo_name']})"
                status_col = COLOR_SUCCESS
            elif self.metrics.get("timed_out"):
                status_str = f"HET GIO TIM KIEM (TIMEOUT) - DUNG AN TOAN ({self.metrics['algo_name']})"
                status_col = COLOR_DANGER
            else:
                status_str = f"KHONG TIM THAY LOI GIAI ({self.metrics['algo_name']})"
                status_col = COLOR_DANGER

        self.screen.blit(self.font_medium.render(status_str, True, status_col), (panel_x + 15, 506))

        metric_cards = [
            ("THOI GIAN THUC THI", f"{self.metrics['time_sec']:.5f} s", (41, 128, 185)),
            ("BO NHO RAM DINH", f"{self.metrics['peak_mem_kb']:.2f} KB", (142, 68, 173)),
            ("NODE / TRANG THAI DUYET", f"{self.metrics['nodes_or_states']}", (39, 174, 96)),
            ("QUAY LUI / RESTARTS", f"{self.metrics['backtracks_or_restarts']}", (211, 84, 0))
        ]

        bx, by = panel_x + 15, 532
        bw, bh = 235, 52

        for i, (m_title, m_val, m_color) in enumerate(metric_cards):
            col = i % 2
            row = i // 2
            x = bx + col * (bw + 15)
            y = by + row * (bh + 10)

            m_rect = pygame.Rect(x, y, bw, bh)
            pygame.draw.rect(self.screen, COLOR_CARD, m_rect, border_radius=6)
            pygame.draw.rect(self.screen, COLOR_CARD_BORDER, m_rect, 1, border_radius=6)
            pygame.draw.rect(self.screen, m_color, (x, y, 4, bh), border_top_left_radius=6, border_bottom_left_radius=6)

            self.screen.blit(self.font_small.render(m_title, True, COLOR_TEXT_MUTED), (x + 12, y + 8))
            self.screen.blit(self.font_bold.render(m_val, True, COLOR_TEXT_WHITE), (x + 12, y + 26))

        tip_text = "Meo: O che do Tu choi, Click chuot trai de dat Leu/Co, Chuot phai de dat Co."
        self.screen.blit(self.font_small.render(tip_text, True, (130, 160, 200)), (panel_x + 15, 655))

    def _draw_solving_overlay(self):
        """Vẽ hộp thoại hiển thị tiến trình khi Worker Thread đang tính toán."""
        dialog_w, dialog_h = 420, 140
        dialog_x = (WINDOW_WIDTH - dialog_w) // 2
        dialog_y = (WINDOW_HEIGHT - dialog_h) // 2
        dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)

        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, (28, 36, 56), dialog_rect, border_radius=10)
        pygame.draw.rect(self.screen, COLOR_COMPARE, dialog_rect, 2, border_radius=10)

        elapsed = time.time() - self.solving_start_time
        title = self.font_bold.render(f"DANG CHAY GIAI THUAT {self.solving_algo_name}...", True, COLOR_TEXT_WHITE)
        self.screen.blit(title, title.get_rect(center=(dialog_rect.centerx, dialog_y + 35)))

        dots = "." * (int(elapsed * 3) % 4)
        status = self.font_small.render(f"Dang tim kiem khong gian trang thai{dots} ({elapsed:.1f}s)", True, COLOR_TEXT_GOLD)
        self.screen.blit(status, status.get_rect(center=(dialog_rect.centerx, dialog_y + 65)))

        sub = self.font_small.render("Cac map lon (>15x15) se tu dung an toan neu het thoi gian.", True, COLOR_TEXT_MUTED)
        self.screen.blit(sub, sub.get_rect(center=(dialog_rect.centerx, dialog_y + 95)))

    def _draw_victory_banner(self):
        banner_rect = pygame.Rect(200, 320, 480, 120)
        shadow = pygame.Surface((banner_rect.width + 10, banner_rect.height + 10), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 140))
        self.screen.blit(shadow, (banner_rect.x - 5, banner_rect.y - 5))

        pygame.draw.rect(self.screen, (24, 75, 40), banner_rect, border_radius=12)
        pygame.draw.rect(self.screen, COLOR_SUCCESS, banner_rect, 3, border_radius=12)

        win_title = self.font_large.render("CHUC MUNG CHIEN THANG!", True, (255, 255, 255))
        self.screen.blit(win_title, win_title.get_rect(center=(banner_rect.centerx, banner_rect.y + 40)))

        win_sub = self.font_bold.render("Ban da hoan thanh giai do hop le chinh xac 100%!", True, COLOR_TEXT_GOLD)
        self.screen.blit(win_sub, win_sub.get_rect(center=(banner_rect.centerx, banner_rect.y + 80)))

    def _draw_compare_modal(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        modal_w, modal_h = 860, 560
        modal_x = (WINDOW_WIDTH - modal_w) // 2
        modal_y = (WINDOW_HEIGHT - modal_h) // 2
        modal_rect = pygame.Rect(modal_x, modal_y, modal_w, modal_h)

        pygame.draw.rect(self.screen, COLOR_PANEL, modal_rect, border_radius=12)
        pygame.draw.rect(self.screen, COLOR_COMPARE, modal_rect, 2, border_radius=12)

        title = self.font_large.render("BANG DOI SANH THUAT TOAN (BENCHMARK REPORT)", True, COLOR_TEXT_WHITE)
        self.screen.blit(title, (modal_x + 30, modal_y + 25))

        sub = self.font_medium.render(f"File bai toan: {self.compare_results['filename']} | Luoi: {self.compare_results['size']} | {self.compare_results['trees']} Cay", True, COLOR_TEXT_GOLD)
        self.screen.blit(sub, (modal_x + 30, modal_y + 60))

        dfs = self.compare_results["dfs"]
        hc = self.compare_results["hc"]

        table_x = modal_x + 30
        table_y = modal_y + 95
        row_h = 40

        pygame.draw.rect(self.screen, COLOR_CARD, (table_x, table_y, 800, row_h), border_radius=6)
        self.screen.blit(self.font_bold.render("THONG SO DO DAC", True, COLOR_TEXT_MUTED), (table_x + 20, table_y + 11))
        self.screen.blit(self.font_bold.render("DFS (BLIND SEARCH)", True, COLOR_DFS), (table_x + 320, table_y + 11))
        self.screen.blit(self.font_bold.render("HILL CLIMBING (HEURISTIC)", True, COLOR_HC), (table_x + 560, table_y + 11))

        rows_data = [
            ("Trang thai giai thanh cong", "CO (Thanh cong)" if dfs["solved"] else "KHONG (Timeout)", "CO (Thanh cong)" if hc["solved"] else "KHONG (Timeout)"),
            ("Thoi gian thuc thi (giay)", f"{dfs['execution_time_sec']:.6f} s", f"{hc['execution_time_sec']:.6f} s"),
            ("Bo nho RAM dinh (KB)", f"{dfs['peak_memory_kb']:.2f} KB", f"{hc['peak_memory_kb']:.2f} KB"),
            ("Khong gian da duyet", f"{dfs['nodes_explored']} nodes", f"{hc['states_evaluated']} states"),
            ("So lan Quay lui / Restarts", f"{dfs['backtracks']} lan quay lui", f"{hc['restarts']} lan restart"),
            ("Diem xung dot Heuristic h(S)", "0 (Toi uu)", f"{hc['final_heuristic']} ({'Toi uu' if hc['final_heuristic']==0 else 'Chua toi uu'})"),
        ]

        for i, (metric, val_dfs, val_hc) in enumerate(rows_data):
            ry = table_y + (i + 1) * row_h
            bg_col = (30, 38, 58) if i % 2 == 0 else (24, 32, 50)
            pygame.draw.rect(self.screen, bg_col, (table_x, ry, 800, row_h))
            pygame.draw.line(self.screen, COLOR_CARD_BORDER, (table_x, ry), (table_x + 800, ry), 1)

            self.screen.blit(self.font_medium.render(metric, True, COLOR_TEXT_WHITE), (table_x + 20, ry + 11))
            self.screen.blit(self.font_bold.render(val_dfs, True, COLOR_TEXT_WHITE), (table_x + 320, ry + 11))
            self.screen.blit(self.font_bold.render(val_hc, True, COLOR_TEXT_WHITE), (table_x + 560, ry + 11))

        note_y = table_y + 7 * row_h + 10
        pygame.draw.rect(self.screen, (20, 26, 42), (table_x, note_y, 800, 75), border_radius=6)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, (table_x, note_y, 800, 75), 1, border_radius=6)

        self.screen.blit(self.font_bold.render("NHAN XET SO SANH GIAI THUAT CHO BAO CAO:", True, COLOR_TEXT_GOLD), (table_x + 15, note_y + 8))
        note1 = "- DFS: Duyet theo chieu sau voi Cat tia (Pruning) bao dam tinh day du, thoi gian giai cuc nhanh tren khong gian rang buoc chat."
        note2 = "- Hill Climbing: Dua tren ham Heuristic h(S) dem xung dot ket hop Random Restart giup vuot bay cuc tieu dia phuong."
        self.screen.blit(self.font_small.render(note1, True, COLOR_TEXT_MUTED), (table_x + 15, note_y + 30))
        self.screen.blit(self.font_small.render(note2, True, COLOR_TEXT_MUTED), (table_x + 15, note_y + 48))

        self.btn_modal_export.rect.x = table_x + 470
        self.btn_modal_export.rect.y = modal_y + modal_h - 55
        self.btn_modal_export.draw(self.screen, self.font_bold)

        self.btn_modal_close.rect.x = table_x + 650
        self.btn_modal_close.rect.y = modal_y + modal_h - 55
        self.btn_modal_close.draw(self.screen, self.font_bold)

    # ==================== VÒNG LẶP SỰ KIỆN CHÍNH ====================
    def run(self):
        running = True

        while running:
            current_time = pygame.time.get_ticks()
            mouse_pos = pygame.mouse.get_pos()

            # Hover
            for btn in [
                self.btn_prev_puzzle, self.btn_next_puzzle, self.btn_random_puzzle,
                self.btn_browse, self.btn_reset_board, self.btn_run_dfs,
                self.btn_run_hc, self.btn_compare, self.btn_toggle_manual,
                self.btn_step_first, self.btn_step_prev, self.btn_play_pause,
                self.btn_step_next, self.btn_step_last, self.btn_speed,
                self.btn_clear_step, self.btn_modal_export, self.btn_modal_close
            ] + self.filter_buttons:
                btn.check_hover(mouse_pos)

            # Auto-play
            if not self.is_solving and self.is_playing and self.history_steps:
                delay = self.speeds[self.playback_speed_idx][1]
                if delay == 0:
                    self.jump_to_step(len(self.history_steps) - 1)
                    self.is_playing = False
                    self.btn_play_pause.text = "Phat"
                    self.btn_play_pause.icon_type = "play"
                elif current_time - self.last_step_tick >= delay:
                    self.step_forward()
                    self.last_step_tick = current_time

            for event in pygame.event.type if hasattr(pygame.event, "get_events") else pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if self.show_compare_modal:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.btn_modal_close.rect.collidepoint(event.pos):
                            self.show_compare_modal = False
                        elif self.btn_modal_export.rect.collidepoint(event.pos):
                            self.export_benchmark_file()
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.show_compare_modal = False
                    continue

                if self.is_solving:
                    # Trong khi đang giải, không xử lý click nút khác để tránh xung đột luồng
                    continue

                scrub_step = self.scrub_bar.handle_event(event, len(self.history_steps))
                if scrub_step is not None:
                    self.is_playing = False
                    self.btn_play_pause.text = "Phat"
                    self.btn_play_pause.icon_type = "play"
                    self.jump_to_step(scrub_step)

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if hasattr(self, "grid_render_info"):
                        info = self.grid_render_info
                        gx = event.pos[0] - info["start_x"]
                        gy = event.pos[1] - info["start_y"]
                        cs = info["cell_size"]
                        if 0 <= gx < info["cols"] * cs and 0 <= gy < info["rows"] * cs:
                            col_click = gx // cs
                            row_click = gy // cs
                            self.handle_manual_click(row_click, col_click, event.button)

                    for btn in self.filter_buttons:
                        if btn.is_clicked(event.pos, event.type):
                            cat_map = {
                                "Tat ca": "ALL",
                                "6x6": "6x6",
                                "8x8": "8x8",
                                "10x10": "10x10",
                                "15x15": "15x15",
                                "Special": "SPECIAL"
                            }
                            self.set_category_filter(cat_map.get(btn.text, "ALL"))

                    if self.btn_prev_puzzle.is_clicked(event.pos, event.type):
                        if self.filtered_puzzle_files:
                            new_idx = (self.current_puzzle_index - 1) % len(self.filtered_puzzle_files)
                            self.load_puzzle(self.filtered_puzzle_files[new_idx])

                    elif self.btn_next_puzzle.is_clicked(event.pos, event.type):
                        if self.filtered_puzzle_files:
                            new_idx = (self.current_puzzle_index + 1) % len(self.filtered_puzzle_files)
                            self.load_puzzle(self.filtered_puzzle_files[new_idx])

                    elif self.btn_random_puzzle.is_clicked(event.pos, event.type):
                        if len(self.filtered_puzzle_files) > 1:
                            new_idx = random.choice([i for i in range(len(self.filtered_puzzle_files)) if i != self.current_puzzle_index])
                            self.load_puzzle(self.filtered_puzzle_files[new_idx])

                    elif self.btn_browse.is_clicked(event.pos, event.type):
                        self.browse_custom_file()

                    elif self.btn_reset_board.is_clicked(event.pos, event.type):
                        self.load_puzzle(self.current_filepath)

                    elif self.btn_run_dfs.is_clicked(event.pos, event.type):
                        self.run_dfs()

                    elif self.btn_run_hc.is_clicked(event.pos, event.type):
                        self.run_hill_climbing()

                    elif self.btn_compare.is_clicked(event.pos, event.type):
                        self.run_comparison()

                    elif self.btn_toggle_manual.is_clicked(event.pos, event.type):
                        self.manual_mode = not self.manual_mode
                        if self.manual_mode:
                            self.is_playing = False
                            self.btn_toggle_manual.text = "Tat Che do Tu choi (Ve AI Demo)"
                            self.btn_toggle_manual.bg_color = (198, 40, 40)
                            self.btn_toggle_manual.hover_color = (229, 57, 53)
                        else:
                            self.btn_toggle_manual.text = "Chuyen sang Che do Tu choi (Manual Mode)"
                            self.btn_toggle_manual.bg_color = (46, 125, 50)
                            self.btn_toggle_manual.hover_color = (56, 142, 60)

                    elif self.btn_step_first.is_clicked(event.pos, event.type):
                        self.is_playing = False
                        self.jump_to_step(0)

                    elif self.btn_step_prev.is_clicked(event.pos, event.type):
                        self.is_playing = False
                        self.step_backward()

                    elif self.btn_play_pause.is_clicked(event.pos, event.type):
                        if self.history_steps:
                            self.is_playing = not self.is_playing
                            self.btn_play_pause.text = "Tam dung" if self.is_playing else "Phat"
                            self.btn_play_pause.icon_type = "pause" if self.is_playing else "play"
                            if self.is_playing and self.current_step_index >= len(self.history_steps) - 1:
                                self.jump_to_step(0)

                    elif self.btn_step_next.is_clicked(event.pos, event.type):
                        self.is_playing = False
                        self.step_forward()

                    elif self.btn_step_last.is_clicked(event.pos, event.type):
                        self.is_playing = False
                        self.jump_to_step(len(self.history_steps) - 1)

                    elif self.btn_speed.is_clicked(event.pos, event.type):
                        self.playback_speed_idx = (self.playback_speed_idx + 1) % len(self.speeds)
                        self.btn_speed.text = self.speeds[self.playback_speed_idx][0]

                    elif self.btn_clear_step.is_clicked(event.pos, event.type):
                        self.load_puzzle(self.current_filepath)

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if self.history_steps:
                            self.is_playing = not self.is_playing
                            self.btn_play_pause.text = "Tam dung" if self.is_playing else "Phat"
                            self.btn_play_pause.icon_type = "pause" if self.is_playing else "play"
                    elif event.key == pygame.K_RIGHT:
                        self.step_forward()
                    elif event.key == pygame.K_LEFT:
                        self.step_backward()
                    elif event.key == pygame.K_r:
                        self.load_puzzle(self.current_filepath)

            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    app = TentsGameGUI()
    app.run()
