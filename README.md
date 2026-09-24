# BÀI TẬP LỚN 1: GIẢI QUYẾT BÀI TOÁN LOGIC PUZZLES
**Môn học:** Nhập môn Trí tuệ nhân tạo (HK1 2026 - 2027)  
**Nhóm thực hiện:** Nhóm 4 thành viên  
**Bài toán lựa chọn:** 
1. **Tents and Trees** (Bài toán 1: DFS & Hill Climbing)
2. **Yin-Yang** (Bài toán 2: DFS & IDA*)

---

## 1. Cấu trúc thư mục dự án

```text
BTL-Nhap-mon-AI/
├── Tents/                         # Bài toán 1: Tents and Trees
│   ├── inputs/                    # >50 file dữ liệu bài toán mẫu (.txt)
│   └── src/
│       ├── board.py               # Core Engine: Đọc file, bàn cờ, kiểm tra luật
│       ├── dfs.py                 # Blind Search: DFS + Backtracking + Pruning
│       ├── hill_climbing.py       # Heuristic Search: Hill Climbing + Random Restart
│       ├── fetch_puzzles.py       # Công cụ cào dữ liệu từ puzzle-tents.com
│       └── GUI.py                 # Giao diện Pygame phong cách Forest Grass Dashboard
├── Yin_Yang/                      # Bài toán 2: Yin-Yang (Âm Dương)
│   ├── inputs/                    # 60 file dữ liệu bài toán mẫu (.txt) từ 6x6 đến 40x40
│   │   ├── 6x6_easy_*.txt
│   │   ├── 6x6_normal_*.txt
│   │   ├── 6x6_hard_*.txt
│   │   ├── 10x10_*.txt, 15x15_*.txt, special_*.txt
│   └── src/
│       ├── board.py               # Core Engine Yin-Yang: Quản lý bàn cờ, luật 2x2, liên thông trực giao
│       ├── dfs.py                 # Blind Search: DFS + Backtracking + Suy diễn tất định + Pruning
│       ├── ida_star.py            # Heuristic Search: IDA* với hàm đánh giá độ phân mảnh liên thông
│       ├── fetch_puzzles.py       # Crawler giải mã task từ puzzle-yin-yang.com
│       └── GUI.py                 # Giao diện Pygame phong cách Bàn Cờ Vây / Trúc & Mực Thủy Mặc Zen
├── BTL1.pdf                       # Đề bài và quy định chấm điểm của giảng viên
└── README.md                      # Hướng dẫn chạy chương trình và tài liệu nhóm
```

---

## 2. Hướng dẫn chạy bài toán Yin-Yang

### 2.1. Cài đặt thư viện yêu cầu
```bash
pip install pygame-ce requests beautifulsoup4
```

### 2.2. Cào dữ liệu bài toán mới từ web (Tùy chọn)
Thư mục `Yin_Yang/inputs/` đã có sẵn 60 bài toán chuẩn. Nếu muốn cào thêm các đề mới từ web `puzzle-yin-yang.com`:
```bash
python Yin_Yang/src/fetch_puzzles.py
```

### 2.3. Chạy thuật toán dòng lệnh (CLI Mode)
- **Giải bằng DFS (Blind Search):**
```bash
python Yin_Yang/src/dfs.py Yin_Yang/inputs/6x6_easy_1232640.txt
```
- **Giải bằng IDA* (Heuristic Search):**
```bash
python Yin_Yang/src/ida_star.py Yin_Yang/inputs/6x6_easy_1232640.txt
```

### 2.4. Khởi chạy Giao diện đồ họa trực quan (GUI Mode)
Giao diện được thiết kế theo phong cách **Bàn Cờ Vây / Trúc & Mực Thủy Mặc Zen** (Kaya/Bamboo wood board, quân cờ Âm Dương đen mun bóng & ngọc trắng sứ có bóng đổ mềm mại, viền vàng ánh kim):
```bash
python Yin_Yang/src/GUI.py
```

**Các tính năng nổi bật trên GUI:**
1. **Giải thuật AI mượt mà:** Chạy luồng nền (Worker Thread), hỗ trợ cả DFS và IDA*.
2. **Trình diễn Step-by-Step linh hoạt:** Play/Pause, Step Next/Prev, First/Last, Scrub Bar kéo thả tức thì, điều chỉnh tốc độ từ 0.5x đến Max.
3. **So sánh Đối đầu (Benchmark Side-by-side):** Chạy cả DFS và IDA* trên cùng một đề bài, hiển thị bảng so sánh thời gian, bộ nhớ RAM đỉnh, số node duyệt, số lần quay lui.
4. **Xuất Báo Cáo TXT:** Bấm nút *"XUẤT BÁO CÁO TXT"* trong modal so sánh để tự động lưu file báo cáo thực nghiệm phục vụ viết báo cáo BTL.
5. **Chế độ Tự Chơi (Manual Play):** Nhấp chuột trực tiếp lên bàn cờ để đặt quân đen/trắng, tích hợp kiểm tra luật thời gian thực (vi phạm 2x2, tính liên thông).