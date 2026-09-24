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

# Thiết lập DPI Awareness & UTF-8 cho Windows để phông chữ sắc nét 100%, không bị vỡ/mờ do display scaling
if sys.platform == "win32":
    try:
        import ctypes
        # Ưu tiên Per Monitor V2 trên Windows 10/11
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
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
COLOR_CARD_BORDER = (65, 85, 125)
COLOR_CARD_HOVER = (42, 56, 86)

# Chữ và nhãn (Độ tương phản cao, chống chìm nền)
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_MUTED = (205, 220, 245)
COLOR_TEXT_LABEL = (225, 238, 255)
COLOR_TEXT_GOLD = (255, 218, 110)

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
    chuyển dịch trạng thái để phục vụ diễn hoạt Step-by-Step và kiểm soát dừng.
    """
    def __init__(self, board: TentsBoard, max_restarts: int = None, max_steps_per_restart: int = 250, max_sideways: int = 25, timeout_sec: float = None, cancel_event=None, step_callback=None):
        super().__init__(board, max_restarts, max_steps_per_restart, max_sideways, timeout_sec, cancel_event, step_callback)
        self.recorded_steps = []
        self.timed_out = False
        self.user_stopped = False

    def solve_recorded(self):
        tracemalloc.start()
        start_time = time.perf_counter()

        best_state = None
        best_score = float("inf")
        current_state = None
        current_score = float("inf")
        self.recorded_steps = []
        MAX_STEPS_CAP = 5000

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

                    if self.step_callback:
                        self.step_callback("MOVE", current_state, current_score, self.total_restarts, self.states_evaluated, new_pos)

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

                    if self.step_callback:
                        self.step_callback("SIDEWAYS", current_state, current_score, self.total_restarts, self.states_evaluated, new_pos)

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

            if self.solved or self.timed_out or self.user_stopped:
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

        if self.user_stopped and not self.solved and len(self.recorded_steps) < MAX_STEPS_CAP:
            self.recorded_steps.append({
                "action": "HC_STOPPED",
                "state": list(best_state) if best_state else (list(current_state) if current_state else []),
                "score": best_score,
                "log": f"Nguoi dung da dung thuat toan! Chua tim thay loi giai (Diem tot nhat h = {best_score})"
            })
        elif self.timed_out and not self.solved and len(self.recorded_steps) < MAX_STEPS_CAP:
            self.recorded_steps.append({
                "action": "HC_TIMEOUT",
                "state": list(best_state) if best_state else (list(current_state) if current_state else []),
                "score": best_score,
                "log": f"Dung do het thoi gian an toan ({self.timeout_sec:.0f}s). Diem tot nhat: h = {best_score}"
            })

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
        border_color = (130, 175, 240) if (self.is_hovered and self.enabled) else (70, 92, 135)
        pygame.draw.rect(surface, border_color, self.rect, 1, border_radius=6)

        icon_color = self.text_color if self.enabled else (120, 135, 160)

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
        pygame.display.set_caption("Tents & Trees Search Algorithms (DFS & HC)")
        self.clock = pygame.time.Clock()

        # Khởi tạo Phông chữ hệ thống sắc nét
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
        self.puzzle_data = None
        self.board = None

        # Trạng thái diễn hoạt Step-by-Step AI
        self.history_steps = []
        self.current_step_index = -1
        self.is_playing = False
        self.current_algo = "NONE"
        self.playback_speed_idx = 1
        self.speeds = [
            ("0.5x", 400, "0.5x (Cham)"),
            ("1.0x", 180, "1.0x (Chuan)"),
            ("2.0x", 80,  "2.0x (Nhanh)"),
            ("5.0x", 25,  "5.0x (Rat nhanh)"),
            ("10.0x", 8,  "10.0x (Cuc nhanh)"),
            ("Max", 0,    "Max (Tuc thi)")
        ]
        self.show_speed_menu = False
        self.last_step_tick = 0

        # Trạng thái luồng chạy nền (Worker Thread) & Khảo sát trực tiếp (Live Search)
        self.is_solving = False
        self.solver_cancel_event = None
        self.solving_algo_name = ""
        self.solving_start_time = 0.0
        self.solver_thread = None
        self.live_lock = threading.Lock()
        self.live_info = {
            "algo": "",
            "tents": set(),
            "last_pos": (-1, -1),
            "nodes": 0,
            "backtracks": 0,
            "restarts": 0,
            "heuristic": 0,
            "action": "IDLE",
            "active": False
        }

        # Thông số đo đạc Benchmark
        self.metrics = {
            "time_sec": 0.0,
            "peak_mem_kb": 0.0,
            "nodes_or_states": 0,
            "backtracks_or_restarts": 0,
            "solved": False,
            "timed_out": False,
            "user_stopped": False,
            "algo_name": ""
        }

        # Trạng thái Cửa sổ Modal So sánh Side-by-side
        self.show_compare_modal = False
        self.compare_results = None
        self.puzzle_results_cache = {}  # {filepath: {"dfs": result_dict, "hc": result_dict}}

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
            Button((panel_x + 10, 78, 65, 26), "Tat ca", (36, 46, 70), (50, 65, 95), font_size=12),
            Button((panel_x + 80, 78, 60, 26), "6x6", (36, 46, 70), (50, 65, 95), font_size=12),
            Button((panel_x + 145, 78, 60, 26), "8x8", (36, 46, 70), (50, 65, 95), font_size=12),
            Button((panel_x + 210, 78, 65, 26), "10x10", (36, 46, 70), (50, 65, 95), font_size=12),
            Button((panel_x + 280, 78, 65, 26), "15x15", (36, 46, 70), (50, 65, 95), font_size=12),
            Button((panel_x + 350, 78, 70, 26), "Special", (36, 46, 70), (50, 65, 95), font_size=12),
        ]

        # CARD 1: Điều hướng đề
        btn_row_y = 142
        self.btn_prev_puzzle = Button((panel_x + 10, btn_row_y, 85, 32), "< Truoc", (40, 52, 78), (55, 72, 108), text_color=(235, 245, 255), font_size=13)
        self.btn_next_puzzle = Button((panel_x + 102, btn_row_y, 85, 32), "Sau >", (40, 52, 78), (55, 72, 108), text_color=(235, 245, 255), font_size=13)
        self.btn_random_puzzle = Button((panel_x + 194, btn_row_y, 105, 32), "Ngau nhien", (40, 52, 78), (55, 72, 108), text_color=(235, 245, 255), font_size=13)
        self.btn_browse = Button((panel_x + 306, btn_row_y, 105, 32), "Mo file...", (31, 110, 165), (41, 128, 185), text_color=COLOR_TEXT_WHITE, font_size=13)
        self.btn_reset_board = Button((panel_x + 418, btn_row_y, 85, 32), "Dat lai", (50, 65, 95), (70, 85, 120), text_color=(235, 245, 255), font_size=13)

        # CARD 2: Chọn thuật toán tìm kiếm (3 nút dàn đều đẹp mắt)
        btn2_y = 228
        btn2_h = 38
        self.btn_run_dfs = Button((panel_x + 10, btn2_y, 135, btn2_h), "Chay DFS", COLOR_DFS, COLOR_DFS_HOVER, font_size=13)
        self.btn_run_hc = Button((panel_x + 152, btn2_y, 145, btn2_h), "Hill Climbing", COLOR_HC, COLOR_HC_HOVER, font_size=13)
        self.btn_compare = Button((panel_x + 304, btn2_y, 201, btn2_h), "Benchmark (DFS vs HC)", COLOR_COMPARE, COLOR_COMPARE_HOVER, font_size=12)

        # CARD 3: Điều khiển hoạt cảnh
        btn3_y = 330
        self.btn_step_first = Button((panel_x + 10, btn3_y, 45, 32), "", (40, 52, 78), (60, 78, 112), icon_type="first")
        self.btn_step_prev = Button((panel_x + 60, btn3_y, 45, 32), "", (40, 52, 78), (60, 78, 112), icon_type="prev")
        self.btn_play_pause = Button((panel_x + 110, btn3_y, 95, 32), "Phat", COLOR_SUCCESS, (56, 220, 125), icon_type="play")
        self.btn_step_next = Button((panel_x + 210, btn3_y, 45, 32), "", (40, 52, 78), (60, 78, 112), icon_type="next")
        self.btn_step_last = Button((panel_x + 260, btn3_y, 45, 32), "", (40, 52, 78), (60, 78, 112), icon_type="last")
        self.btn_speed = Button((panel_x + 315, btn3_y, 85, 32), "1.0x ▼", (50, 65, 95), (70, 85, 120), font_size=13)
        self.btn_clear_step = Button((panel_x + 408, btn3_y, 97, 32), "Huy buoc", (198, 40, 40), (229, 57, 53), font_size=13)

        # Thanh kéo Scrub Bar
        self.scrub_bar = ScrubBar((panel_x + 10, 375, 495, 12))

        # Nút Dừng giải thuật trên thanh HUD góc bàn cờ
        self.btn_stop_solving = Button((0, 0, 92, 30), "Dung [ESC]", (195, 40, 40), (230, 55, 55), text_color=(255, 255, 255), font_size=12)

        # Modal So sánh Buttons
        self.btn_modal_rerun = Button((0, 0, 185, 38), "Do lai tu dau (Re-run)", (180, 95, 20), (215, 120, 25), font_size=12)
        self.btn_modal_export = Button((940, 680, 160, 38), "Xuat file Bao cao", COLOR_SUCCESS, (56, 220, 125))
        self.btn_modal_close = Button((1115, 680, 100, 38), "Dong", (100, 110, 130), (130, 140, 160))

    def request_stop_solving(self):
        """Kích hoạt cờ dừng an toàn để ngắt Solver Worker Thread ngay lập tức."""
        if self.is_solving and self.solver_cancel_event:
            self.solver_cancel_event.set()

    def reset_board_state(self):
        """Xoa sach hoan toan trang thai leu cua bat ky giai thuat nao truoc do."""
        self.is_playing = False
        self.btn_play_pause.text = "Phat"
        self.btn_play_pause.icon_type = "play"
        self.history_steps = []
        self.current_step_index = -1
        self.scrub_bar.set_step(0, 1)

        with self.live_lock:
            self.live_info = {
                "algo": "",
                "tents": set(),
                "last_pos": (-1, -1),
                "nodes": 0,
                "backtracks": 0,
                "restarts": 0,
                "heuristic": 0,
                "action": "IDLE",
                "active": False
            }

        if self.puzzle_data:
            self.board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )

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
                "user_stopped": False,
                "algo_name": ""
            }
        except Exception as e:
            print(f"[!] Loi khi nap file {filepath}: {e}")

    # ==================== CƠ CHẾ ĐA LUỒNG & KHẢO SÁT TRỰC TIẾP (LIVE SEARCH) ====================
    def _get_live_step_delay(self) -> float:
        """Tính toán độ trễ (delay giây) cho mỗi bước khảo sát trực quan."""
        raw_delay = self.speeds[self.playback_speed_idx][1]
        if raw_delay == 0:
            return 0.0
        elif raw_delay <= 8:
            return 0.0005
        elif raw_delay <= 25:
            return 0.003
        elif raw_delay <= 80:
            return 0.010
        elif raw_delay <= 180:
            return 0.025
        else:
            return 0.060

    def _on_dfs_step(self, action: str, pos: tuple, tree: tuple, nodes: int, backtracks: int):
        """Callback nhận sự kiện từ thuật toán DFS để cập nhật bàn cờ trực tiếp."""
        with self.live_lock:
            if action == "PLACE":
                self.live_info["tents"].add(pos)
            elif action == "REMOVE":
                self.live_info["tents"].discard(pos)
            self.live_info["last_pos"] = pos
            self.live_info["nodes"] = nodes
            self.live_info["backtracks"] = backtracks
            self.live_info["action"] = action

        delay = self._get_live_step_delay()
        if delay > 0:
            time.sleep(delay)

    def _on_hc_step(self, action: str, state: list, score: int, restarts: int, evaluated: int, changed_pos: tuple):
        """Callback nhận sự kiện từ Hill Climbing để cập nhật bàn cờ trực tiếp."""
        with self.live_lock:
            tent_set = {pos for pos in state if pos is not None and pos != (-1, -1)}
            self.live_info["tents"] = tent_set
            self.live_info["last_pos"] = changed_pos
            self.live_info["heuristic"] = score
            self.live_info["restarts"] = restarts
            self.live_info["nodes"] = evaluated
            self.live_info["action"] = action

        delay = self._get_live_step_delay()
        if delay > 0:
            time.sleep(delay)

    def run_dfs(self):
        if self.is_solving or not self.puzzle_data:
            return

        self.reset_board_state()
        self.is_solving = True
        self.solver_cancel_event = threading.Event()
        self.solving_algo_name = "DFS"
        self.solving_start_time = time.time()
        self.current_algo = "DFS"

        with self.live_lock:
            self.live_info = {
                "algo": "DFS",
                "tents": set(),
                "last_pos": (-1, -1),
                "nodes": 0,
                "backtracks": 0,
                "restarts": 0,
                "heuristic": 0,
                "action": "START",
                "active": True
            }

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
            solver = DFSSolver(
                worker_board,
                max_nodes=None,
                timeout_sec=None,
                cancel_event=self.solver_cancel_event,
                step_callback=self._on_dfs_step
            )
            res = solver.solve()

            self.history_steps = list(worker_board.history_steps)
            self.metrics = {
                "time_sec": res["execution_time_sec"],
                "peak_mem_kb": res["peak_memory_kb"],
                "nodes_or_states": res["nodes_explored"],
                "backtracks_or_restarts": res["backtracks"],
                "solved": res["solved"],
                "timed_out": res.get("timed_out", False),
                "user_stopped": res.get("user_stopped", False),
                "algo_name": "DFS (Depth-First Search)"
            }

            # Lưu vào bộ nhớ đệm (Cache) phục vụ Benchmark tức thì
            if self.current_filepath not in self.puzzle_results_cache:
                self.puzzle_results_cache[self.current_filepath] = {}
            self.puzzle_results_cache[self.current_filepath]["dfs"] = dict(res)

            self.board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            if res["solved"]:
                self.board = worker_board
                self.current_step_index = len(self.history_steps) - 1
                self.scrub_bar.set_step(self.current_step_index, len(self.history_steps))
            elif self.history_steps:
                self.jump_to_step(len(self.history_steps) - 1)
            else:
                self.current_step_index = -1

            self.is_playing = False
            self.btn_play_pause.text = "Phat"
            self.btn_play_pause.icon_type = "play"
        finally:
            with self.live_lock:
                self.live_info["active"] = False
            self.is_solving = False

    def run_hill_climbing(self):
        if self.is_solving or not self.puzzle_data:
            return

        self.reset_board_state()
        self.is_solving = True
        self.solver_cancel_event = threading.Event()
        self.solving_algo_name = "HILL CLIMBING"
        self.solving_start_time = time.time()
        self.current_algo = "HILL_CLIMBING"

        with self.live_lock:
            self.live_info = {
                "algo": "HILL_CLIMBING",
                "tents": set(),
                "last_pos": (-1, -1),
                "nodes": 0,
                "backtracks": 0,
                "restarts": 0,
                "heuristic": 0,
                "action": "START",
                "active": True
            }

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
            solver = SteppedHillClimbingSolver(
                worker_board,
                max_restarts=None,
                max_steps_per_restart=250,
                timeout_sec=None,
                cancel_event=self.solver_cancel_event,
                step_callback=self._on_hc_step
            )
            res = solver.solve_recorded()

            self.history_steps = list(res["steps"])
            self.metrics = {
                "time_sec": res["execution_time_sec"],
                "peak_mem_kb": res["peak_memory_kb"],
                "nodes_or_states": res["states_evaluated"],
                "backtracks_or_restarts": res["restarts"],
                "solved": res["solved"],
                "timed_out": res.get("timed_out", False),
                "user_stopped": res.get("user_stopped", False),
                "algo_name": "Hill Climbing (Random Restart)"
            }

            # Lưu vào bộ nhớ đệm (Cache) phục vụ Benchmark tức thì
            if self.current_filepath not in self.puzzle_results_cache:
                self.puzzle_results_cache[self.current_filepath] = {}
            self.puzzle_results_cache[self.current_filepath]["hc"] = {
                "solved": res["solved"],
                "execution_time_sec": res["execution_time_sec"],
                "peak_memory_kb": res["peak_memory_kb"],
                "states_evaluated": res["states_evaluated"],
                "restarts": res["restarts"],
                "final_heuristic": res.get("final_heuristic", 0),
                "timed_out": res.get("timed_out", False),
                "user_stopped": res.get("user_stopped", False)
            }

            self.board = TentsBoard(
                rows=self.puzzle_data["rows"],
                cols=self.puzzle_data["cols"],
                row_constraints=self.puzzle_data["row_constraints"],
                col_constraints=self.puzzle_data["col_constraints"],
                grid=self.puzzle_data["grid"],
                trees=self.puzzle_data["trees"],
            )
            if self.history_steps:
                self.jump_to_step(len(self.history_steps) - 1)
            else:
                self.current_step_index = -1

            self.is_playing = False
            self.btn_play_pause.text = "Phat"
            self.btn_play_pause.icon_type = "play"
        finally:
            with self.live_lock:
                self.live_info["active"] = False
            self.is_solving = False

    def run_comparison(self, force_rerun: bool = False):
        if self.is_solving or not self.puzzle_data:
            return

        cached = self.puzzle_results_cache.get(self.current_filepath, {})
        # Nếu cả 2 thuật toán đều đã chạy trước đó trên bài toán này và không yêu cầu đo lại:
        if not force_rerun and "dfs" in cached and "hc" in cached:
            self.compare_results = {
                "filename": os.path.basename(self.current_filepath),
                "size": f"{self.puzzle_data['rows']}x{self.puzzle_data['cols']}",
                "trees": len(self.puzzle_data["trees"]),
                "dfs": cached["dfs"],
                "hc": cached["hc"]
            }
            self.show_compare_modal = True
            return

        self.reset_board_state()
        self.is_solving = True
        self.solver_cancel_event = threading.Event()
        self.solving_algo_name = "BENCHMARK (DFS vs HC)"
        self.solving_start_time = time.time()

        self.solver_thread = threading.Thread(target=self._worker_run_compare, args=(force_rerun,), daemon=True)
        self.solver_thread.start()

    def _worker_run_compare(self, force_rerun: bool = False):
        try:
            cached = self.puzzle_results_cache.get(self.current_filepath, {}) if not force_rerun else {}

            # ---------------- Giai đoạn 1: DFS ----------------
            if "dfs" in cached:
                dfs_res = cached["dfs"]
            else:
                self.solving_algo_name = "BENCHMARK: 1/2 DFS"
                with self.live_lock:
                    self.live_info = {
                        "algo": "DFS",
                        "tents": set(),
                        "last_pos": (-1, -1),
                        "nodes": 0,
                        "backtracks": 0,
                        "restarts": 0,
                        "heuristic": 0,
                        "action": "START",
                        "active": True
                    }
                board_dfs = TentsBoard(
                    self.puzzle_data["rows"], self.puzzle_data["cols"],
                    self.puzzle_data["row_constraints"], self.puzzle_data["col_constraints"],
                    self.puzzle_data["grid"], self.puzzle_data["trees"]
                )
                dfs_solver = DFSSolver(
                    board_dfs,
                    max_nodes=None,
                    timeout_sec=None,
                    cancel_event=self.solver_cancel_event,
                    step_callback=self._on_dfs_step
                )
                dfs_res = dfs_solver.solve()
                if self.current_filepath not in self.puzzle_results_cache:
                    self.puzzle_results_cache[self.current_filepath] = {}
                self.puzzle_results_cache[self.current_filepath]["dfs"] = dict(dfs_res)

            # Nếu người dùng bấm Dừng [ESC] ngay trong giai đoạn DFS
            if self.solver_cancel_event and self.solver_cancel_event.is_set():
                hc_res = {
                    "solved": False,
                    "timed_out": False,
                    "user_stopped": True,
                    "execution_time_sec": 0.0,
                    "peak_memory_kb": 0.0,
                    "states_evaluated": 0,
                    "restarts": 0,
                    "final_heuristic": "N/A"
                }
            else:
                # ---------------- Giai đoạn 2: Hill Climbing ----------------
                if "hc" in cached:
                    hc_res = cached["hc"]
                else:
                    num_trees = len(self.puzzle_data["trees"])
                    # Định mức giới hạn thích ứng cho Hill Climbing khi Benchmark
                    if num_trees <= 12:
                        hc_timeout = 10.0
                        hc_max_restarts = 100
                    elif num_trees <= 25:
                        hc_timeout = 7.0
                        hc_max_restarts = 50
                    else:
                        # Bản đồ lớn (15x15, 20x20...) không gian tìm kiếm 4^N siêu khổng lồ
                        hc_timeout = 5.0
                        hc_max_restarts = 20

                    self.solving_algo_name = f"BENCHMARK: 2/2 HC (Toi da {int(hc_timeout)}s)"
                    with self.live_lock:
                        self.live_info = {
                            "algo": "HILL_CLIMBING",
                            "tents": set(),
                            "last_pos": (-1, -1),
                            "nodes": 0,
                            "backtracks": 0,
                            "restarts": 0,
                            "heuristic": 0,
                            "action": "START",
                            "active": True
                        }
                    board_hc = TentsBoard(
                        self.puzzle_data["rows"], self.puzzle_data["cols"],
                        self.puzzle_data["row_constraints"], self.puzzle_data["col_constraints"],
                        self.puzzle_data["grid"], self.puzzle_data["trees"]
                    )
                    hc_solver = HillClimbingSolver(
                        board_hc,
                        max_restarts=hc_max_restarts,
                        max_steps_per_restart=250,
                        timeout_sec=hc_timeout,
                        cancel_event=self.solver_cancel_event,
                        step_callback=self._on_hc_step
                    )
                    hc_res = hc_solver.solve()
                    if self.current_filepath not in self.puzzle_results_cache:
                        self.puzzle_results_cache[self.current_filepath] = {}
                    self.puzzle_results_cache[self.current_filepath]["hc"] = dict(hc_res)

            self.compare_results = {
                "filename": os.path.basename(self.current_filepath),
                "size": f"{self.puzzle_data['rows']}x{self.puzzle_data['cols']}",
                "trees": len(self.puzzle_data["trees"]),
                "dfs": dfs_res,
                "hc": hc_res
            }
            self.show_compare_modal = True
        finally:
            with self.live_lock:
                self.live_info["active"] = False
            self.is_solving = False

    def export_benchmark_file(self):
        if not self.compare_results:
            return

        c = self.compare_results
        dfs = c["dfs"]
        hc = c["hc"]

        base_map_name = os.path.splitext(c['filename'])[0]
        timestamp_str = time.strftime('%Y%m%d_%H%M%S')
        suggested_name = f"benchmark_{base_map_name}_{timestamp_str}.txt"

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        report_path = filedialog.asksaveasfilename(
            title="Luu file Bao cao Thuc nghiem",
            initialdir=SRC_DIR,
            initialfile=suggested_name,
            defaultextension=".txt",
            filetypes=[("Text files (*.txt)", "*.txt"), ("All files (*.*)", "*.*")]
        )
        root.destroy()

        if not report_path:
            return

        dfs_status_str = 'CO (Thanh cong)' if dfs['solved'] else ('DA DUNG (Nguoi dung dung)' if dfs.get('user_stopped') else 'KHONG')
        hc_status_str = 'CO (Thanh cong)' if hc['solved'] else ('DA DUNG (Nguoi dung dung)' if hc.get('user_stopped') else ('KHONG (Het thoi gian thu)' if hc.get('timed_out') else 'KHONG (Cuc tieu dia phuong)'))

        content = f"""================================================================================
