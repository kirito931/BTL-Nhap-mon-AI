"""
MODULE: GUI.py
CÔNG NGHỆ: 100% Python kết hợp Pygame (Đồ họa 60 FPS) và Tkinter (Bộ chọn file native, xuất báo cáo).
PHONG CÁCH: Bàn Cờ Vây / Trúc & Mực Thủy Mặc Zen (Bamboo Wood & Ink Slate Theme).

TÍNH NĂNG CHÍNH:
1. Đồ họa Vector 100% sắc nét:
   - Mặt bàn cờ gỗ Trúc (Bamboo/Kaya wood) ấm áp với điểm sao (Hoshi points) truyền thống.
   - Quân cờ Âm Dương đen mun bóng (Obsidian Black) và ngọc trắng sứ (Ivory White)
     với bóng đổ mềm mại, viền vát 3D và đốm sáng bóng gương chân thực.
   - Huy hiệu Thái Cực (Taijitu Yin-Yang Emblem) cách điệu tinh tế ở thanh tiêu đề.
2. Đa luồng (Multi-threading): Chạy thuật toán AI trên luồng nền (Worker Thread),
   tuyệt đối KHÔNG BAO GIỜ bị đơ cửa sổ hoặc "(Not Responding)" ngay cả trên map lớn.
3. Giải thuật Tìm kiếm:
   - Blind Search: Depth-First Search (DFS) kết hợp Backtracking, Suy diễn 2x2 & Pruning.
   - Heuristic Search: IDA* (Iterative Deepening A*) với hàm đánh giá độ phân mảnh liên thông.
4. Trình diễn Step-by-Step linh hoạt (Play/Pause, Step Next/Prev, First/Last, Scrub Bar, Speed Control).
5. Chế độ So sánh Đối đầu (Benchmark Side-by-side Modal) và Xuất Báo Cáo TXT cho BTL1.
6. Thiết kế Tỷ lệ Vàng trực quan, hiển thị thông số RAM/Node/Thời gian chuẩn xác 100%.
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

# Thiết lập DPI Awareness & UTF-8 cho Windows để phông chữ sắc nét 100%
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được các module trong thư mục src/
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "inputs"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from board import YinYangBoard, load_input_file
from dfs import DFSSolver
from ida_star import IDAStarSolver


# ==============================================================================
# HẰNG SỐ MÀU SẮC VÀ THIẾT KẾ (ZEN GO-BOARD THEME)
# ==============================================================================
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 860
FPS = 60

# Palette phong cách Thủy Mặc & Gỗ Trúc (Ink Zen & Bamboo)
COLOR_BG = (18, 21, 28)                  # Deep Obsidian / Dark Slate
COLOR_PANEL = (26, 30, 40)               # Slate Ink Panel
COLOR_CARD = (34, 40, 54)                # Slate Card Background
COLOR_CARD_BORDER = (60, 70, 92)         # Slate Card Border
COLOR_CARD_HOVER = (44, 52, 70)

# Chữ và điểm nhấn ánh kim (Imperial Gold)
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_MUTED = (195, 205, 225)
COLOR_TEXT_LABEL = (220, 230, 245)
COLOR_GOLD = (218, 168, 85)              # Vàng ánh kim Zen
COLOR_GOLD_HOVER = (245, 200, 115)
COLOR_GOLD_MUTED = (165, 128, 65)

# Bàn cờ gỗ Trúc (Bamboo / Kaya Wood Board)
COLOR_BOARD_WOOD = (224, 185, 132)       # Gỗ ấm Bamboo
COLOR_BOARD_WOOD_DARK = (198, 155, 102)  # Viền vát gỗ
COLOR_GRID_LINE = (92, 65, 38)           # Đường kẻ cờ vây nâu sẫm
COLOR_STAR_POINT = (75, 50, 25)          # Điểm sao Hoshi
COLOR_CELL_HOVER = (255, 235, 175)

# Quân cờ Âm Dương (Go Stones)
COLOR_STONE_BLACK = (22, 24, 28)         # Đen mun bóng
COLOR_STONE_WHITE = (248, 248, 252)      # Trắng ngọc sứ
COLOR_STONE_WHITE_BORDER = (195, 200, 212)
COLOR_CLUE_MARK = (218, 168, 85)         # Vòng khuyên vàng đánh dấu ô đề bài gốc

# Màu nút chức năng & thuật toán
COLOR_DFS = (225, 105, 45)               # Đất nung / Terracotta
COLOR_DFS_HOVER = (245, 125, 65)
COLOR_IDA = (40, 150, 195)               # Lam ngọc Sapphire
COLOR_IDA_HOVER = (60, 175, 225)
COLOR_COMPARE = (155, 89, 182)           # Tím Amethyst
COLOR_COMPARE_HOVER = (175, 109, 202)
COLOR_MANUAL = (46, 175, 100)            # Xanh Lục Trúc
COLOR_MANUAL_HOVER = (66, 195, 120)
COLOR_DANGER = (235, 87, 87)             # Đỏ cảnh báo / Xung đột
COLOR_INFO = (52, 152, 219)


# ==============================================================================
# BỘ GIẢI STEP-BY-STEP CÓ GIỚI HẠN AN TOÀN
# ==============================================================================
class SteppedSolver:
    """Wrapper hỗ trợ giải và thu thập lịch sử bước cho animation Step-by-Step."""
    @staticmethod
    def run_dfs(board: YinYangBoard, max_nodes=100000, timeout_sec=30.0, cancel_event=None, step_callback=None):
        solver = DFSSolver(board, max_nodes=max_nodes, timeout_sec=timeout_sec, cancel_event=cancel_event, step_callback=step_callback)
        result = solver.solve()
        return result

    @staticmethod
    def run_ida(board: YinYangBoard, max_threshold=50, timeout_sec=30.0, cancel_event=None, step_callback=None):
        solver = IDAStarSolver(board, max_nodes=100000, timeout_sec=timeout_sec, cancel_event=cancel_event, step_callback=step_callback)
        result = solver.solve(max_threshold=max_threshold)
        return result


# ==============================================================================
# HỆ THỐNG VẼ ĐỒ HỌA VECTOR (VECTOR SPRITES)
# ==============================================================================
class VectorSprites:
    """Vẽ huy hiệu Thái Cực, quân cờ đen trắng và hiệu ứng bàn cờ hoàn toàn bằng vector."""

    @staticmethod
    def draw_taijitu(surface: pygame.Surface, cx: int, cy: int, radius: int):
        """Vẽ biểu tượng Thái Cực (Yin-Yang Taijitu)."""
        # 1. Nền trắng
        pygame.draw.circle(surface, COLOR_STONE_WHITE, (cx, cy), radius)
        pygame.draw.circle(surface, COLOR_STONE_BLACK, (cx, cy), radius, 1)

        # 2. Bán nguyệt đen bên phải (hoặc bên trái)
        rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
        pygame.draw.arc(surface, COLOR_STONE_BLACK, rect, -math.pi / 2, math.pi / 2, radius)
        # Điền nửa hình tròn đen bằng polygon mịn
        pts = [(cx, cy - radius)]
        for angle_deg in range(-90, 91, 5):
            rad = math.radians(angle_deg)
            pts.append((cx + int(radius * math.cos(rad)), cy + int(radius * math.sin(rad))))
        pts.append((cx, cy + radius))
        pygame.draw.polygon(surface, COLOR_STONE_BLACK, pts)

        # 3. Hai vòng cung s-curve (một đen, một trắng)
        r_half = radius // 2
        # Vòng tròn đen nhỏ phía trên
        pygame.draw.circle(surface, COLOR_STONE_BLACK, (cx, cy - r_half), r_half)
        # Vòng tròn trắng nhỏ phía dưới
        pygame.draw.circle(surface, COLOR_STONE_WHITE, (cx, cy + r_half), r_half)

        # 4. Mắt cờ đối lập (Dots)
        dot_r = max(2, radius // 6)
        pygame.draw.circle(surface, COLOR_STONE_WHITE, (cx, cy - r_half), dot_r)
        pygame.draw.circle(surface, COLOR_STONE_BLACK, (cx, cy + r_half), dot_r)

    @staticmethod
    def draw_stone(surface: pygame.Surface, cx: int, cy: int, radius: int, color_type: str, is_clue: bool = False, alpha: int = 255):
        """
        Vẽ quân cờ Vây đen / trắng theo phong cách cờ đá bóng gương cao cấp.
        - color_type: 'B' hoặc 'W'
        - is_clue: True nếu là quân cờ đề bài cho sẵn (vẽ khuyên vàng)
        """
        if radius <= 3:
            return

        stone_surf = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        scx = radius + 5
        scy = radius + 5

        # 1. Bóng đổ mềm mại dưới quân cờ (Drop Shadow)
        shadow_rect = pygame.Rect(scx - radius + 2, scy - radius + 4, radius * 2, radius * 2)
        shadow_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(shadow_surf, (0, 0, 0, int(75 * (alpha / 255.0))), (radius, radius), radius)
        stone_surf.blit(shadow_surf, (scx - radius + 2, scy - radius + 3))

        # 2. Thân quân cờ
        if color_type == 'B':
            # Quân Đen mun bóng
            base_color = (24, 26, 30, alpha)
            pygame.draw.circle(stone_surf, base_color, (scx, scy), radius)
            pygame.draw.circle(stone_surf, (10, 12, 15, alpha), (scx, scy), radius, 1)

            # Đốm sáng phản chiếu (Specular Highlight) trên mặt cờ
            hl_r = max(2, int(radius * 0.45))
            hl_x = scx - int(radius * 0.28)
            hl_y = scy - int(radius * 0.28)
            hl_surf = pygame.Surface((hl_r * 2, hl_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(hl_surf, (255, 255, 255, int(55 * (alpha / 255.0))), (hl_r, hl_r), hl_r)
            stone_surf.blit(hl_surf, (hl_x - hl_r, hl_y - hl_r))

            # Tâm sáng nhỏ li ti
            dot_x = scx - int(radius * 0.35)
            dot_y = scy - int(radius * 0.35)
            dot_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (255, 255, 255, int(90 * (alpha / 255.0))), (3, 3), max(1, radius // 9))
            stone_surf.blit(dot_surf, (dot_x - 3, dot_y - 3))

        else:
            # Quân Trắng sứ ngọc
            base_color = (248, 248, 252, alpha)
            pygame.draw.circle(stone_surf, base_color, (scx, scy), radius)
            pygame.draw.circle(stone_surf, (190, 195, 205, alpha), (scx, scy), radius, 1)

            # Viền bóng đổ nhẹ nửa dưới tạo cảm giác nổi khối 3D
            rim_r = radius - 1
            rim_surf = pygame.Surface((rim_r * 2, rim_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(rim_surf, (215, 220, 230, int(120 * (alpha / 255.0))), (rim_r, rim_r), rim_r, max(1, radius // 7))
            stone_surf.blit(rim_surf, (scx - rim_r, scy - rim_r + 1))

            # Đốm sáng phản chiếu
            hl_r = max(2, int(radius * 0.4))
            hl_x = scx - int(radius * 0.25)
            hl_y = scy - int(radius * 0.25)
            hl_surf = pygame.Surface((hl_r * 2, hl_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(hl_surf, (255, 255, 255, int(150 * (alpha / 255.0))), (hl_r, hl_r), hl_r)
            stone_surf.blit(hl_surf, (hl_x - hl_r, hl_y - hl_r))

        # 3. Đánh dấu quân cờ xuất phát của đề bài (Clue Mark)
        if is_clue:
            mark_r = max(3, radius // 3)
            # Khuyên tròn vàng ánh kim
            pygame.draw.circle(stone_surf, COLOR_GOLD, (scx, scy), mark_r, max(1, radius // 10))
            if mark_r >= 5:
                pygame.draw.circle(stone_surf, (255, 235, 170), (scx, scy), max(1, mark_r // 3))

        surface.blit(stone_surf, (cx - scx, cy - scy))

    @staticmethod
    def draw_icon_first(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pygame.draw.rect(surface, color, (cx - 7, cy - 6, 3, 12), border_radius=1)
        pts = [(cx + 6, cy - 6), (cx + 6, cy + 6), (cx - 3, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_prev(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx + 5, cy - 6), (cx + 5, cy + 6), (cx - 4, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_next(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 5, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_last(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx - 6, cy - 6), (cx - 6, cy + 6), (cx + 3, cy)]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.rect(surface, color, (cx + 5, cy - 6, 3, 12), border_radius=1)

    @staticmethod
    def draw_icon_play(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pts = [(cx - 4, cy - 7), (cx - 4, cy + 7), (cx + 6, cy)]
        pygame.draw.polygon(surface, color, pts)

    @staticmethod
    def draw_icon_pause(surface: pygame.Surface, rect: pygame.Rect, color: tuple):
        cx, cy = rect.center
        pygame.draw.rect(surface, color, (cx - 5, cy - 6, 3, 12), border_radius=1)
        pygame.draw.rect(surface, color, (cx + 2, cy - 6, 3, 12), border_radius=1)


# ==============================================================================
# THÀNH PHẦN NÚT BẤM VÀ ĐIỀU KHIỂN (BUTTON & SCRUBBAR)
# ==============================================================================
class Button:
    def __init__(self, rect, text="", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, font=None, icon_type=None, border_radius=6, border_color=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.font = font
        self.icon_type = icon_type
        self.border_radius = border_radius
        self.border_color = border_color
        self.is_hovered = False
        self.is_active = False

    def draw(self, surface):
        color = self.hover_color if self.is_hovered else self.bg_color
        if self.is_active:
            color = self.hover_color

        pygame.draw.rect(surface, color, self.rect, border_radius=self.border_radius)
        if self.border_color:
            pygame.draw.rect(surface, self.border_color, self.rect, 1, border_radius=self.border_radius)

        icon_col = self.text_color
        if self.is_hovered and self.bg_color != COLOR_GOLD:
            icon_col = COLOR_GOLD_HOVER

        if self.icon_type == "first":
            VectorSprites.draw_icon_first(surface, self.rect, icon_col)
        elif self.icon_type == "prev":
            VectorSprites.draw_icon_prev(surface, self.rect, icon_col)
        elif self.icon_type == "next":
            VectorSprites.draw_icon_next(surface, self.rect, icon_col)
        elif self.icon_type == "last":
            VectorSprites.draw_icon_last(surface, self.rect, icon_col)
        elif self.icon_type == "play":
            VectorSprites.draw_icon_play(surface, self.rect, icon_col)
        elif self.icon_type == "pause":
            VectorSprites.draw_icon_pause(surface, self.rect, icon_col)

        if self.font and self.text:
            txt_surf = self.font.render(self.text, True, self.text_color)
            txt_rect = txt_surf.get_rect(center=self.rect.center)
            surface.blit(txt_surf, txt_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False


class ScrubBar:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.is_dragging = False

    def draw(self, surface, current_step, total_steps):
        # Thanh ray nền
        pygame.draw.rect(surface, (45, 52, 68), self.rect, border_radius=4)
        pygame.draw.rect(surface, (70, 80, 105), self.rect, 1, border_radius=4)

        if total_steps > 0:
            progress = max(0.0, min(1.0, current_step / max(1, total_steps - 1)))
            fill_w = int(self.rect.width * progress)

            # Thanh tiến trình vàng ánh kim
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
            pygame.draw.rect(surface, COLOR_GOLD, fill_rect, border_radius=4)

            # Con trượt tròn
            knob_x = self.rect.x + fill_w
            knob_y = self.rect.centery
            pygame.draw.circle(surface, (255, 255, 255), (knob_x, knob_y), 7)
            pygame.draw.circle(surface, COLOR_GOLD, (knob_x, knob_y), 5)
            pygame.draw.circle(surface, (60, 45, 20), (knob_x, knob_y), 7, 1)

    def get_step_at(self, mouse_x, total_steps):
        if total_steps <= 1:
            return 0
        clamped_x = max(self.rect.x, min(self.rect.right, mouse_x))
        ratio = (clamped_x - self.rect.x) / self.rect.width
        step = int(round(ratio * (total_steps - 1)))
        return max(0, min(total_steps - 1, step))


# ==============================================================================
# GIAO DIỆN CHÍNH (YIN-YANG GAME GUI)
# ==============================================================================
class YinYangGameGUI:
    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Yin-Yang Logic Puzzle - Blind Search (DFS) & Heuristic (IDA*)")
        
        # Thiết lập biểu tượng cửa sổ Thái Cực sắc nét
        icon_surf = pygame.Surface((32, 32), pygame.SRCALPHA)
        VectorSprites.draw_taijitu(icon_surf, 16, 16, 14)
        pygame.display.set_icon(icon_surf)

        self.clock = pygame.time.Clock()

        # Khởi tạo Phông chữ
        self.font_title = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], 20, bold=True)
        self.font_bold = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], 14, bold=True)
        self.font_medium = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], 13)
        self.font_small = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], 12)
        self.font_badge = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], 13, bold=True)
        self.font_large = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], 22, bold=True)

        # Quét danh sách các câu đố
        self.all_puzzle_files = self._scan_puzzle_files()
        self.active_category = "ALL"
        self.filtered_puzzle_files = list(self.all_puzzle_files)
        self.current_puzzle_index = 0
        self.current_filepath = ""
        self.board = None
        self.initial_board_data = None

        # Trạng thái diễn hoạt Step-by-Step AI
        self.history_steps = []
        self.current_step_index = -1
        self.is_playing = False
        self.playback_speed_idx = 1
        self.speeds = [
            ("0.5x", 400, "0.5x (Chậm)"),
            ("1.0x", 150, "1.0x (Chuẩn)"),
            ("2.0x", 60,  "2.0x (Nhanh)"),
            ("5.0x", 20,  "5.0x (Rất nhanh)"),
            ("10.0x", 5,  "10.0x (Cực nhanh)"),
            ("Max", 0,    "Max (Tức thì)")
        ]
        self.last_step_tick = 0

        # Luồng chạy nền (Worker Thread)
        self.is_solving = False
        self.solver_cancel_event = None
        self.solving_algo_name = ""
        self.solving_start_time = 0.0
        self.solver_thread = None

        # Thông số đo đạc Benchmark
        self.metrics = {
            "time_sec": 0.0,
            "peak_mem_kb": 0.0,
            "nodes_explored": 0,
            "backtracks": 0,
            "iterations": 0,
            "solved": False,
            "timed_out": False,
            "user_stopped": False,
            "algo_name": ""
        }

        # Cửa sổ Modal So sánh Side-by-side
        self.show_compare_modal = False
        self.compare_results = None
        self.puzzle_results_cache = {}

        # Trạng thái Hộp chọn tốc độ (Speed Option Box)
        self.show_speed_menu = False

        # Khảo sát trực tiếp (Live Search Worker Sync)
        self.live_lock = threading.Lock()
        self.live_info = {
            "algo": "",
            "grid": None,
            "last_pos": (-1, -1),
            "nodes": 0,
            "backtracks": 0,
            "iterations": 0,
            "h": 0,
            "action": "IDLE",
            "active": False
        }
        self.log_msg = "Sẵn sàng. Nhấn 'GIẢI BLIND SEARCH (DFS)' hoặc 'HEURISTIC (IDA*)' để quan sát."

        # Khởi tạo các nút bấm giao diện
        self._init_buttons()

        # Nạp câu đố đầu tiên
        if self.filtered_puzzle_files:
            self.load_puzzle(self.filtered_puzzle_files[0])

    def _scan_puzzle_files(self) -> list:
        if not os.path.exists(INPUTS_DIR):
            os.makedirs(INPUTS_DIR, exist_ok=True)
            return []

        def sort_key(filename):
            base = os.path.basename(filename)
            size_order = 99
            if "6x6" in base:
                size_order = 1
            elif "10x10" in base:
                size_order = 2
            elif "15x15" in base:
                size_order = 3
            elif "special" in base:
                size_order = 4

            diff_order = 99
            if "easy" in base:
                diff_order = 1
            elif "normal" in base:
                diff_order = 2
            elif "hard" in base:
                diff_order = 3

            return (size_order, diff_order, base)

        all_files = [
            os.path.join(INPUTS_DIR, f)
            for f in sorted(os.listdir(INPUTS_DIR), key=lambda x: sort_key(x))
            if f.endswith(".txt")
        ]
        return all_files

    def set_category_filter(self, category_key: str):
        if self.is_solving:
            return
        self.active_category = category_key
        if category_key == "ALL":
            self.filtered_puzzle_files = list(self.all_puzzle_files)
        else:
            self.filtered_puzzle_files = [f for f in self.all_puzzle_files if category_key.lower() in os.path.basename(f).lower()]

        self.current_puzzle_index = 0
        if self.filtered_puzzle_files:
            self.load_puzzle(self.filtered_puzzle_files[0])
        self._init_buttons()

    def load_puzzle(self, filepath: str):
        if self.is_solving:
            return
        try:
            data = load_input_file(filepath)
            self.current_filepath = filepath
            self.initial_board_data = data
            self.board = YinYangBoard(data["rows"], data["cols"], data["grid"], data["initial_clues"])
            self.history_steps = []
            self.current_step_index = -1
            self.is_playing = False
            self.metrics["solved"] = False
            self.metrics["algo_name"] = ""
        except Exception as e:
            print(f"[!] Lỗi khi nạp file {filepath}: {e}")

    def reset_board(self):
        if self.is_solving:
            return
        if self.initial_board_data:
            d = self.initial_board_data
            self.board = YinYangBoard(d["rows"], d["cols"], d["grid"], d["initial_clues"])
            self.history_steps = []
            self.current_step_index = -1
            self.is_playing = False
            self.metrics["solved"] = False

    def _init_buttons(self):
        self.buttons = {}

        # 1. Các tab lọc danh mục bài toán (Category Tabs)
        cats = [("TẤT CẢ", "ALL"), ("6x6", "6x6"), ("10x10", "10x10"), ("15x15", "15x15"), ("ĐẶC BIỆT", "special")]
        tab_x = 360
        tab_y = 15
        tab_w = 90
        tab_h = 32
        for label, cat_key in cats:
            is_act = (self.active_category == cat_key)
            bg = COLOR_GOLD if is_act else COLOR_CARD
            fg = (20, 20, 20) if is_act else COLOR_TEXT_LABEL
            btn = Button((tab_x, tab_y, tab_w, tab_h), label, bg, COLOR_CARD_HOVER, text_color=fg, font=self.font_bold, border_radius=6, border_color=COLOR_CARD_BORDER)
            btn.cat_key = cat_key
            self.buttons[f"cat_{cat_key}"] = btn
            tab_x += tab_w + 8

        # 2. Nút chuyển câu đố & file (Dùng vector icon và text chuẩn không lỗi font)
        nav_x = 880
        nav_y = 15
        self.buttons["prev_puzzle"] = Button((nav_x, nav_y, 40, 32), text="", icon_type="prev", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, border_radius=6, border_color=COLOR_CARD_BORDER)
        self.buttons["next_puzzle"] = Button((nav_x + 46, nav_y, 40, 32), text="", icon_type="next", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, border_radius=6, border_color=COLOR_CARD_BORDER)
        self.buttons["open_file"] = Button((nav_x + 94, nav_y, 110, 32), text="Mở File...", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, font=self.font_bold, border_radius=6, border_color=COLOR_CARD_BORDER)
        self.buttons["reset_board"] = Button((nav_x + 212, nav_y, 90, 32), text="Reset", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, font=self.font_bold, border_radius=6, border_color=COLOR_CARD_BORDER)

        # 3. Bảng điều khiển thuật toán (Left Panel Action Buttons: Cân đối hoàn hảo 3 nút)
        px = 32
        py = 180
        pw = 286
        btn_h = 46

        self.buttons["solve_dfs"] = Button((px, py, pw, btn_h), text="GIẢI BLIND SEARCH (DFS)", bg_color=COLOR_DFS, hover_color=COLOR_DFS_HOVER, font=self.font_bold, border_radius=8)
        self.buttons["solve_ida"] = Button((px, py + 56, pw, btn_h), text="GIẢI HEURISTIC (IDA*)", bg_color=COLOR_IDA, hover_color=COLOR_IDA_HOVER, font=self.font_bold, border_radius=8)
        self.buttons["compare"] = Button((px, py + 112, pw, btn_h), text="SO SÁNH ĐỐI ĐẦU (BENCHMARK)", bg_color=COLOR_COMPARE, hover_color=COLOR_COMPARE_HOVER, font=self.font_bold, border_radius=8)

        # 4. Nút điều khiển diễn hoạt Step-by-Step (Playback Controls: 100% Vector Sprites)
        ctrl_y = 795
        ctrl_x = 360
        btn_sz = 38
        self.buttons["step_first"] = Button((ctrl_x, ctrl_y, btn_sz, btn_sz), text="", icon_type="first", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, border_radius=6, border_color=COLOR_CARD_BORDER)
        self.buttons["step_prev"] = Button((ctrl_x + 44, ctrl_y, btn_sz, btn_sz), text="", icon_type="prev", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, border_radius=6, border_color=COLOR_CARD_BORDER)
        self.buttons["step_play"] = Button((ctrl_x + 88, ctrl_y, btn_sz + 10, btn_sz), text="", icon_type="play", bg_color=COLOR_GOLD, hover_color=COLOR_GOLD_HOVER, text_color=(20, 20, 20), border_radius=6)
        self.buttons["step_next"] = Button((ctrl_x + 142, ctrl_y, btn_sz, btn_sz), text="", icon_type="next", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, border_radius=6, border_color=COLOR_CARD_BORDER)
        self.buttons["step_last"] = Button((ctrl_x + 186, ctrl_y, btn_sz, btn_sz), text="", icon_type="last", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT_WHITE, border_radius=6, border_color=COLOR_CARD_BORDER)

        # Nút chuyển tốc độ (Box Option)
        self.buttons["speed_toggle"] = Button((ctrl_x + 234, ctrl_y, 106, btn_sz), text=f"{self.speeds[self.playback_speed_idx][0]} ▼", bg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, font=self.font_bold, border_radius=6, border_color=COLOR_CARD_BORDER)

        # Nút Dừng thuật toán [ESC] dành cho Live HUD
        self.btn_stop_solving = Button((0, 0, 95, 30), text="Dừng [ESC]", bg_color=COLOR_DANGER, hover_color=(240, 100, 100), font=self.font_bold, border_radius=6)

        # Thanh trượt diễn hoạt (Scrub Bar)
        scrub_x = ctrl_x + 352
        scrub_w = WINDOW_WIDTH - scrub_x - 30
        self.scrub_bar = ScrubBar((scrub_x, ctrl_y + 10, scrub_w, 18))

    # ==========================================================================
    # CƠ CHẾ ĐIỀU KHIỂN TỐC ĐỘ VÀ MENU LỰA CHỌN (SPEED OPTION BOX)
    # ==========================================================================
    def _get_speed_menu_rects(self):
        """Tính toán tọa độ Dropup (hộp mở hướng lên trên) của menu tốc độ."""
        bx, by, bw, bh = self.buttons["speed_toggle"].rect
        menu_w = 168
        item_h = 28
        menu_h = len(self.speeds) * item_h + 8
        menu_x = bx + (bw - menu_w) // 2
        menu_y = by - menu_h - 6  # Dropup: mở ngược lên trên để không tràn cửa sổ
        menu_rect = pygame.Rect(menu_x, menu_y, menu_w, menu_h)
        item_rects = [
            pygame.Rect(menu_x + 4, menu_y + 4 + i * item_h, menu_w - 8, item_h - 2)
            for i in range(len(self.speeds))
        ]
        return menu_rect, item_rects

    def _draw_speed_menu(self):
        """Vẽ Floating Option Box cho phép chọn tốc độ trực quan."""
        menu_rect, item_rects = self._get_speed_menu_rects()
        mouse_pos = pygame.mouse.get_pos()

        # Bóng đổ mờ của menu (Drop Shadow)
        shadow_rect = menu_rect.move(2, 3)
        pygame.draw.rect(self.screen, (10, 12, 18), shadow_rect, border_radius=8)

        # Nền hộp menu và viền vàng ánh kim
        pygame.draw.rect(self.screen, (24, 28, 40), menu_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_GOLD, menu_rect, 1, border_radius=8)

        for i, (label, delay, desc) in enumerate(self.speeds):
            item_rect = item_rects[i]
            is_hovered = item_rect.collidepoint(mouse_pos)
            is_selected = (i == self.playback_speed_idx)

            if is_hovered:
                pygame.draw.rect(self.screen, (45, 54, 76), item_rect, border_radius=5)
            elif is_selected:
                pygame.draw.rect(self.screen, (36, 44, 62), item_rect, border_radius=5)
                pygame.draw.rect(self.screen, (65, 80, 110), item_rect, 1, border_radius=5)

            if is_selected:
                text_col = COLOR_GOLD
            elif is_hovered:
                text_col = COLOR_TEXT_WHITE
            else:
                text_col = COLOR_TEXT_LABEL

            txt_surf = self.font_small.render(desc, True, text_col)
            self.screen.blit(txt_surf, (item_rect.x + 10, item_rect.centery - txt_surf.get_height() // 2))

            if is_selected:
                pygame.draw.circle(self.screen, COLOR_GOLD, (item_rect.right - 12, item_rect.centery), 4)

    # ==========================================================================
    # CƠ CHẾ ĐA LUỒNG & KHẢO SÁT MÒ ĐƯỜNG TRỰC TIẾP (LIVE SEARCH VISUALIZATION)
    # ==========================================================================
    def _get_live_step_delay(self) -> float:
        """Tính toán độ trễ (delay giây) cho mỗi bước khảo sát trực tiếp."""
        raw_delay = self.speeds[self.playback_speed_idx][1]
        if raw_delay == 0:
            return 0.0
        elif raw_delay <= 8:
            return 0.0005
        elif raw_delay <= 25:
            return 0.003
        elif raw_delay <= 80:
            return 0.012
        elif raw_delay <= 180:
            return 0.030
        else:
            return 0.080

    def _on_solver_step(self, board: YinYangBoard, pos: tuple, action: str, nodes: int, backtracks: int, iterations: int = 0, h: int = 0):
        """Callback nhận sự kiện từng bước từ solver để cập nhật bàn cờ và thông số theo thời gian thực."""
        if self.solver_cancel_event is not None and self.solver_cancel_event.is_set():
            return

        delay = self._get_live_step_delay()
        # Nếu đang chạy ở Max Speed (delay == 0), điều tiết tần suất lock/copy để solver đạt hiệu năng tối đa
        if delay == 0.0 and nodes % 50 != 0:
            return

        with self.live_lock:
            self.live_info["grid"] = [row[:] for row in board.grid]
            self.live_info["last_pos"] = pos
            self.live_info["nodes"] = nodes
            self.live_info["backtracks"] = backtracks
            self.live_info["iterations"] = iterations
            self.live_info["h"] = h
            self.live_info["action"] = action

        if delay > 0:
            time.sleep(delay)

    def request_stop_solving(self):
        """Yêu cầu dừng thuật toán đang chạy an toàn."""
        if self.is_solving and self.solver_cancel_event:
            self.solver_cancel_event.set()
            self.metrics["user_stopped"] = True
            self.log_msg = "Người dùng đã dừng tìm kiếm."

    def _draw_live_search_hud(self, bx: int, by: int, bw: int):
        """Vẽ thanh HUD thông số mò đường và đồng hồ bấm giờ trực tiếp phía trên bàn cờ."""
        area_x = 360
        area_w = WINDOW_WIDTH - area_x - 30
        hud_w = 780
        hud_h = 38
        hud_x = area_x + (area_w - hud_w) // 2
        hud_y = max(62, by - hud_h - 10)
        hud_rect = pygame.Rect(hud_x, hud_y, hud_w, hud_h)

        # Nền đen xanh mờ thanh lịch với viền phát sáng
        pygame.draw.rect(self.screen, (18, 22, 32), hud_rect, border_radius=8)
        border_col = COLOR_DFS if "DFS" in self.solving_algo_name else COLOR_IDA
        pygame.draw.rect(self.screen, border_col, hud_rect, 1, border_radius=8)

        # Chấm tròn nhấp nháy báo hiệu trực tiếp (Live Pulse Indicator)
        elapsed = time.perf_counter() - self.solving_start_time
        pulse = (math.sin(elapsed * 7) + 1) / 2.0
        dot_alpha = int(140 + 115 * pulse)
        dot_surf = pygame.Surface((14, 14), pygame.SRCALPHA)
        dot_color = (245, 105, 45, dot_alpha) if "DFS" in self.solving_algo_name else (40, 180, 240, dot_alpha)
        pygame.draw.circle(dot_surf, dot_color, (7, 7), 5)
        self.screen.blit(dot_surf, (hud_x + 12, hud_y + (hud_h - 14) // 2))

        # Tiêu đề thuật toán đang mò đường
        algo_short = "DFS" if "DFS" in self.solving_algo_name else "IDA*"
        algo_title = f"MÒ ĐƯỜNG: {algo_short}"
        title_surf = self.font_bold.render(algo_title, True, COLOR_TEXT_WHITE)
        self.screen.blit(title_surf, (hud_x + 32, hud_y + 10))

        # Thông số tìm kiếm trực tiếp ở giữa thanh
        with self.live_lock:
            nodes = self.live_info.get("nodes", 0)
            backtracks = self.live_info.get("backtracks", 0)
            iterations = self.live_info.get("iterations", 0)
            h = self.live_info.get("h", 0)

        if "DFS" in self.solving_algo_name:
            stat_text = f"Nodes: {nodes:,}  |  Quay lui: {backtracks:,}"
        else:
            stat_text = f"Ngưỡng h: {h}  |  Vòng #{iterations}  |  Nodes: {nodes:,}"

        stat_surf = self.font_medium.render(stat_text, True, COLOR_GOLD)
        self.screen.blit(stat_surf, (hud_x + 230, hud_y + 10))

        # Đồng hồ đếm thời gian thực (Live Timer)
        mins = int(elapsed) // 60
        secs = elapsed % 60
        timer_text = f"{mins:02d}:{secs:04.1f}s"
        timer_surf = self.font_bold.render(timer_text, True, (0, 230, 255))
        self.screen.blit(timer_surf, (hud_x + hud_w - 200, hud_y + 10))

        # Nút Dừng thuật toán [ESC]
        self.btn_stop_solving.rect = pygame.Rect(hud_x + hud_w - 105, hud_y + 4, 98, 30)
        self.btn_stop_solving.draw(self.screen)

    # ==========================================================================
    # QUẢN LÝ LUỒNG GIẢI THUẬT TOÁN (BACKGROUND SOLVER THREAD)
    # ==========================================================================
    def start_solving(self, algo_name: str):
        if self.is_solving:
            return

        self.reset_board()
        self.is_solving = True
        self.solving_algo_name = algo_name
        self.solver_cancel_event = threading.Event()
        self.solving_start_time = time.perf_counter()
        self.metrics["algo_name"] = algo_name
        self.metrics["solved"] = False
        self.metrics["timed_out"] = False
        self.metrics["user_stopped"] = False

        with self.live_lock:
            self.live_info = {
                "algo": algo_name,
                "grid": [row[:] for row in self.board.grid],
                "last_pos": (-1, -1),
                "nodes": 0,
                "backtracks": 0,
                "iterations": 0,
                "h": 0,
                "action": "START",
                "active": True
            }
        self.log_msg = f"Đang chạy thuật toán {algo_name}... Nhấn [ESC] hoặc nút 'Dừng' để hủy."

        def worker():
            solve_board = self.board.copy()
            try:
                if algo_name == "DFS":
                    res = SteppedSolver.run_dfs(
                        solve_board,
                        timeout_sec=30.0,
                        cancel_event=self.solver_cancel_event,
                        step_callback=self._on_solver_step
                    )
                else:
                    res = SteppedSolver.run_ida(
                        solve_board,
                        timeout_sec=30.0,
                        cancel_event=self.solver_cancel_event,
                        step_callback=self._on_solver_step
                    )

                # Cập nhật kết quả vào giao diện chính an toàn
                self.metrics["time_sec"] = res["execution_time_sec"]
                self.metrics["peak_mem_kb"] = res["peak_memory_kb"]
                self.metrics["nodes_explored"] = res["nodes_explored"]
                self.metrics["backtracks"] = res["backtracks"]
                self.metrics["iterations"] = res.get("iterations", 0)
                self.metrics["solved"] = res["solved"]
                self.metrics["timed_out"] = res.get("timed_out", False)
                self.metrics["user_stopped"] = res.get("user_stopped", False)

                # Lưu lại chuỗi bước để animation Step-by-Step
                self.history_steps = list(solve_board.history_steps)
                if res["solved"]:
                    self.board = solve_board
                    self.current_step_index = len(self.history_steps) - 1
                    self.log_msg = f"Đã tìm thấy lời giải thành công ({res['execution_time_sec']:.4f}s, {res['nodes_explored']:,} nodes)!"
                elif res.get("user_stopped", False):
                    self.log_msg = "Tìm kiếm đã dừng bởi người dùng."
                elif res.get("timed_out", False):
                    self.log_msg = "Hết thời gian tìm kiếm (Timeout 30s)!"
                else:
                    self.log_msg = "Không tìm thấy lời giải khả thi cho câu đố này."
            finally:
                with self.live_lock:
                    self.live_info["active"] = False
                self.is_solving = False

        self.solver_thread = threading.Thread(target=worker, daemon=True)
        self.solver_thread.start()

    def run_benchmark_comparison(self, force_rerun: bool = False):
        """Chạy cả 2 giải thuật DFS và IDA* liên tiếp để lập bảng so sánh đối đầu."""
        if self.is_solving:
            return

        # Kiểm tra bộ nhớ đệm (Cache) nếu không force_rerun
        if not force_rerun and self.current_filepath in self.puzzle_results_cache:
            self.compare_results = self.puzzle_results_cache[self.current_filepath]
            self.show_compare_modal = True
            return

        self.reset_board()
        self.is_solving = True
        self.solving_algo_name = "BENCHMARK (DFS vs IDA*)"
        self.solver_cancel_event = threading.Event()
        self.solving_start_time = time.perf_counter()

        with self.live_lock:
            self.live_info = {
                "algo": "BENCHMARK",
                "grid": [row[:] for row in self.board.grid],
                "last_pos": (-1, -1),
                "nodes": 0,
                "backtracks": 0,
                "iterations": 0,
                "h": 0,
                "action": "START",
                "active": True
            }
        self.log_msg = "Đang chạy Benchmark đối đầu (DFS vs IDA*)..."

        def worker():
            try:
                # 1. Chạy DFS
                self.solving_algo_name = "BENCHMARK - DFS"
                b_dfs = self.board.copy()
                res_dfs = SteppedSolver.run_dfs(
                    b_dfs,
                    timeout_sec=30.0,
                    cancel_event=self.solver_cancel_event,
                    step_callback=self._on_solver_step
                )

                if self.solver_cancel_event.is_set():
                    return

                # 2. Chạy IDA*
                self.solving_algo_name = "BENCHMARK - IDA*"
                b_ida = self.board.copy()
                res_ida = SteppedSolver.run_ida(
                    b_ida,
                    timeout_sec=30.0,
                    cancel_event=self.solver_cancel_event,
                    step_callback=self._on_solver_step
                )

                self.compare_results = {
                    "dfs": res_dfs,
                    "ida": res_ida,
                    "filename": os.path.basename(self.current_filepath),
                    "rows": self.board.rows,
                    "cols": self.board.cols
                }
                self.puzzle_results_cache[self.current_filepath] = self.compare_results

                if res_dfs["solved"]:
                    self.board = b_dfs
                    self.history_steps = list(b_dfs.history_steps)
                    self.current_step_index = len(self.history_steps) - 1
                elif res_ida["solved"]:
                    self.board = b_ida
                    self.history_steps = list(b_ida.history_steps)
                    self.current_step_index = len(self.history_steps) - 1

                self.show_compare_modal = True
                self.log_msg = "Đã hoàn thành Benchmark đối đầu!"
            finally:
                with self.live_lock:
                    self.live_info["active"] = False
                self.is_solving = False

        self.solver_thread = threading.Thread(target=worker, daemon=True)
        self.solver_thread.start()

    # ==========================================================================
    # ĐIỀU KHIỂN DIỄN HOẠT (ANIMATION PLAYBACK ENGINE)
    # ==========================================================================
    def update_animation(self):
        if not self.is_playing or not self.history_steps:
            return

        now = pygame.time.get_ticks()
        delay_ms = self.speeds[self.playback_speed_idx][1]

        if delay_ms == 0:
            # Max speed: nhảy thẳng đến bước cuối cùng
            self.jump_to_step(len(self.history_steps) - 1)
            self.is_playing = False
            return

        if now - self.last_step_tick >= delay_ms:
            self.last_step_tick = now
            if self.current_step_index < len(self.history_steps) - 1:
                self.step_next()
            else:
                self.is_playing = False

    def step_next(self):
        if self.current_step_index < len(self.history_steps) - 1:
            self.current_step_index += 1
            action, r, c, val = self.history_steps[self.current_step_index]
            self.board.grid[r][c] = val

    def step_prev(self):
        if self.current_step_index >= 0:
            action, r, c, val = self.history_steps[self.current_step_index]
            # Tìm lại giá trị của ô (r, c) ở bước ngay trước đó
            prev_val = self.board.EMPTY
            if (r, c) in self.board.initial_clues:
                prev_val = self.initial_board_data["grid"][r][c]
            else:
                for idx in range(self.current_step_index - 1, -1, -1):
                    _, pr, pc, pval = self.history_steps[idx]
                    if pr == r and pc == c:
                        prev_val = pval
                        break
            self.board.grid[r][c] = prev_val
            self.current_step_index -= 1

    def jump_to_step(self, target_idx: int):
        target_idx = max(-1, min(len(self.history_steps) - 1, target_idx))
        if target_idx == self.current_step_index:
            return

        # Khôi phục bàn cờ về ban đầu
        d = self.initial_board_data
        self.board.grid = [row[:] for row in d["grid"]]

        # Áp dụng lại các bước đến target_idx
        for i in range(target_idx + 1):
            action, r, c, val = self.history_steps[i]
            self.board.grid[r][c] = val

        self.current_step_index = target_idx


    # ==========================================================================
    # XUẤT BÁO CÁO KẾT QUẢ BENCHMARK RA FILE .TXT
    # ==========================================================================
    def export_benchmark_report(self):
        if not self.compare_results:
            return
        try:
            fname = self.compare_results["filename"]
            out_name = f"benchmark_{os.path.splitext(fname)[0]}.txt"
            out_path = os.path.join(SRC_DIR, "..", out_name)

            dfs = self.compare_results["dfs"]
            ida = self.compare_results["ida"]

            with open(out_path, "w", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write(" BÁO CÁO THỰC NGHIỆM SO SÁNH GIẢI THUẬT YIN-YANG (BTL1 - AI)\n")
                f.write(f" File bài toán: {fname} (Kích thước: {self.compare_results['rows']}x{self.compare_results['cols']})\n")
                f.write(f" Thời gian thực nghiệm: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 70 + "\n\n")

                f.write(f"{'Tiêu chí so sánh':<32} | {'Blind Search (DFS)':<18} | {'Heuristic (IDA*)':<18}\n")
                f.write("-" * 74 + "\n")
                f.write(f"{'Trạng thái giải':<32} | {'Thành công' if dfs['solved'] else 'Thất bại':<18} | {'Thành công' if ida['solved'] else 'Thất bại':<18}\n")
                f.write(f"{'Thời gian thực thi (giây)':<32} | {dfs['execution_time_sec']:<18.4f} | {ida['execution_time_sec']:<18.4f}\n")
                f.write(f"{'Bộ nhớ RAM đỉnh (KB)':<32} | {dfs['peak_memory_kb']:<18.2f} | {ida['peak_memory_kb']:<18.2f}\n")
                f.write(f"{'Số trạng thái đã duyệt (Nodes)':<32} | {dfs['nodes_explored']:<18} | {ida['nodes_explored']:<18}\n")
                f.write(f"{'Số lần quay lui (Backtracks)':<32} | {dfs['backtracks']:<18} | {ida['backtracks']:<18}\n")
                f.write(f"{'Số vòng lặp tăng ngưỡng IDA*':<32} | {'N/A':<18} | {ida.get('iterations', 1):<18}\n")
                f.write(f"{'Tổng số bước lưu vết (Steps)':<32} | {dfs.get('total_steps', 0):<18} | {ida.get('total_steps', 0):<18}\n")
                f.write("=" * 70 + "\n\n")

                f.write("KẾT LUẬN & ĐÁNH GIÁ THỰC NGHIỆM:\n")
                if dfs['execution_time_sec'] < ida['execution_time_sec']:
                    f.write("- DFS giải quyết bài toán nhanh hơn nhờ sự kết hợp chặt chẽ của các luật cắt tỉa 2x2 và liên thông trực tiếp.\n")
                else:
                    f.write("- IDA* cho hiệu năng tìm kiếm vượt trội nhờ hàm Heuristic đo độ phân mảnh liên thông định hướng chính xác nhánh đi.\n")

            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                messagebox.showinfo("Xuất Báo Cáo Thành Công", f"Đã lưu báo cáo tại:\n{os.path.abspath(out_path)}")
                root.destroy()
            except Exception:
                pass
        except Exception as e:
            print(f"[!] Lỗi xuất file báo cáo: {e}")

    # ==========================================================================
    # TÍNH TOÁN BỐ CỤC VÀ VẼ GIAO DIỆN CHÍNH
    # ==========================================================================
    def _get_board_layout(self):
        """Tính toán tọa độ và kích thước ô cờ sao cho vừa vặn tuyệt đối trong khu vực hiển thị."""
        area_x = 360
        area_y = 65
        area_w = WINDOW_WIDTH - area_x - 30
        area_h = 710

        margin = 35
        avail_w = area_w - margin * 2
        avail_h = area_h - margin * 2

        cell_sz = min(avail_w // self.board.cols, avail_h // self.board.rows)
        cell_sz = max(18, min(80, cell_sz))

        bw = cell_sz * self.board.cols
        bh = cell_sz * self.board.rows
        bx = area_x + (area_w - bw) // 2
        by = area_y + (area_h - bh) // 2

        return bx, by, bw, bh, cell_sz

    def draw(self):
        self.screen.fill(COLOR_BG)

        # 1. Vẽ Header (Logo Thái Cực và Tiêu đề môn học)
        self._draw_header()

        # 2. Vẽ Panel bên trái (Bảng điều khiển và Thẻ thông số)
        self._draw_left_panel()

        # 3. Vẽ Bàn cờ gỗ Trúc và các quân cờ Âm Dương
        self._draw_board()

        # 4. Vẽ Thanh điều khiển diễn hoạt Step-by-Step
        self._draw_playback_bar()

        # 5. Vẽ Modal So Sánh Đối Đầu nếu đang mở
        if self.show_compare_modal:
            self._draw_compare_modal()

        pygame.display.flip()

    def _draw_header(self):
        # Thanh header trên cùng
        hdr_rect = pygame.Rect(0, 0, WINDOW_WIDTH, 56)
        pygame.draw.rect(self.screen, COLOR_PANEL, hdr_rect)
        pygame.draw.line(self.screen, (45, 52, 70), (0, 56), (WINDOW_WIDTH, 56), 1)

        # Huy hiệu Thái Cực
        VectorSprites.draw_taijitu(self.screen, 38, 28, 18)

        # Tiêu đề
        title_surf = self.font_title.render("YIN-YANG PUZZLE SOLVER", True, COLOR_GOLD)
        self.screen.blit(title_surf, (68, 16))

        sub_surf = self.font_small.render("TÌM KIẾM ĐỐI KHÁNG VÀ HEURISTIC", True, COLOR_TEXT_MUTED)
        self.screen.blit(sub_surf, (68, 38))

        # Vẽ các nút Tab Lọc danh mục và chuyển câu đố
        for key, btn in self.buttons.items():
            if key.startswith("cat_") or key in ("prev_puzzle", "next_puzzle", "open_file", "reset_board"):
                btn.draw(self.screen)

    def _draw_left_panel(self):
        px = 20
        py = 70
        pw = 310
        ph = WINDOW_HEIGHT - py - 20

        # Khung panel chính
        pygame.draw.rect(self.screen, COLOR_PANEL, (px, py, pw, ph), border_radius=10)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, (px, py, pw, ph), 1, border_radius=10)

        # 1. Thẻ thông tin bài toán hiện tại (Puzzle Info Card)
        card1_rect = pygame.Rect(px + 12, py + 12, pw - 24, 85)
        pygame.draw.rect(self.screen, COLOR_CARD, card1_rect, border_radius=8)
        pygame.draw.rect(self.screen, (50, 58, 78), card1_rect, 1, border_radius=8)

        fname = os.path.basename(self.current_filepath) if self.current_filepath else "Chưa chọn file"
        lbl_p = self.font_bold.render(f"Bài toán: {fname[:22]}", True, COLOR_GOLD)
        self.screen.blit(lbl_p, (card1_rect.x + 12, card1_rect.y + 10))

        if self.board:
            total_cells = self.board.rows * self.board.cols
            clues_cnt = len(self.board.initial_clues)
            empty_cnt = total_cells - clues_cnt
            sz_str = f"Kích thước: {self.board.rows}x{self.board.cols} ({total_cells} ô cờ)"
            self.screen.blit(self.font_medium.render(sz_str, True, COLOR_TEXT_LABEL), (card1_rect.x + 12, card1_rect.y + 34))
            clue_str = f"Manh mối gốc: {clues_cnt} ô | Cần điền: {empty_cnt} ô"
            self.screen.blit(self.font_small.render(clue_str, True, COLOR_TEXT_MUTED), (card1_rect.x + 12, card1_rect.y + 56))

        # 2. Vẽ các nút bấm thuật toán (DFS, IDA*, Compare)
        for key in ["solve_dfs", "solve_ida", "compare"]:
            if key in self.buttons:
                self.buttons[key].draw(self.screen)

        # 3. Thẻ Thông số Thực nghiệm (Benchmark & Live Metrics Card)
        card2_y = 352
        card2_h = ph - (card2_y - py) - 12
        card2_rect = pygame.Rect(px + 12, card2_y, pw - 24, card2_h)
        pygame.draw.rect(self.screen, COLOR_CARD, card2_rect, border_radius=8)
        pygame.draw.rect(self.screen, (50, 58, 78), card2_rect, 1, border_radius=8)

        # Tiêu đề thẻ thông số
        self.screen.blit(self.font_bold.render("KẾT QUẢ THỰC NGHIỆM", True, COLOR_GOLD), (card2_rect.x + 14, card2_y + 14))

        # Trạng thái đang giải / đã giải
        status_y = card2_y + 44
        if self.is_solving:
            elapsed = time.perf_counter() - self.solving_start_time
            st_txt = f"ĐANG TÌM KIẾM ({self.solving_algo_name})... {elapsed:.1f}s"
            st_color = (255, 215, 0)
            with self.live_lock:
                live_nodes = self.live_info.get("nodes", 0)
                live_bts = self.live_info.get("backtracks", 0)
                live_iters = self.live_info.get("iterations", 0)
            lines = [
                ("Thời gian chạy:", f"{elapsed:.3f} s"),
                ("RAM đỉnh:", "Đang đo đạc..."),
                ("Số node duyệt:", f"{live_nodes:,}"),
                ("Số lần quay lui:", f"{live_bts:,}"),
                ("Số bước lưu vết:", "Đang ghi nhận..."),
            ]
            if live_iters > 0 or "IDA" in self.solving_algo_name:
                lines.append(("Vòng lặp IDA*:", f"{live_iters}"))
        elif self.metrics["solved"]:
            st_txt = f"THÀNH CÔNG ({self.metrics['algo_name']})"
            st_color = (46, 204, 113)
            lines = [
                ("Thời gian chạy:", f"{self.metrics['time_sec']:.4f} s"),
                ("RAM đỉnh:", f"{self.metrics['peak_mem_kb']:.2f} KB"),
                ("Số node duyệt:", f"{self.metrics['nodes_explored']:,}"),
                ("Số lần quay lui:", f"{self.metrics['backtracks']:,}"),
                ("Số bước lưu vết:", f"{len(self.history_steps):,}"),
            ]
            if self.metrics.get("iterations", 0) > 0:
                lines.append(("Vòng lặp IDA*:", f"{self.metrics['iterations']}"))
        elif self.metrics["timed_out"]:
            st_txt = "HẾT THỜI GIAN (TIMEOUT)"
            st_color = COLOR_DANGER
            lines = [
                ("Thời gian chạy:", f"{self.metrics['time_sec']:.4f} s"),
                ("RAM đỉnh:", f"{self.metrics['peak_mem_kb']:.2f} KB"),
                ("Số node duyệt:", f"{self.metrics['nodes_explored']:,}"),
                ("Số lần quay lui:", f"{self.metrics['backtracks']:,}"),
                ("Số bước lưu vết:", f"{len(self.history_steps):,}"),
            ]
        elif self.metrics["user_stopped"]:
            st_txt = "NGƯỜI DÙNG DỪNG"
            st_color = COLOR_DANGER
            lines = [
                ("Thời gian chạy:", f"{self.metrics['time_sec']:.4f} s"),
                ("RAM đỉnh:", f"{self.metrics['peak_mem_kb']:.2f} KB"),
                ("Số node duyệt:", f"{self.metrics['nodes_explored']:,}"),
                ("Số lần quay lui:", f"{self.metrics['backtracks']:,}"),
                ("Số bước lưu vết:", f"{len(self.history_steps):,}"),
            ]
        else:
            st_txt = "SẴN SÀNG"
            st_color = COLOR_TEXT_MUTED
            lines = [
                ("Thời gian chạy:", "0.0000 s"),
                ("RAM đỉnh:", "0.00 KB"),
                ("Số node duyệt:", "0"),
                ("Số lần quay lui:", "0"),
                ("Số bước lưu vết:", f"{len(self.history_steps):,}"),
            ]

        pygame.draw.rect(self.screen, (22, 26, 36), (card2_rect.x + 10, status_y, card2_rect.width - 20, 30), border_radius=5)
        self.screen.blit(self.font_bold.render(st_txt, True, st_color), (card2_rect.x + 18, status_y + 6))

        line_y = status_y + 44
        for lbl, val in lines:
            self.screen.blit(self.font_medium.render(lbl, True, COLOR_TEXT_MUTED), (card2_rect.x + 14, line_y))
            v_surf = self.font_bold.render(val, True, COLOR_TEXT_WHITE)
            v_rect = v_surf.get_rect(right=card2_rect.right - 14, top=line_y)
            self.screen.blit(v_surf, v_rect)
            line_y += 28

    def _draw_board(self):
        if not self.board:
            return

        bx, by, bw, bh, cell_sz = self._get_board_layout()

        # 1. Đế bàn cờ gỗ Trúc (Bamboo Wood Plank with bevel & shadow)
        bevel = 14
        wood_rect = pygame.Rect(bx - bevel, by - bevel, bw + bevel * 2, bh + bevel * 2)

        # Bóng đổ bàn cờ
        shadow_rect = pygame.Rect(wood_rect.x + 6, wood_rect.y + 8, wood_rect.width, wood_rect.height)
        pygame.draw.rect(self.screen, (10, 12, 16), shadow_rect, border_radius=8)

        # Mặt gỗ chính
        pygame.draw.rect(self.screen, COLOR_BOARD_WOOD, wood_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_BOARD_WOOD_DARK, wood_rect, 2, border_radius=8)

        # Vân gỗ trang nhã (Subtle Wood Grains)
        grain_surf = pygame.Surface((wood_rect.width, wood_rect.height), pygame.SRCALPHA)
        for gy in range(0, wood_rect.height, 6):
            alpha = random.randint(8, 16) if gy % 18 == 0 else 5
            pygame.draw.line(grain_surf, (160, 115, 65, alpha), (0, gy), (wood_rect.width, gy), 1)
        self.screen.blit(grain_surf, wood_rect.topleft)

        # 2. Vẽ lưới ô cờ Vây (Grid Lines)
        for r in range(self.board.rows):
            cy = by + int((r + 0.5) * cell_sz)
            pygame.draw.line(self.screen, COLOR_GRID_LINE, (bx + cell_sz // 2, cy), (bx + bw - cell_sz // 2, cy), 1)

        for c in range(self.board.cols):
            cx = bx + int((c + 0.5) * cell_sz)
            pygame.draw.line(self.screen, COLOR_GRID_LINE, (cx, by + cell_sz // 2), (cx, by + bh - cell_sz // 2), 1)

        # Khung viền bàn cờ
        pygame.draw.rect(self.screen, COLOR_GRID_LINE, (bx + cell_sz // 2, by + cell_sz // 2, bw - cell_sz, bh - cell_sz), 2)

        # 3. Vẽ các điểm sao Hoshi (Star Points)
        if self.board.rows >= 10 and self.board.cols >= 10:
            star_coords = []
            if self.board.rows == 10:
                star_coords = [(2, 2), (2, 7), (7, 2), (7, 7)]
            elif self.board.rows >= 15:
                star_coords = [(3, 3), (3, self.board.cols - 4), (self.board.rows - 4, 3), (self.board.rows - 4, self.board.cols - 4),
                               (self.board.rows // 2, self.board.cols // 2)]
            for sr, sc in star_coords:
                if sr < self.board.rows and sc < self.board.cols:
                    sx = bx + int((sc + 0.5) * cell_sz)
                    sy = by + int((sr + 0.5) * cell_sz)
                    pygame.draw.circle(self.screen, COLOR_STAR_POINT, (sx, sy), max(2, cell_sz // 12))

        # 4. Xác định ma trận cờ và vị trí quân cờ tiêu điểm cần vẽ
        if self.is_solving and self.live_info.get("active") and self.live_info.get("grid"):
            with self.live_lock:
                display_grid = [row[:] for row in self.live_info["grid"]]
                last_pos = self.live_info.get("last_pos", (-1, -1))
        else:
            display_grid = self.board.grid
            last_pos = (-1, -1)
            if 0 <= self.current_step_index < len(self.history_steps):
                _, sr, sc, _ = self.history_steps[self.current_step_index]
                last_pos = (sr, sc)

        # 5. Vẽ các quân cờ Âm Dương
        stone_radius = int(cell_sz * 0.42)
        for r in range(self.board.rows):
            for c in range(self.board.cols):
                val = display_grid[r][c]
                cx = bx + int((c + 0.5) * cell_sz)
                cy = by + int((r + 0.5) * cell_sz)

                if val in (self.board.BLACK, self.board.WHITE):
                    is_clue = ((r, c) in self.board.initial_clues)
                    VectorSprites.draw_stone(self.screen, cx, cy, stone_radius, val, is_clue=is_clue)

        # 6. Hiệu ứng Hào quang (Luminous Focus Halo) đánh dấu quân cờ đang xét / vừa đặt
        if last_pos != (-1, -1) and 0 <= last_pos[0] < self.board.rows and 0 <= last_pos[1] < self.board.cols:
            lr, lc = last_pos
            lx = bx + int((lc + 0.5) * cell_sz)
            ly = by + int((lr + 0.5) * cell_sz)
            pulse = (math.sin(time.perf_counter() * 9) + 1) / 2.0
            halo_r = int(stone_radius + 4 + 3 * pulse)
            halo_alpha = int(140 + 105 * pulse)
            halo_surf = pygame.Surface((halo_r * 2 + 6, halo_r * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(halo_surf, (0, 230, 118, halo_alpha), (halo_r + 3, halo_r + 3), halo_r, 2)
            self.screen.blit(halo_surf, (lx - halo_r - 3, ly - halo_r - 3))

        # 7. Vẽ thanh Live Search HUD phía trên bàn cờ nếu đang giải thuật toán
        if self.is_solving:
            self._draw_live_search_hud(bx, by, bw)

    def _draw_playback_bar(self):
        # Vẽ các nút điều khiển Step-by-Step
        for key in ["step_first", "step_prev", "step_play", "step_next", "step_last", "speed_toggle"]:
            if key in self.buttons:
                if key == "step_play":
                    self.buttons[key].icon_type = "pause" if self.is_playing else "play"
                    self.buttons[key].text = ""
                elif key == "speed_toggle":
                    self.buttons[key].text = f"{self.speeds[self.playback_speed_idx][0]} {'▲' if self.show_speed_menu else '▼'}"
                self.buttons[key].draw(self.screen)

        # Vẽ thanh Scrub Bar
        total_steps = len(self.history_steps)
        self.scrub_bar.draw(self.screen, self.current_step_index + 1, total_steps)

        # Dòng trạng thái / Live log và bộ đếm bước
        status_line = f"> {self.log_msg}"
        if len(status_line) > 70:
            status_line = status_line[:67] + "..."
        lbl_log = self.font_small.render(status_line, True, COLOR_GOLD)
        self.screen.blit(lbl_log, (self.scrub_bar.rect.x, self.scrub_bar.rect.y - 20))

        step_txt = f"Bước: {self.current_step_index + 1} / {total_steps}"
        lbl_step = self.font_small.render(step_txt, True, COLOR_TEXT_LABEL)
        lbl_step_rect = lbl_step.get_rect(right=self.scrub_bar.rect.right, bottom=self.scrub_bar.rect.y - 4)
        self.screen.blit(lbl_step, lbl_step_rect)

        # Vẽ Hộp tùy chọn Tốc độ (Speed Option Box) nếu đang mở
        if self.show_speed_menu:
            self._draw_speed_menu()

    # ==========================================================================
    # CỬA SỔ MODAL SO SÁNH ĐỐI ĐẦU SIDE-BY-SIDE (BENCHMARK MODAL)
    # ==========================================================================
    def _draw_compare_modal(self):
        if not self.compare_results:
            return

        # Lớp phủ mờ tối toàn màn hình
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))

        # Cửa sổ Dialog nổi bật
        mw = 780
        mh = 490
        mx = (WINDOW_WIDTH - mw) // 2
        my = (WINDOW_HEIGHT - mh) // 2
        dialog_rect = pygame.Rect(mx, my, mw, mh)

        pygame.draw.rect(self.screen, COLOR_PANEL, dialog_rect, border_radius=12)
        pygame.draw.rect(self.screen, COLOR_GOLD, dialog_rect, 2, border_radius=12)

        # Header Dialog
        self.screen.blit(self.font_large.render("BẢNG SO SÁNH ĐỐI ĐẦU GIẢI THUẬT (BTL1 - AI)", True, COLOR_GOLD), (mx + 25, my + 22))
        f_info = f"Bài toán: {self.compare_results['filename']} ({self.compare_results['rows']}x{self.compare_results['cols']})"
        self.screen.blit(self.font_medium.render(f_info, True, COLOR_TEXT_MUTED), (mx + 25, my + 54))

        # Bảng dữ liệu thực nghiệm
        tbl_x = mx + 25
        tbl_y = my + 95
        tbl_w = mw - 50
        row_h = 36

        # Hàng tiêu đề bảng
        pygame.draw.rect(self.screen, (38, 44, 60), (tbl_x, tbl_y, tbl_w, row_h), border_radius=6)
        self.screen.blit(self.font_bold.render("TIÊU CHÍ ĐÁNH GIÁ", True, COLOR_TEXT_LABEL), (tbl_x + 15, tbl_y + 8))
        self.screen.blit(self.font_bold.render("BLIND SEARCH (DFS)", True, COLOR_DFS), (tbl_x + 320, tbl_y + 8))
        self.screen.blit(self.font_bold.render("HEURISTIC (IDA*)", True, COLOR_IDA), (tbl_x + 550, tbl_y + 8))

        dfs = self.compare_results["dfs"]
        ida = self.compare_results["ida"]

        rows_data = [
            ("Trạng thái tìm kiếm", "THÀNH CÔNG" if dfs["solved"] else "THẤT BẠI", "THÀNH CÔNG" if ida["solved"] else "THẤT BẠI"),
            ("Thời gian thực thi", f"{dfs['execution_time_sec']:.4f} s", f"{ida['execution_time_sec']:.4f} s"),
            ("Bộ nhớ RAM đỉnh", f"{dfs['peak_memory_kb']:.2f} KB", f"{ida['peak_memory_kb']:.2f} KB"),
            ("Số trạng thái đã duyệt", f"{dfs['nodes_explored']:,}", f"{ida['nodes_explored']:,}"),
            ("Số lần quay lui (Backtracks)", f"{dfs['backtracks']:,}", f"{ida['backtracks']:,}"),
            ("Số vòng lặp tăng ngưỡng IDA*", "N/A", f"{ida.get('iterations', 1)}"),
            ("Số bước lưu vết (Steps)", f"{dfs.get('total_steps', 0):,}", f"{ida.get('total_steps', 0):,}")
        ]

        curr_y = tbl_y + row_h + 4
        for i, (crit, v_dfs, v_ida) in enumerate(rows_data):
            bg_col = (30, 35, 48) if i % 2 == 0 else (24, 28, 38)
            pygame.draw.rect(self.screen, bg_col, (tbl_x, curr_y, tbl_w, row_h - 2), border_radius=4)

            self.screen.blit(self.font_medium.render(crit, True, COLOR_TEXT_WHITE), (tbl_x + 15, curr_y + 6))
            self.screen.blit(self.font_bold.render(v_dfs, True, COLOR_DFS if "THÀNH" in v_dfs else COLOR_TEXT_LABEL), (tbl_x + 320, curr_y + 6))
            self.screen.blit(self.font_bold.render(v_ida, True, COLOR_IDA if "THÀNH" in v_ida else COLOR_TEXT_LABEL), (tbl_x + 550, curr_y + 6))
            curr_y += row_h

        # Nút Đóng, Đo lại & Nút Xuất báo cáo
        btn_y = my + mh - 55
        self.btn_export = Button((mx + 25, btn_y, 210, 38), "XUẤT BÁO CÁO TXT", COLOR_CARD, COLOR_CARD_HOVER, font=self.font_bold, border_radius=6, border_color=COLOR_GOLD)
        self.btn_modal_rerun = Button((mx + 250, btn_y, 190, 38), "ĐO LẠI (RE-RUN)", COLOR_CARD, COLOR_CARD_HOVER, font=self.font_bold, border_radius=6, border_color=COLOR_IDA)
        self.btn_close_modal = Button((mx + mw - 140, btn_y, 115, 38), "ĐÓNG", COLOR_GOLD, COLOR_GOLD_HOVER, text_color=(20, 20, 20), font=self.font_bold, border_radius=6)

        self.btn_export.draw(self.screen)
        self.btn_modal_rerun.draw(self.screen)
        self.btn_close_modal.draw(self.screen)

    # ==========================================================================
    # VÒNG LẶP CHÍNH (MAIN LOOP & EVENT HANDLING)
    # ==========================================================================
    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            self.update_animation()

            mouse_pos = pygame.mouse.get_pos()
            any_hover = False

            # Tự động thay đổi con trỏ chuột sang hình bàn tay (Cursor-Pointer) khi trỏ vào nút hoặc thanh trượt
            if self.show_compare_modal:
                for b in [getattr(self, 'btn_export', None), getattr(self, 'btn_modal_rerun', None), getattr(self, 'btn_close_modal', None)]:
                    if b and hasattr(b, "rect") and b.rect.collidepoint(mouse_pos):
                        any_hover = True
                        break
            elif self.is_solving:
                if hasattr(self, 'btn_stop_solving') and self.btn_stop_solving.rect.collidepoint(mouse_pos):
                    any_hover = True
                elif self.buttons["speed_toggle"].rect.collidepoint(mouse_pos):
                    any_hover = True
                elif self.show_speed_menu:
                    menu_rect, _ = self._get_speed_menu_rects()
                    if menu_rect.collidepoint(mouse_pos):
                        any_hover = True
            else:
                if self.show_speed_menu:
                    menu_rect, _ = self._get_speed_menu_rects()
                    if menu_rect.collidepoint(mouse_pos):
                        any_hover = True
                if not any_hover:
                    for btn in self.buttons.values():
                        if btn.rect.collidepoint(mouse_pos):
                            any_hover = True
                            break
                if not any_hover and self.scrub_bar.rect.collidepoint(mouse_pos):
                    any_hover = True

            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if any_hover else pygame.SYSTEM_CURSOR_ARROW)
            except Exception:
                pass

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if self.is_solving and self.solver_cancel_event:
                        self.solver_cancel_event.set()
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if self.is_solving:
                            self.request_stop_solving()
                        elif self.history_steps:
                            self.is_playing = not self.is_playing
                            if self.is_playing and self.current_step_index >= len(self.history_steps) - 1:
                                self.jump_to_step(0)
                    elif event.key == pygame.K_RIGHT:
                        self.is_playing = False
                        self.step_next()
                    elif event.key == pygame.K_LEFT:
                        self.is_playing = False
                        self.step_prev()
                    elif event.key == pygame.K_HOME:
                        self.is_playing = False
                        self.jump_to_step(0)
                    elif event.key == pygame.K_END:
                        self.is_playing = False
                        self.jump_to_step(len(self.history_steps) - 1)
                    elif event.key == pygame.K_ESCAPE:
                        if self.show_speed_menu:
                            self.show_speed_menu = False
                        elif self.show_compare_modal:
                            self.show_compare_modal = False
                        elif self.is_solving:
                            self.request_stop_solving()

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mpos = event.pos

                    # 1. Sự kiện trong Modal So Sánh
                    if self.show_compare_modal:
                        if hasattr(self, 'btn_close_modal') and self.btn_close_modal.rect.collidepoint(mpos):
                            self.show_compare_modal = False
                        elif hasattr(self, 'btn_export') and self.btn_export.rect.collidepoint(mpos):
                            self.export_benchmark_report()
                        elif hasattr(self, 'btn_modal_rerun') and self.btn_modal_rerun.rect.collidepoint(mpos):
                            self.show_compare_modal = False
                            if self.current_filepath in self.puzzle_results_cache:
                                del self.puzzle_results_cache[self.current_filepath]
                            self.run_benchmark_comparison(force_rerun=True)
                        continue

                    # 2. Xử lý khi đang giải thuật toán
                    if self.is_solving:
                        if hasattr(self, 'btn_stop_solving') and self.btn_stop_solving.rect.collidepoint(mpos):
                            self.request_stop_solving()
                            continue
                        elif self.show_speed_menu:
                            menu_rect, item_rects = self._get_speed_menu_rects()
                            handled = False
                            for i, irect in enumerate(item_rects):
                                if irect.collidepoint(mpos):
                                    self.playback_speed_idx = i
                                    self.show_speed_menu = False
                                    handled = True
                                    break
                            if not handled:
                                self.show_speed_menu = False
                            continue
                        elif self.buttons["speed_toggle"].rect.collidepoint(mpos):
                            self.show_speed_menu = not self.show_speed_menu
                            continue
                        continue

                    # 3. Xử lý menu tốc độ khi ở chế độ bình thường
                    if self.show_speed_menu:
                        menu_rect, item_rects = self._get_speed_menu_rects()
                        handled = False
                        for i, irect in enumerate(item_rects):
                            if irect.collidepoint(mpos):
                                self.playback_speed_idx = i
                                self.show_speed_menu = False
                                handled = True
                                break
                        if handled:
                            continue
                        elif self.buttons["speed_toggle"].rect.collidepoint(mpos):
                            self.show_speed_menu = False
                            continue
                        else:
                            self.show_speed_menu = False

                    # 4. Xử lý click thanh Scrub Bar
                    if self.scrub_bar.rect.collidepoint(mpos):
                        self.is_playing = False
                        self.scrub_bar.is_dragging = True
                        step = self.scrub_bar.get_step_at(mpos[0], len(self.history_steps))
                        self.jump_to_step(step)
                        continue

                    # 5. Xử lý click các nút bấm
                    for key, btn in self.buttons.items():
                        if btn.rect.collidepoint(mpos):
                            if key.startswith("cat_"):
                                self.set_category_filter(btn.cat_key)
                            elif key == "prev_puzzle":
                                if self.filtered_puzzle_files:
                                    self.current_puzzle_index = (self.current_puzzle_index - 1) % len(self.filtered_puzzle_files)
                                    self.load_puzzle(self.filtered_puzzle_files[self.current_puzzle_index])
                            elif key == "next_puzzle":
                                if self.filtered_puzzle_files:
                                    self.current_puzzle_index = (self.current_puzzle_index + 1) % len(self.filtered_puzzle_files)
                                    self.load_puzzle(self.filtered_puzzle_files[self.current_puzzle_index])
                            elif key == "open_file":
                                try:
                                    root = tk.Tk()
                                    root.withdraw()
                                    root.attributes("-topmost", True)
                                    f = filedialog.askopenfilename(initialdir=INPUTS_DIR, title="Chọn file bài toán Yin-Yang", filetypes=[("Text files", "*.txt")])
                                    root.destroy()
                                    if f:
                                        self.load_puzzle(f)
                                except Exception:
                                    pass
                            elif key == "reset_board":
                                self.reset_board()
                            elif key == "solve_dfs":
                                self.start_solving("DFS")
                            elif key == "solve_ida":
                                self.start_solving("IDA*")
                            elif key == "compare":
                                self.run_benchmark_comparison()
                            elif key == "step_first":
                                self.is_playing = False
                                self.jump_to_step(0)
                            elif key == "step_prev":
                                self.is_playing = False
                                self.step_prev()
                            elif key == "step_play":
                                if self.history_steps:
                                    self.is_playing = not self.is_playing
                                    if self.is_playing and self.current_step_index >= len(self.history_steps) - 1:
                                        self.jump_to_step(0)
                            elif key == "step_next":
                                self.is_playing = False
                                self.step_next()
                            elif key == "step_last":
                                self.is_playing = False
                                self.jump_to_step(len(self.history_steps) - 1)
                            elif key == "speed_toggle":
                                self.show_speed_menu = not self.show_speed_menu

                elif event.type == pygame.MOUSEBUTTONUP:
                    self.scrub_bar.is_dragging = False

                elif event.type == pygame.MOUSEMOTION:
                    mpos = event.pos
                    if self.scrub_bar.is_dragging:
                        step = self.scrub_bar.get_step_at(mpos[0], len(self.history_steps))
                        self.jump_to_step(step)

                    for btn in self.buttons.values():
                        btn.is_hovered = btn.rect.collidepoint(mpos)

                    if hasattr(self, 'btn_stop_solving'):
                        self.btn_stop_solving.is_hovered = self.btn_stop_solving.rect.collidepoint(mpos)

                    if self.show_compare_modal:
                        if hasattr(self, 'btn_close_modal'):
                            self.btn_close_modal.is_hovered = self.btn_close_modal.rect.collidepoint(mpos)
                        if hasattr(self, 'btn_export'):
                            self.btn_export.is_hovered = self.btn_export.rect.collidepoint(mpos)
                        if hasattr(self, 'btn_modal_rerun'):
                            self.btn_modal_rerun.is_hovered = self.btn_modal_rerun.rect.collidepoint(mpos)

            self.draw()

        pygame.quit()


if __name__ == "__main__":
    app = YinYangGameGUI()
    app.run()
