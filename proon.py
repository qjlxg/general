import os
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
import xml.etree.ElementTree as ET

# 目标网站地址（以 proton 相关或目标站点为主，可自行修改）
TARGET_URL = "https://pro-on.org/"
OUTPUT_FILE = "proon_paths.txt"


def get_paths_from_sitemap(base_url, headers):
  """尝试从网站的 sitemap.xml 中直接提取所有路径"""
  sitemap_urls = [
      urljoin(base_url, "/sitemap.xml"),
      urljoin(base_url, "/sitemap_index.xml"),
  ]
  paths = set()

  for sitemap_url in sitemap_urls:
    try:
      response = requests.get(sitemap_url, headers=headers, timeout=10)
      if response.status_code == 200:
        print(发现并解析 Sitemap: {sitemap_url})
        root = ET.fromstring(response.content)
        # 处理带有命名空间的 xml
        for elem in root.iter():
          if elem.tag.endswith("loc"):
            if elem.text:
              parsed = urlparse(elem.text.strip())
              if parsed.path:
                paths.add(parsed.path)
    except Exception as e:
      print(f"Sitemap 解析跳过 {sitemap_url}: {e}")

  return paths


def crawl_site(start_url, headers):
  """递归深度爬取"""
  visited = set()
  to_visit = {start_url}
  domain = urlparse(start_url).netloc
  paths = set()

  print(f"开始递归深度抓取: {start_url}")

  while to_visit and len(visited) < 500:  # 限制最大抓取量防止死循环
    current_url = to_visit.pop()
    if current_url in visited:
      continue
    visited.add(current_url)

    parsed_url = urlparse(current_url)
    if parsed_url.path:
      paths.add(parsed_url.path)

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

  return paths


if __name__ == "__main__":
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
  }

  # 1. 优先通过 Sitemap 获取全量路径
  all_paths = get_paths_from_sitemap(TARGET_URL, headers)

  # 2. 结合页面递归爬取补充
  scraped_paths = crawl_site(TARGET_URL, headers)
  all_paths.update(scraped_paths)

  # 确保根目录存在
  all_paths.add("/")

  sorted_paths = sorted(list(all_paths))

  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for path in sorted_paths:
      f.write(path + "\n")

  print(f"抓取完成，共找到 {len(sorted_paths)} 个路径，已保存至 {OUTPUT_FILE}")