BAO CAO THUC NGHIEM DOI SANH THUAT TOAN - PUZZLE TENTS & TREES
================================================================================
Bai toan kiem thu      : {c['filename']}
Kich thuoc luoi co     : {c['size']}
Tong so cay / so leu   : {c['trees']} cay
Thoi diem thuc hien    : {time.strftime('%Y-%m-%d %H:%M:%S')}
--------------------------------------------------------------------------------
THONG SO DO DAC                    DFS (Constraint / MRV)     Hill Climbing (Local Search)
--------------------------------------------------------------------------------
Trang thai giai thanh cong         {dfs_status_str:<26} {hc_status_str}
Thoi gian thuc thi (giay)          {dfs['execution_time_sec']:.6f} s                 {hc['execution_time_sec']:.6f} s
Bo nho RAM dinh (KB)               {dfs['peak_memory_kb']:.2f} KB                   {hc['peak_memory_kb']:.2f} KB
So node / trang thai da duyet      {dfs['nodes_explored']} nodes                    {hc['states_evaluated']} states
So lan quay lui / Restart          {dfs['backtracks']} lan quay lui               {hc['restarts']} lan restart
Gia tri xung dot Heuristic h(S)    0 (Toi uu)                 {hc['final_heuristic']} ({'Toi uu' if hc.get('final_heuristic')==0 else 'Cuc tieu dia phuong'})
--------------------------------------------------------------------------------
DANH GIA VA NHAN XET:
1. Thuat toan DFS ket hop Backtracking, Forward Checking va Heuristic MRV (Minimum
   Remaining Values) bao dam tinh day du (Completeness), cat tia nhanh chong khong
   gian loi giai va tim ra nghiem cuc ky hieu qua tren ca cac luoi lon (15x15, 20x20).
