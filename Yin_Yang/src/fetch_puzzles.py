"""
MODULE: fetch_puzzles.py
MỤC ĐÍCH: Trích xuất và giải mã biến JavaScript 'task' từ puzzle-yin-yang.com,
          lưu thành các file .txt theo định dạng chuẩn ma trận trực quan
          cho bài toán Yin-Yang (Âm Dương).
"""

import os
import sys
import re
import time
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==============================================================================
# 1. CẤU HÌNH THƯ MỤC VÀ DANH MỤC CÂU ĐỐ
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))       # Thư mục Yin_Yang/src/
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "inputs")         # Thư mục Yin_Yang/inputs/
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://www.puzzle-yin-yang.com"

# Tra cứu tham số 'size' chính xác từ puzzle-yin-yang.com:
# size="" là 6x6 Easy, size="1" là 6x6 Normal, size="2" là 6x6 Hard, ...
CATEGORY_TARGETS = {
    "6x6_easy":        {"size": "",   "count": 8},
    "6x6_normal":      {"size": "1",  "count": 8},
    "6x6_hard":        {"size": "2",  "count": 8},
    "10x10_easy":      {"size": "3",  "count": 6},
    "10x10_normal":    {"size": "4",  "count": 6},
    "10x10_hard":      {"size": "5",  "count": 6},
    "15x15_easy":      {"size": "6",  "count": 5},
    "15x15_normal":    {"size": "7",  "count": 5},
    "15x15_hard":      {"size": "8",  "count": 5},
    "special_daily":   {"size": "15", "count": 1},
    "special_weekly":  {"size": "16", "count": 1},
    "special_monthly": {"size": "17", "count": 1}
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.puzzle-yin-yang.com/"
}

# ==============================================================================
# 2. GIẢI MÃ MA TRẬN TỪ BIẾN TASK
# ==============================================================================
def decode_grid(task_str: str, rows: int, cols: int):
    """
    Giải mã chuỗi task của puzzle-yin-yang.com thành ma trận 2D:
    - 'W': Ô tròn trắng (White circle)
    - 'B': Ô tròn đen (Black circle)
    - Ký tự chữ thường 'a'..'z': Khoảng trống gồm (ord(ch) - 96) ô '.' liên tiếp
    """
    total_cells = rows * cols
    cells = []

    for ch in task_str:
        if ch == 'W':
            cells.append('W')
        elif ch == 'B':
            cells.append('B')
        elif 'a' <= ch <= 'z':
            gap = ord(ch) - ord('a') + 1
            cells.extend(['.'] * gap)
        else:
            # Bỏ qua ký tự phân tách nếu có
            pass

    # Bù thêm các ô trống nếu chưa đủ kích thước
    if len(cells) < total_cells:
        cells.extend(['.'] * (total_cells - len(cells)))

    cells = cells[:total_cells]
    grid = [cells[r * cols:(r + 1) * cols] for r in range(rows)]
    return grid

def parse_puzzle_page(html_content: str):
    """Bóc tách thông tin từ các biến JavaScript nhúng trong HTML."""
    task_match = re.search(r"var\s+task\s*=\s*'([^']+)'", html_content)
    if not task_match:
        return None
    task_str = task_match.group(1)

    w_match = re.search(r"puzzleWidth:\s*(\d+)", html_content) or re.search(r'name="w"\s+value="(\d+)"', html_content)
    h_match = re.search(r"puzzleHeight:\s*(\d+)", html_content) or re.search(r'name="h"\s+value="(\d+)"', html_content)
    if not (w_match and h_match):
        return None
    cols = int(w_match.group(1))
    rows = int(h_match.group(1))

    id_match = re.search(r'id="puzzleID">([0-9,]+)<', html_content) or re.search(r"Puzzle ID:\s*([0-9,]+)", html_content)
    puzzle_id = id_match.group(1).replace(",", "") if id_match else "unknown"

    grid = decode_grid(task_str, rows, cols)

    return {
        "id": puzzle_id,
        "rows": rows,
        "cols": cols,
        "grid": grid,
        "raw_task": task_str
    }

# ==============================================================================
# 3. LƯU RA FILE INPUT .TXT
# ==============================================================================
def save_to_file(puzzle_data: dict, category_name: str, filepath: str):
    """
    Ghi dữ liệu ma trận bài toán:
    - Dòng 1: # Puzzle ID: ... | Category: ...
    - Dòng 2: rows cols
    - Các dòng tiếp theo: Ma trận ô cờ cách nhau bởi dấu cách ('B', 'W', '.')
    """
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Puzzle ID: {puzzle_data['id']} | Category: {category_name}\n")
        f.write(f"{puzzle_data['rows']} {puzzle_data['cols']}\n")
        for r in range(puzzle_data["rows"]):
            f.write(" ".join(puzzle_data["grid"][r]) + "\n")

# ==============================================================================
# 4. TIẾN TRÌNH CÀO TỰ ĐỘNG
# ==============================================================================
def fetch_all():
    total_saved = 0
    saved_ids = set()

    print("=" * 70)
    print(" BẮT ĐẦU CÀO DỮ LIỆU TỰ ĐỘNG TỪ PUZZLE-YIN-YANG.COM")
    print(f" Thư mục lưu trữ: {OUTPUT_DIR}")
    print("=" * 70)

    for cat_name, info in CATEGORY_TARGETS.items():
        size_param = info["size"]
        target_count = info["count"]
        cat_saved = 0
        attempts = 0
        max_attempts = target_count * 4

        print(f"\n[*] Đang lấy danh mục: {cat_name.upper()} (Mục tiêu: {target_count} màn)...")

        while cat_saved < target_count and attempts < max_attempts:
            attempts += 1
            timestamp = int(time.time() * 1000)
            url = f"{BASE_URL}/?size={size_param}&_={timestamp}" if size_param != "" else f"{BASE_URL}/?_={timestamp}"

            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code != 200:
                    time.sleep(1)
                    continue

                puzzle_data = parse_puzzle_page(resp.text)
                if not puzzle_data:
                    time.sleep(0.5)
                    continue

                pid = puzzle_data["id"]
                if pid in saved_ids and pid != "unknown":
                    time.sleep(0.3)
                    continue

                filename = f"{cat_name}_{pid}.txt"
                filepath = os.path.join(OUTPUT_DIR, filename)

                save_to_file(puzzle_data, cat_name, filepath)

                saved_ids.add(pid)
                cat_saved += 1
                total_saved += 1
                print(f"   [+] ({cat_saved}/{target_count}) Đã lưu: {filename} ({puzzle_data['rows']}x{puzzle_data['cols']})")

                time.sleep(0.4)

            except Exception as e:
                time.sleep(1)

        if cat_saved < target_count:
            print(f"   [!] Lưu ý: {cat_name} chỉ lấy được {cat_saved} màn (Đặc biệt Daily/Weekly/Monthly chỉ có 1 màn mỗi kỳ).")

    print("\n" + "=" * 70)
    print(f" HOÀN TẤT! Tổng cộng đã lưu thành công {total_saved} file input vào thư mục Yin_Yang/inputs/.")
    print("=" * 70)

if __name__ == "__main__":
    fetch_all()
