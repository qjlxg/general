import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

TARGET_URL = "https://pro-on.org"
OUTPUT_FILE = "proton_paths.txt"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def get_all_paths():
  all_paths = set()
  domain = urlparse(TARGET_URL).netloc

  # 1. 解析 robots.txt
  sitemaps = []
  try:
    r = requests.get(
        urljoin(TARGET_URL, "/robots.txt"), headers=HEADERS, timeout=10
    )
    if r.status_code == 200:
      sitemaps = [
          line.split(":", 1)[1].strip()
          for line in r.text.splitlines()
          if line.lower().startswith("sitemap:")
      ]
  except Exception:
    pass

  # robots.txt 没找到 Sitemap，主动尝试常见地址兜底
  if not sitemaps:
    sitemaps = [
        urljoin(TARGET_URL, "/sitemap.xml"),
        urljoin(TARGET_URL, "/sitemap_index.xml"),
    ]

  # 2. 根据 XML 根节点精确解析 Sitemap / Sitemap Index
  def parse_sitemap(url):
    try:
      r = requests.get(url, headers=HEADERS, timeout=10)
      if r.status_code != 200:
        return

      root = ET.fromstring(r.content)
      # 获取标签名（去除可能存在的 XML Namespace，例如 {http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex）
      tag_name = root.tag.split("}")[-1].lower()

      if tag_name == "sitemapindex":
        # 如果是子索引，递归解析其中的子 sitemap
        for loc in root.findall(
            ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        ):
          if loc.text:
            parse_sitemap(loc.text.strip())
        # 兼容无 namespace 的情况
        for loc in root.findall(".//loc"):
          if loc.text and loc.text.strip() not in sitemaps:
            # 简单去重防止重复递归
            pass
      elif tag_name == "urlset":
        # 如果是具体的 url 集合，提取路径
        for loc in root.findall(
            ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        ):
          if loc.text:
            parsed = urlparse(loc.text.strip())
            if parsed.path:
              all_paths.add(parsed.path)
        for loc in root.findall(".//loc"):
          if loc.text:
            parsed = urlparse(loc.text.strip())
            if parsed.path:
              all_paths.add(parsed.path)
    except Exception:
      pass

  for sm in sitemaps:
    parse_sitemap(sm)

  # 3. 首页/站内页面递归爬取兜底补充
  visited = set()
  to_visit = {TARGET_URL}

  while to_visit and len(visited) < 500:
    curr = to_visit.pop()
    if curr in visited:
      continue
    visited.add(curr)

    try:
      r = requests.get(curr, headers=HEADERS, timeout=5)
      parsed_curr = urlparse(curr)
      if parsed_curr.path:
        all_paths.add(parsed_curr.path)

      if "text/html" in r.headers.get("Content-Type", ""):
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
          full_url = urljoin(curr, a["href"])
          p_url = urlparse(full_url)
          if p_url.netloc == domain:  # 过滤外部域名
            to_visit.add(full_url)
    except Exception:
      continue

  # 4. 统一、去重、排序
  return sorted(list(all_paths))


if __name__ == "__main__":
  result = get_all_paths()
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for p in result:
      f.write(p + "\n")
  print(f"抓取完成，共 {len(result)} 个路径，已保存至 {OUTPUT_FILE}")