2. Thuat toan Hill Climbing dua tren ham Heuristic dem xung dot h(S) ket hop Random
   Restart giup giai phong bay cuc tieu dia phuong, toc do hoi tu nhanh tren cac
   bai toan vua va nho, nhung bi gioi han boi khong gian tim kiem bung no (4^N) tren
   cac luoi lon (Local Search bi bay o cuc tieu dia phuong nong).
================================================================================
"""
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(content)
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
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

    # ==================== RENDERING PIPELINE ====================
    def draw(self):
        self.screen.fill(COLOR_BG)

        self._draw_header()
        self._draw_board()
        self._draw_controls()

        if self.show_speed_menu:
            self._draw_speed_menu()

        if self.show_compare_modal and self.compare_results:
            self._draw_compare_modal()

        # Hiển thị thanh HUD trực tiếp góc trên bàn cờ khi đang giải
        if self.is_solving:
            self._draw_live_search_hud()

        pygame.display.flip()

    def _draw_header(self):
        header_rect = pygame.Rect(0, 0, WINDOW_WIDTH, 56)
        pygame.draw.rect(self.screen, COLOR_PANEL, header_rect)
        pygame.draw.line(self.screen, COLOR_CARD_BORDER, (0, 56), (WINDOW_WIDTH, 56), 1)

        title_surf = self.font_title.render("TENTS & TREES SEARCH ALGORITHMS (DFS & HC)", True, COLOR_TEXT_WHITE)
        self.screen.blit(title_surf, (35, 16))

        # Badge trạng thái hệ thống góc phải (thay thế cho Chế độ AI (none))
        if self.is_solving:
            elapsed = time.time() - self.solving_start_time
            mins = int(elapsed) // 60
            secs = elapsed % 60
            status_text = f"DANG TIM KIEM: {self.solving_algo_name} ({mins:02d}:{secs:04.1f}s)"
            status_bg = (180, 95, 20)
            status_border = (255, 167, 38)
            text_color = COLOR_TEXT_WHITE
        elif self.metrics["algo_name"]:
            if self.metrics["solved"]:
                status_text = f"DA GIAI XONG: {self.current_algo}"
                status_bg = (24, 90, 50)
                status_border = COLOR_SUCCESS
                text_color = COLOR_TEXT_WHITE
            elif self.metrics.get("user_stopped"):
                status_text = f"DA DUNG (CHUA TIM THAY): {self.current_algo}"
                status_bg = (150, 60, 20)
                status_border = (245, 158, 11)
                text_color = COLOR_TEXT_WHITE
            elif self.metrics.get("timed_out"):
                status_text = f"HET GIO (TIMEOUT): {self.current_algo}"
                status_bg = (120, 30, 30)
                status_border = COLOR_DANGER
                text_color = COLOR_TEXT_WHITE
            else:
                status_text = f"KHONG TIM THAY LOI GIAI: {self.current_algo}"
                status_bg = (120, 30, 30)
                status_border = COLOR_DANGER
                text_color = COLOR_TEXT_WHITE
        else:
            status_text = "TRANG THAI: SAN SANG"
            status_bg = (30, 48, 80)
            status_border = (75, 120, 195)
            text_color = (220, 240, 255)

        badge_surf = self.font_badge.render(status_text, True, text_color)
        badge_w = badge_surf.get_width() + 24
        badge_h = 32
        badge_rect = pygame.Rect(WINDOW_WIDTH - 35 - badge_w, 12, badge_w, badge_h)

        pygame.draw.rect(self.screen, status_bg, badge_rect, border_radius=16)
        pygame.draw.rect(self.screen, status_border, badge_rect, 1, border_radius=16)
        self.screen.blit(badge_surf, badge_surf.get_rect(center=badge_rect.center))

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

        if self.is_solving and self.live_info.get("active"):
            active_grid = [row[:] for row in self.puzzle_data["grid"]]
            with self.live_lock:
                live_tents = list(self.live_info.get("tents", set()))
                last_changed_pos = self.live_info.get("last_pos", (-1, -1))
            for tr, tc in live_tents:
                if 0 <= tr < rows and 0 <= tc < cols:
                    active_grid[tr][tc] = TentsBoard.TENT
        else:
            active_grid = self.board.grid
            last_changed_pos = (-1, -1)
            if 0 <= self.current_step_index < len(self.history_steps):
                step = self.history_steps[self.current_step_index]
                if "pos" in step:
                    last_changed_pos = step["pos"]
                elif "new_pos" in step:
                    last_changed_pos = step["new_pos"]

        curr_row_counts = [0] * rows
        curr_col_counts = [0] * cols

        for r in range(rows):
            for c in range(cols):
                if active_grid[r][c] == TentsBoard.TENT:
                    curr_row_counts[r] += 1
                    curr_col_counts[c] += 1

        clue_font_size = max(13, min(24, int(cell_size * 0.46)))
        font_clue = pygame.font.SysFont(["Segoe UI", "Tahoma", "Arial"], clue_font_size, bold=True)

        # Cột chỉ số trên (Column Constraints)
        for c in range(cols):
            cx = start_x + c * cell_size
            cy = start_y - cell_size + 4
            clue = self.puzzle_data["col_constraints"][c]
            curr_c = curr_col_counts[c]

            if curr_c == clue:
                badge_bg = (34, 139, 34)
                badge_border = (46, 204, 113)
            elif curr_c > clue:
                badge_bg = (192, 57, 43)
                badge_border = (235, 87, 87)
            else:
                badge_bg = (38, 50, 75)
                badge_border = (80, 105, 155)

            badge_rect = pygame.Rect(
                cx + max(1, cell_size // 10),
                cy,
                max(16, cell_size - max(2, cell_size // 5)),
                max(16, cell_size - max(2, cell_size // 5))
            )
            pygame.draw.rect(self.screen, badge_bg, badge_rect, border_radius=max(3, cell_size // 10))
            pygame.draw.rect(self.screen, badge_border, badge_rect, 1, border_radius=max(3, cell_size // 10))
            clue_surf = font_clue.render(str(clue), True, COLOR_TEXT_WHITE)
            self.screen.blit(clue_surf, clue_surf.get_rect(center=badge_rect.center))

        # Hàng chỉ số trái (Row Constraints)
        for r in range(rows):
            cx = start_x - cell_size + 4
            cy = start_y + r * cell_size
            clue = self.puzzle_data["row_constraints"][r]
            curr_r = curr_row_counts[r]

            if curr_r == clue:
                badge_bg = (34, 139, 34)
                badge_border = (46, 204, 113)
            elif curr_r > clue:
                badge_bg = (192, 57, 43)
                badge_border = (235, 87, 87)
            else:
                badge_bg = (38, 50, 75)
                badge_border = (80, 105, 155)

            badge_rect = pygame.Rect(
                cx,
                cy + max(1, cell_size // 10),
                max(16, cell_size - max(2, cell_size // 5)),
                max(16, cell_size - max(2, cell_size // 5))
            )
            pygame.draw.rect(self.screen, badge_bg, badge_rect, border_radius=max(3, cell_size // 10))
            pygame.draw.rect(self.screen, badge_border, badge_rect, 1, border_radius=max(3, cell_size // 10))
            clue_surf = font_clue.render(str(clue), True, COLOR_TEXT_WHITE)
            self.screen.blit(clue_surf, clue_surf.get_rect(center=badge_rect.center))

        # Vẽ các ô cờ
        mouse_pos = pygame.mouse.get_pos()

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
            is_active = (btn.text == "Tat ca" and self.active_category == "ALL") or \
                       (btn.text == self.active_category) or \
                       (btn.text == "Special" and self.active_category == "SPECIAL")
            if is_active:
                btn.bg_color = (0, 140, 220)
                btn.hover_color = (30, 160, 240)
                btn.text_color = COLOR_TEXT_WHITE
            else:
                btn.bg_color = (36, 46, 70)
                btn.hover_color = (50, 65, 95)
                btn.text_color = (215, 230, 255)
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

        # CARD 2: Lựa chọn thuật toán AI
        card2_rect = pygame.Rect(panel_x, 193, panel_w, 86)
        pygame.draw.rect(self.screen, COLOR_PANEL, card2_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card2_rect, 1, border_radius=8)

        card2_title = self.font_bold.render("LUA CHON THUAT TOAN TIM KIEM", True, COLOR_TEXT_WHITE)
        self.screen.blit(card2_title, (panel_x + 15, 203))

        self.btn_run_dfs.draw(self.screen, self.font_bold)
        self.btn_run_hc.draw(self.screen, self.font_bold)
        self.btn_compare.draw(self.screen, self.font_bold)

        # CARD 3: Step-by-Step
        card3_rect = pygame.Rect(panel_x, 289, panel_w, 145)
        pygame.draw.rect(self.screen, COLOR_PANEL, card3_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card3_rect, 1, border_radius=8)

        title3 = self.font_bold.render("DIEU KHIEN HOAT CANH (STEP-BY-STEP)", True, COLOR_TEXT_WHITE)
        self.screen.blit(title3, (panel_x + 15, 301))

        total_s = len(self.history_steps)
        curr_s = max(0, self.current_step_index + 1)
        step_counter_text = f"Buoc: {curr_s} / {total_s}"
        self.screen.blit(self.font_medium.render(step_counter_text, True, COLOR_TEXT_GOLD), (panel_x + 380, 301))

        self.btn_step_first.draw(self.screen, self.font_bold)
        self.btn_step_prev.draw(self.screen, self.font_bold)
        self.btn_play_pause.draw(self.screen, self.font_bold)
        self.btn_step_next.draw(self.screen, self.font_bold)
        self.btn_step_last.draw(self.screen, self.font_bold)
        self.btn_speed.draw(self.screen, self.font_bold)
        self.btn_clear_step.draw(self.screen, self.font_bold)

        self.scrub_bar.draw(self.screen, curr_s, total_s)

        log_msg = "San sang. Nhan 'Chay DFS' hoac 'Hill Climbing' de quan sat giai thuat."
        if self.is_solving:
            with self.live_lock:
                act = self.live_info.get("action", "")
                lp = self.live_info.get("last_pos", (-1, -1))
            if "DFS" in self.solving_algo_name:
                if act == "PLACE":
                    log_msg = f"[MO DUONG] Thu dat leu tai hang {lp[0]}, cot {lp[1]}"
                elif act == "REMOVE":
                    log_msg = f"[QUAY LUI] Rut leu tai hang {lp[0]}, cot {lp[1]} (Vao ngo cut)"
                else:
                    log_msg = "Dang do duong theo chieu sau (DFS)..."
            else:
                if act == "MOVE":
                    log_msg = f"[HC DOI LEU] Chuyen leu sang vi tri {lp}"
                elif act == "SIDEWAYS":
                    log_msg = f"[HC DI NGANG] Buoc di ngang sang {lp}"
                elif act == "RESTART":
                    log_msg = f"[HC RESTART] Khoi tao lai ngau nhien khong gian trang thai"
                else:
                    log_msg = "Dang toi uu ham xung dot Heuristic..."
        elif self.metrics.get("user_stopped"):
            log_msg = f"Nguoi dung da dung thuat toan {self.metrics['algo_name']}! Chua tim thay loi giai."
        elif 0 <= self.current_step_index < len(self.history_steps):
            st = self.history_steps[self.current_step_index]
            if "log" in st:
                log_msg = st["log"]
            elif st.get("action") == "PLACE":
                log_msg = f"[DAT LEU] tai hang {st['pos'][0]}, cot {st['pos'][1]} cho Cay tai {st['tree']}"
            elif st.get("action") == "REMOVE":
                log_msg = f"[QUAY LUI] Rut leu tai hang {st['pos'][0]}, cot {st['pos'][1]} (Vao ngo cut)"

        log_surf = self.font_small.render(f"> {log_msg}", True, (215, 235, 255))
        self.screen.blit(log_surf, (panel_x + 15, 402))

        # CARD 4: Benchmark HUD
        card4_rect = pygame.Rect(panel_x, 444, panel_w, 270)
        pygame.draw.rect(self.screen, COLOR_PANEL, card4_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card4_rect, 1, border_radius=8)

        title4 = self.font_bold.render("SO LIEU THUC NGHIEM DO DAC (BENCHMARK HUD)", True, COLOR_TEXT_WHITE)
        self.screen.blit(title4, (panel_x + 15, 456))

        if self.is_solving:
            elapsed = time.time() - self.solving_start_time
            status_str = f"DANG TIM KIEM TRUC TIEP: {self.solving_algo_name}..."
            status_col = (255, 175, 55)
            with self.live_lock:
                live_nodes = self.live_info.get("nodes", 0)
                live_bts = self.live_info.get("backtracks", 0) if "DFS" in self.solving_algo_name else self.live_info.get("restarts", 0)
            metric_cards = [
                ("THOI GIAN DANG CHAY", f"{elapsed:.3f} s", (41, 128, 185)),
                ("BO NHO RAM DINH", "Dang ghi nhan...", (142, 68, 173)),
                ("NODE / TRANG THAI DUYET", f"{live_nodes:,}", (39, 174, 96)),
                ("QUAY LUI / RESTARTS", f"{live_bts:,}", (211, 84, 0))
            ]
        elif self.metrics["algo_name"]:
            if self.metrics["solved"]:
                status_str = f"TIM THAY LOI GIAI ({self.metrics['algo_name']})"
                status_col = COLOR_SUCCESS
            elif self.metrics.get("user_stopped"):
                status_str = f"DA DUNG BOI NGUOI DUNG - CHUA TIM THAY LOI GIAI ({self.metrics['algo_name']})"
                status_col = (255, 175, 55)
            elif self.metrics.get("timed_out"):
                status_str = f"HET GIO TIM KIEM (TIMEOUT) - DUNG AN TOAN ({self.metrics['algo_name']})"
                status_col = COLOR_DANGER
            else:
                status_str = f"KHONG TIM THAY LOI GIAI ({self.metrics['algo_name']})"
                status_col = COLOR_DANGER

            metric_cards = [
                ("THOI GIAN THUC THI", f"{self.metrics['time_sec']:.5f} s", (41, 128, 185)),
                ("BO NHO RAM DINH", f"{self.metrics['peak_mem_kb']:.2f} KB", (142, 68, 173)),
                ("NODE / TRANG THAI DUYET", f"{self.metrics['nodes_or_states']:,}", (39, 174, 96)),
                ("QUAY LUI / RESTARTS", f"{self.metrics['backtracks_or_restarts']:,}", (211, 84, 0))
            ]
        else:
            status_str = "TRANG THAI: CHUA CHAY GIAI THUAT"
            status_col = (180, 215, 255)
            metric_cards = [
                ("THOI GIAN THUC THI", "0.00000 s", (41, 128, 185)),
                ("BO NHO RAM DINH", "0.00 KB", (142, 68, 173)),
                ("NODE / TRANG THAI DUYET", "0", (39, 174, 96)),
                ("QUAY LUI / RESTARTS", "0", (211, 84, 0))
            ]

        self.screen.blit(self.font_medium.render(status_str, True, status_col), (panel_x + 15, 480))

        bx, by = panel_x + 15, 508
        bw, bh = 235, 54

        for i, (m_title, m_val, m_color) in enumerate(metric_cards):
            col = i % 2
            row = i // 2
            x = bx + col * (bw + 15)
            y = by + row * (bh + 10)

            m_rect = pygame.Rect(x, y, bw, bh)
            pygame.draw.rect(self.screen, COLOR_CARD, m_rect, border_radius=6)
            pygame.draw.rect(self.screen, COLOR_CARD_BORDER, m_rect, 1, border_radius=6)
            pygame.draw.rect(self.screen, m_color, (x, y, 4, bh), border_top_left_radius=6, border_bottom_left_radius=6)

            self.screen.blit(self.font_small.render(m_title, True, COLOR_TEXT_LABEL), (x + 12, y + 8))
            self.screen.blit(self.font_bold.render(m_val, True, COLOR_TEXT_WHITE), (x + 12, y + 27))

        tip_text1 = "Phim tat: [Space] Phat / Dung  |  [Mui ten] Tung buoc  |  [R] Dat lai"
        tip_text2 = "Goi y: Nhan 'Benchmark (DFS vs HC)' de xem bang danh gia chi tiet!"
        self.screen.blit(self.font_small.render(tip_text1, True, (185, 215, 255)), (panel_x + 15, 642))
        self.screen.blit(self.font_small.render(tip_text2, True, (140, 175, 220)), (panel_x + 15, 665))

    def _get_speed_menu_rects(self):
        bx, by, bw, bh = self.btn_speed.rect
        menu_w = 158
        menu_x = bx + (bw - menu_w) // 2
        menu_y = by + bh + 4
        item_h = 28
        menu_h = len(self.speeds) * item_h + 8
        menu_rect = pygame.Rect(menu_x, menu_y, menu_w, menu_h)
        item_rects = [
            pygame.Rect(menu_x + 4, menu_y + 4 + i * item_h, menu_w - 8, item_h - 2)
            for i in range(len(self.speeds))
        ]
        return menu_rect, item_rects

    def _draw_speed_menu(self):
        menu_rect, item_rects = self._get_speed_menu_rects()
        mouse_pos = pygame.mouse.get_pos()

        # Bóng đổ (Drop Shadow)
        shadow_rect = menu_rect.move(2, 4)
        pygame.draw.rect(self.screen, (10, 14, 22), shadow_rect, border_radius=8)

        # Hộp tùy chọn (Option Box Background & Border)
        pygame.draw.rect(self.screen, (24, 33, 52), menu_rect, border_radius=8)
        pygame.draw.rect(self.screen, (85, 120, 180), menu_rect, 1, border_radius=8)

        for i, (label, delay, desc) in enumerate(self.speeds):
            item_rect = item_rects[i]
            is_hovered = item_rect.collidepoint(mouse_pos)
            is_selected = (i == self.playback_speed_idx)

            if is_hovered:
                pygame.draw.rect(self.screen, (48, 70, 110), item_rect, border_radius=5)
            elif is_selected:
                pygame.draw.rect(self.screen, (32, 50, 80), item_rect, border_radius=5)
                pygame.draw.rect(self.screen, (60, 100, 155), item_rect, 1, border_radius=5)

            if is_selected:
                text_col = COLOR_COMPARE
            elif is_hovered:
                text_col = COLOR_TEXT_WHITE
            else:
                text_col = (215, 230, 255)

            txt_surf = self.font_small.render(desc, True, text_col)
            self.screen.blit(txt_surf, (item_rect.x + 10, item_rect.centery - txt_surf.get_height() // 2))

            if is_selected:
                pygame.draw.circle(self.screen, COLOR_COMPARE, (item_rect.right - 12, item_rect.centery), 3)

    def _draw_live_search_hud(self):
        """Vẽ thanh HUD hiển thị tiến trình mò đường và đồng hồ bấm giờ trực tiếp ở góc trên bàn cờ."""
        hud_x = 45
        hud_y = 80
        hud_w = 670
        hud_h = 38
        hud_rect = pygame.Rect(hud_x, hud_y, hud_w, hud_h)

        # Nền HUD đen xanh mờ thanh lịch với viền phát sáng
        pygame.draw.rect(self.screen, (18, 25, 40), hud_rect, border_radius=8)
        pygame.draw.rect(self.screen, (0, 184, 212), hud_rect, 1, border_radius=8)

        # Chấm tròn nhấp nháy báo hiệu đang chạy trực tiếp (Live Pulse Indicator)
        elapsed = time.time() - self.solving_start_time
        pulse = (math.sin(elapsed * 7) + 1) / 2.0
        dot_alpha = int(140 + 115 * pulse)
        dot_surf = pygame.Surface((14, 14), pygame.SRCALPHA)
        dot_color = (255, 60, 60, dot_alpha) if "DFS" in self.solving_algo_name else (186, 104, 200, dot_alpha)
        pygame.draw.circle(dot_surf, dot_color, (7, 7), 5)
        self.screen.blit(dot_surf, (hud_x + 10, hud_y + (hud_h - 14) // 2))

        # Tiêu đề thuật toán đang mò đường
        algo_title = f"MO DUONG: {self.solving_algo_name}"
        title_surf = self.font_bold.render(algo_title, True, COLOR_TEXT_WHITE)
        self.screen.blit(title_surf, (hud_x + 28, hud_y + 10))

        # Thông số tìm kiếm trực tiếp ở giữa thanh
        with self.live_lock:
            nodes = self.live_info.get("nodes", 0)
            backtracks = self.live_info.get("backtracks", 0)
            restarts = self.live_info.get("restarts", 0)
            heuristic = self.live_info.get("heuristic", 0)

        if "DFS" in self.solving_algo_name:
            stat_text = f"Nodes: {nodes:,}  |  Quay lui: {backtracks:,}"
        else:
            stat_text = f"Restart #{restarts}  |  h(S): {heuristic}  |  Xet: {nodes:,}"

        stat_surf = self.font_medium.render(stat_text, True, COLOR_TEXT_GOLD)
        self.screen.blit(stat_surf, (hud_x + 220, hud_y + 10))

        # Đồng hồ đếm thời gian thực góc phải (Live Timer)
        mins = int(elapsed) // 60
        secs = elapsed % 60
        timer_text = f"{mins:02d}:{secs:04.1f}s"
        timer_surf = self.font_bold.render(timer_text, True, (0, 230, 255))
        timer_icon = self.font_small.render("TIME", True, (140, 180, 220))
        self.screen.blit(timer_icon, (hud_x + hud_w - 200, hud_y + 12))
        self.screen.blit(timer_surf, (hud_x + hud_w - 165, hud_y + 10))

        # Nút Dừng thuật toán [ESC] nổi bật màu đỏ
        self.btn_stop_solving.rect.x = hud_x + hud_w - 95
        self.btn_stop_solving.rect.y = hud_y + 4
        self.btn_stop_solving.rect.width = 90
        self.btn_stop_solving.rect.height = 30
        self.btn_stop_solving.text = "Dung [ESC]"
        self.btn_stop_solving.draw(self.screen, self.font_bold)

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
        self.screen.blit(self.font_bold.render("THONG SO DO DAC", True, COLOR_TEXT_WHITE), (table_x + 20, table_y + 11))
        self.screen.blit(self.font_bold.render("DFS (BLIND SEARCH)", True, COLOR_DFS), (table_x + 320, table_y + 11))
        self.screen.blit(self.font_bold.render("HILL CLIMBING (HEURISTIC)", True, COLOR_HC), (table_x + 560, table_y + 11))

        dfs_status = "CO (Thanh cong)" if dfs["solved"] else ("DA DUNG (Nguoi dung dung)" if dfs.get("user_stopped") else "KHONG (Chua tim thay)")
        hc_status = "CO (Thanh cong)" if hc["solved"] else ("DA DUNG (Nguoi dung dung)" if hc.get("user_stopped") else ("KHONG (Het thoi gian thu)" if hc.get("timed_out") else "KHONG (Cuc tieu dia phuong)"))

        hc_h = hc.get("final_heuristic", "N/A")
        if hc["solved"] or hc_h == 0:
            hc_h_str = "0 (Toi uu)"
        elif hc_h == "N/A":
            hc_h_str = "N/A"
        else:
            hc_h_str = f"{hc_h} (Cuc tieu dia phuong)"

        rows_data = [
            ("Trang thai giai thanh cong", dfs_status, hc_status),
            ("Thoi gian thuc thi (giay)", f"{dfs['execution_time_sec']:.6f} s", f"{hc['execution_time_sec']:.6f} s"),
            ("Bo nho RAM dinh (KB)", f"{dfs['peak_memory_kb']:.2f} KB", f"{hc['peak_memory_kb']:.2f} KB"),
            ("Khong gian da duyet", f"{dfs['nodes_explored']} nodes", f"{hc['states_evaluated']} states"),
            ("So lan Quay lui / Restarts", f"{dfs['backtracks']} lan quay lui", f"{hc['restarts']} lan restart"),
            ("Diem xung dot Heuristic h(S)", "0 (Toi uu)" if dfs["solved"] else ("Chua xac dinh" if dfs.get("user_stopped") else "Khong giai duoc"), hc_h_str),
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
        note1 = "- DFS: Duyet cay tim kiem voi Cat tia (Pruning) & Heuristic MRV; giai quyet triet de ca luoi nho lan sieu lon."
        note2 = "- Hill Climbing: Heuristic Local Search hieu qua o luoi nho/vua; de bi ket cuc tieu dia phuong tren luoi lon (4^N trang thai)."
        self.screen.blit(self.font_small.render(note1, True, COLOR_TEXT_LABEL), (table_x + 15, note_y + 30))
        self.screen.blit(self.font_small.render(note2, True, COLOR_TEXT_LABEL), (table_x + 15, note_y + 48))

        self.btn_modal_rerun.rect.x = table_x + 15
        self.btn_modal_rerun.rect.y = modal_y + modal_h - 55
        self.btn_modal_rerun.draw(self.screen, self.font_bold)

        self.btn_modal_export.rect.x = table_x + 470
        self.btn_modal_export.rect.y = modal_y + modal_h - 55
        self.btn_modal_export.draw(self.screen, self.font_bold)

        self.btn_modal_close.rect.x = table_x + 665
        self.btn_modal_close.rect.y = modal_y + modal_h - 55
        self.btn_modal_close.draw(self.screen, self.font_bold)

    # ==================== VÒNG LẶP SỰ KIỆN CHÍNH ====================
    def run(self):
        running = True

        while running:
            current_time = pygame.time.get_ticks()
            mouse_pos = pygame.mouse.get_pos()

            # Hover
            if self.show_compare_modal:
                self.btn_modal_rerun.check_hover(mouse_pos)
                self.btn_modal_export.check_hover(mouse_pos)
                self.btn_modal_close.check_hover(mouse_pos)
            elif self.is_solving:
                self.btn_stop_solving.check_hover(mouse_pos)
                self.btn_speed.check_hover(mouse_pos)
            else:
                for btn in [
                    self.btn_prev_puzzle, self.btn_next_puzzle, self.btn_random_puzzle,
                    self.btn_browse, self.btn_reset_board, self.btn_run_dfs,
                    self.btn_run_hc, self.btn_compare,
                    self.btn_step_first, self.btn_step_prev, self.btn_play_pause,
                    self.btn_step_next, self.btn_step_last, self.btn_speed,
                    self.btn_clear_step
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
                        elif self.btn_modal_rerun.rect.collidepoint(event.pos):
                            self.show_compare_modal = False
                            if self.current_filepath in self.puzzle_results_cache:
                                del self.puzzle_results_cache[self.current_filepath]
                            self.run_comparison(force_rerun=True)
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.show_compare_modal = False
                    continue

                if self.is_solving:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.btn_stop_solving.is_clicked(event.pos, event.type):
                            self.request_stop_solving()
                            continue
                        elif self.show_speed_menu:
                            menu_rect, item_rects = self._get_speed_menu_rects()
                            handled = False
                            for i, irect in enumerate(item_rects):
                                if irect.collidepoint(event.pos):
                                    self.playback_speed_idx = i
                                    self.show_speed_menu = False
                                    self.btn_speed.text = f"{self.speeds[i][0]} ▼"
                                    handled = True
                                    break
                            if not handled:
                                self.show_speed_menu = False
                                self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} ▼"
                            continue
                        elif self.btn_speed.is_clicked(event.pos, event.type):
                            self.show_speed_menu = not self.show_speed_menu
                            self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} {'▲' if self.show_speed_menu else '▼'}"
                            continue
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            if self.show_speed_menu:
                                self.show_speed_menu = False
                                self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} ▼"
                            else:
                                self.request_stop_solving()
                            continue
                        elif event.key == pygame.K_SPACE:
                            self.request_stop_solving()
                            continue
                    continue

                scrub_step = self.scrub_bar.handle_event(event, len(self.history_steps))
                if scrub_step is not None:
                    self.is_playing = False
                    self.btn_play_pause.text = "Phat"
                    self.btn_play_pause.icon_type = "play"
                    self.jump_to_step(scrub_step)

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.show_speed_menu:
                        menu_rect, item_rects = self._get_speed_menu_rects()
                        handled_speed_option = False
                        for i, irect in enumerate(item_rects):
                            if irect.collidepoint(event.pos):
                                self.playback_speed_idx = i
                                self.show_speed_menu = False
                                self.btn_speed.text = f"{self.speeds[i][0]} ▼"
                                handled_speed_option = True
                                break
                        if handled_speed_option:
                            continue
                        elif self.btn_speed.rect.collidepoint(event.pos):
                            self.show_speed_menu = False
                            self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} ▼"
                            continue
                        else:
                            self.show_speed_menu = False
                            self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} ▼"

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
                        self.show_speed_menu = not self.show_speed_menu
                        self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} {'▲' if self.show_speed_menu else '▼'}"

                    elif self.btn_clear_step.is_clicked(event.pos, event.type):
                        self.load_puzzle(self.current_filepath)

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.show_speed_menu:
                            self.show_speed_menu = False
                            self.btn_speed.text = f"{self.speeds[self.playback_speed_idx][0]} ▼"
                    elif event.key == pygame.K_SPACE:
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
