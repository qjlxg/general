import os
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

# 目标网站地址（如有需要，可修改此处网址）
TARGET_URL = "https://pro-on.org"
OUTPUT_FILE = "proon_paths.txt"


def get_site_paths(start_url):
  visited = set()
  to_visit = {start_url}
  domain = urlparse(start_url).netloc
  paths = set()

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  print(f"开始抓取网站: {start_url}")

  while to_visit:
    current_url = to_visit.pop()
    if current_url in visited:
      continue

    visited.add(current_url)
    parsed_url = urlparse(current_url)
    paths.add(parsed_url.path or "/")

    try:
      response = requests.get(
          current_url, headers=headers, timeout=10, verify=True
      )
      if response.status_code != 200:
        continue

      if "text/html" in response.headers.get("Content-Type", ""):
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
          absolute_url = urljoin(current_url, link["href"])
          p_url = urlparse(absolute_url)

          if p_url.netloc == domain:
            clean_url = f"{p_url.scheme}://{p_url.netloc}{p_url.path}"
            if clean_url not in visited:
              to_visit.add(clean_url)

    except Exception as e:
      print(f"抓取出错 {current_url}: {e}")

  return sorted(list(paths))


if __name__ == "__main__":
  all_paths = get_site_paths(TARGET_URL)

  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for path in all_paths:
      f.write(path + "\n")

  print(f"抓取完成，共找到 {len(all_paths)} 个路径，已保存至 {OUTPUT_FILE}")
