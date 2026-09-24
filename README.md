# BÀI TẬP LỚN 1: GIẢI QUYẾT BÀI TOÁN LOGIC PUZZLES
**Môn học:** Nhập môn Trí tuệ nhân tạo (HK1 2026 - 2027)  
**Nhóm thực hiện:** Nhóm 4 thành viên  
**Bài toán lựa chọn:** 
1. **Tents and Trees** (Trọng tâm giai đoạn 1)
2. **Yin-Yang** (Giai đoạn 2)

---

## 1. Cấu trúc thư mục dự án

```text
BTL-Nhap-mon-AI/
├── inputs/                      # Chứa >50 file dữ liệu bài toán mẫu (.txt)
│   ├── 6x6_easy_*.txt
│   ├── 8x8_hard_*.txt
│   └── ...
├── src/                         # Mã nguồn chính của bài toán Tents
│   ├── board.py                 # Core Engine: Đọc file, quản lý bàn cờ, kiểm tra luật
│   ├── dfs.py                   # Thuật toán Blind Search: DFS + Backtracking + Pruning
│   ├── hill_climbing.py         # Thuật toán Heuristic: Hill Climbing + Random Restart
│   ├── fetch_puzzles.py         # Công cụ tự động cào và giải mã dữ liệu từ web (Run cái này để tạo folder inputs)
│   └── GUI.py                   # Giao diện trực quan mô phỏng Step-by-Step
├── Yin_Yang/                    # Mã nguồn cho bài toán thứ hai (triển khai sau)
├── .gitignore                   # Loại trừ file rác, cache, debug
├── BTL1.pdf                     # Đề bài và quy định chấm điểm của giảng viên
└── README.md                    # Tài liệu hướng dẫn làm việc nội bộ nhóm