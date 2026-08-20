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

# 需要过滤的静态资源后缀
EXCLUDE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".css",
    ".js",
    ".ico",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
)


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
  except Exception as e:
    print(f"获取 robots.txt 失败: {e}")

  if not sitemaps:
    sitemaps = [
        urljoin(TARGET_URL, "/sitemap.xml"),
        urljoin(TARGET_URL, "/sitemap_index.xml"),
    ]

  # 2. 精确解析 Sitemap / Sitemap Index (带 visited_sitemaps 防止死循环)
  visited_sitemaps = set()

  def parse_sitemap(url):
    if url in visited_sitemaps:
      return
    visited_sitemaps.add(url)

    try:
      r = requests.get(url, headers=HEADERS, timeout=10)
      if r.status_code != 200:
        print(f"Sitemap 请求异常 [{r.status_code}]: {url}")
        return

      root = ET.fromstring(r.content)
      tag_name = root.tag.split("}")[-1].lower()

      # 兼容带命名空间或不带命名空间的查找
      loc_elements = root.findall(
          ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
      )
      if not loc_elements:
        loc_elements = root.findall(".//loc")

      if tag_name == "sitemapindex":
        for loc in loc_elements:
          if loc.text:
            parse_sitemap(loc.text.strip())
      elif tag_name == "urlset":
        for loc in loc_elements:
          if loc.text:
            parsed = urlparse(loc.text.strip())
            if parsed.path:
              all_paths.add(parsed.path)
    except Exception as e:
      print(f"Sitemap 解析错误 ({url}): {e}")

  for sm in sitemaps:
    parse_sitemap(sm)

  # 3. 深度递归爬取补充
  visited = set()
  to_visit = {urljoin(TARGET_URL, p) for p in all_paths}
  to_visit.add(TARGET_URL)

  while to_visit and len(visited) < 2000:
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
          if p_url.netloc == domain:
            path_lower = p_url.path.lower()
            if not path_lower.endswith(EXCLUDE_EXTENSIONS):
              clean_url = f"{p_url.scheme}://{p_url.netloc}{p_url.path}"
              if clean_url not in visited:
                to_visit.add(clean_url)
    except Exception:
      continue

  # 4. 最终输出前统一清洗、去重、过滤静态资源并排序
  final_paths = set()
  for p in all_paths:
    if not p.lower().endswith(EXCLUDE_EXTENSIONS):
      final_paths.add(p)

  return sorted(list(final_paths))


if __name__ == "__main__":
  result = get_all_paths()
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for p in result:
      f.write(p + "\n")
  print(f"抓取完成，共精选有效路径 {len(result)} 个，已保存至 {OUTPUT_FILE}")
