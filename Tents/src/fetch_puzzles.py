"""
MODULE: fetch_puzzles.py
MỤC ĐÍCH: Trích xuất và giải mã biến JavaScript 'task' từ puzzle-tents.com,
         lưu thành các file .txt theo giao diện trực quan khớp với bàn cờ gốc.
"""

import os
import re
import time
import requests

# ==============================================================================
# 1. CẤU HÌNH THƯ MỤC LƯU TRỮ VÀ DANH MỤC CÂU ĐỐ
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))       # Thư mục src/
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "inputs")         # Thư mục inputs/
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://www.puzzle-tents.com"

# Bảng tra cứu tham số size chính xác từ menu của web:
# size="" là 6x6 Easy, size="1" là 6x6 Hard, ..., size="10" là Special Monthly
CATEGORY_TARGETS = {
    "6x6_easy":        {"size": "",   "count": 10},
    "6x6_hard":        {"size": "1",  "count": 10},
    "8x8_easy":        {"size": "2",  "count": 8},
    "8x8_hard":        {"size": "3",  "count": 8},
    "10x10_easy":      {"size": "4",  "count": 6},
    "10x10_hard":      {"size": "5",  "count": 6},
    "15x15_easy":      {"size": "6",  "count": 4},
    "15x15_hard":      {"size": "7",  "count": 4},
    "special_daily":   {"size": "8",  "count": 1},
    "special_weekly":  {"size": "9",  "count": 1},  # Bàn đặc biệt 25x25
    "special_monthly": {"size": "10", "count": 1}
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.puzzle-tents.com/"
}

# ==============================================================================
# 2. HÀM GIẢI MÃ MA TRẬN TỪ BIẾN TASK
# ==============================================================================
def decode_grid(tree_code: str, rows: int, cols: int):
    """
    Giải mã chuỗi RLE cây thành ma trận 2 chiều [rows][cols]:
    - '_' đại diện cho 0 ô trống giữa hai cây liên tiếp
    - 'a'..'z' đại diện cho 1..26 ô trống
    - 'A'..'Z' đại diện cho 27..52 ô trống (dành cho các map lớn)
    """
    total_cells = rows * cols
    flat_cells = []

    for ch in tree_code:
        if ch == '_':
            gap = 0
        elif 'a' <= ch <= 'z':
            gap = ord(ch) - ord('a') + 1
        elif 'A' <= ch <= 'Z':
            gap = ord(ch) - ord('A') + 27
        else:
            gap = 0

        # Thêm các ô đất trống
        flat_cells.extend(['.'] * gap)
        # Nếu chưa vượt quá số ô của bàn thì ô tiếp theo là Cây
        if len(flat_cells) < total_cells:
            flat_cells.append('T')

    # Bù thêm ô trống ở cuối bàn nếu chuỗi kết thúc
    if len(flat_cells) < total_cells:
        flat_cells.extend(['.'] * (total_cells - len(flat_cells)))

    # Cắt chuẩn kích thước
    flat_cells = flat_cells[:total_cells]

    # Chuyển mảng 1D thành ma trận 2D
    grid = [flat_cells[r * cols:(r + 1) * cols] for r in range(rows)]
    return grid

def parse_puzzle_page(html_content: str):
    """Bóc tách thông tin từ các biến JavaScript nhúng trong HTML."""
    # 1. Trích xuất chuỗi task
    task_match = re.search(r"var\s+task\s*=\s*'([^']+)'", html_content)
    if not task_match:
        return None
    task_str = task_match.group(1)

    # 2. Trích xuất kích thước bàn cờ (Width, Height)
    w_match = re.search(r"puzzleWidth:\s*(\d+)", html_content) or re.search(r'name="w"\s+value="(\d+)"', html_content)
    h_match = re.search(r"puzzleHeight:\s*(\d+)", html_content) or re.search(r'name="h"\s+value="(\d+)"', html_content)
    if not (w_match and h_match):
        return None
    cols = int(w_match.group(1))
    rows = int(h_match.group(1))

    # 3. Trích xuất Puzzle ID
    id_match = re.search(r'id="puzzleID">([0-9,]+)<', html_content) or re.search(r"Puzzle ID:\s*([0-9,]+)", html_content)
    puzzle_id = id_match.group(1).replace(",", "") if id_match else "unknown"

    # 4. Tách các thành phần trong chuỗi task
    parts = task_str.split(',')
    tree_code = parts[0]
    clues = [int(x) for x in parts[1:] if x.isdigit()]

    if len(clues) < rows + cols:
        return None

    row_constraints = clues[:rows]
    col_constraints = clues[rows:rows + cols]

    # 5. Khôi phục ma trận Cây
    grid = decode_grid(tree_code, rows, cols)

    return {
        "id": puzzle_id,
        "rows": rows,
        "cols": cols,
        "row_constraints": row_constraints,
        "col_constraints": col_constraints,
        "grid": grid
    }

# ==============================================================================
# 3. LƯU THEO GIAO DIỆN BÀN CỜ TRỰC QUAN
# ==============================================================================
def save_to_file(puzzle_data: dict, category_name: str, filepath: str):
    """
    Ghi dữ liệu mô phỏng giao diện bàn cờ thực tế:
    - Dãy số Cột nằm ngang trên đỉnh.
    - Cột số Hàng nằm dọc bên mép trái của từng dòng ma trận.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Puzzle ID: {puzzle_data['id']} | Category: {category_name}\n")
        f.write(f"{puzzle_data['rows']} {puzzle_data['cols']}\n")
        
        # Dòng số ràng buộc CỘT (thụt vào 2 khoảng trắng để thẳng hàng với các ô)
        col_str = " ".join(map(str, puzzle_data["col_constraints"]))
        f.write(f"  {col_str}\n")
        
        # Từng dòng ma trận: [Chỉ số Hàng] [Nội dung các ô]
        for r in range(puzzle_data["rows"]):
            row_clue = puzzle_data["row_constraints"][r]
            row_content = " ".join(puzzle_data["grid"][r])
            f.write(f"{row_clue} {row_content}\n")

# ==============================================================================
# 4. TIẾN TRÌNH CÀO TỰ ĐỘNG
# ==============================================================================
def fetch_all():
    total_saved = 0
    saved_ids = set()

    print("=" * 70)
    print(" BẮT ĐẦU CÀO DỮ LIỆU TỰ ĐỘNG TỪ PUZZLE-TENTS.COM")
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
            # Thêm timestamp vào query string để đảm bảo web luôn cấp màn ngẫu nhiên mới
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

                # Nghỉ ngắn giữa các lượt tải
                time.sleep(0.5)

            except Exception as e:
                time.sleep(1)

        if cat_saved < target_count:
            print(f"   [!] Lưu ý: {cat_name} chỉ lấy được {cat_saved} màn (Đặc biệt Daily/Weekly/Monthly chỉ có 1 màn mỗi kỳ).")

    print("\n" + "=" * 70)
    print(f" HOÀN TẤT! Tổng cộng đã lưu thành công {total_saved} file input vào thư mục inputs/.")
    print("=" * 70)

if __name__ == "__main__":
    fetch_all()