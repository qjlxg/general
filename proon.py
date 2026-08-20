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

  if not sitemaps:
    sitemaps = [
        urljoin(TARGET_URL, "/sitemap.xml"),
        urljoin(TARGET_URL, "/sitemap_index.xml"),
    ]

  # 2. 精确解析 Sitemap / Sitemap Index
  def parse_sitemap(url):
    try:
      r = requests.get(url, headers=HEADERS, timeout=10)
      if r.status_code != 200:
        return

      root = ET.fromstring(r.content)
      tag_name = root.tag.split("}")[-1].lower()

      if tag_name == "sitemapindex":
        for loc in root.findall(
            ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        ):
          if loc.text:
            parse_sitemap(loc.text.strip())
        for loc in root.findall(".//loc"):
          if loc.text:
            parse_sitemap(loc.text.strip())
      elif tag_name == "urlset":
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

  # 3. 深度递归爬取（扩大抓取量，确保捞出内页和深层文件）
  visited = set()
  # 把刚才 sitemap 拿到的路径转成完整 URL 作为后续深度递归的种子
  to_visit = {urljoin(TARGET_URL, p) for p in all_paths}
  to_visit.add(TARGET_URL)

  while to_visit and len(visited) < 2000:  # 提高上限以捕捉更多深层页面
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
          # 限制在同域名下，并且排除常见锚点或静态资源后缀
          if p_url.netloc == domain:
            path_lower = p_url.path.lower()
            if not any(
                path_lower.endswith(ext)
                for ext in [
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".css",
                    ".js",
                    ".ico",
                    ".svg",
                ]
            ):
              clean_url = f"{p_url.scheme}://{p_url.netloc}{p_url.path}"
              if clean_url not in visited:
                to_visit.add(clean_url)
    except Exception:
      continue

  return sorted(list(all_paths))


if __name__ == "__main__":
  result = get_all_paths()
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for p in result:
      f.write(p + "\n")
  print(f"抓取完成，共 {len(result)} 个路径，已保存至 {OUTPUT_FILE}")
