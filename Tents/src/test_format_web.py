import requests

url = "https://www.puzzle-tents.com/?size=1"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"[*] Mã HTTP phản hồi: {resp.status_code}")
    print(f"[*] Độ dài nội dung: {len(resp.text)} ký tự")
    
    # Lưu lại để xem trang web thực sự trả về cái gì
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print("[+] Đã lưu phản hồi vào file debug_page.html")
except Exception as e:
    print(f"[!] Lỗi kết nối: {e}")