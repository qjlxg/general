import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

TARGET_URL = "https://pro-on.org"
OUTPUT_FILE = "proton_paths.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def get_all_paths():
    all_paths = set()
    domain = urlparse(TARGET_URL).netloc

    # 1. 从 robots.txt 发现 Sitemap
    try:
        r = requests.get(urljoin(TARGET_URL, "/robots.txt"), headers=HEADERS, timeout=10)
        sitemaps = [line.split(":", 1)[1].strip() for line in r.text.splitlines() if line.lower().startswith("sitemap:")]
    except:
        sitemaps = [urljoin(TARGET_URL, "/sitemap.xml")]

    # 2. 递归解析 Sitemap Index 和所有 sitemap
    def parse_sitemap(url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            root = ET.fromstring(r.content)
            # 处理 sitemapindex
            for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                if "sitemap" in loc.text and "xml" in loc.text:
                    parse_sitemap(loc.text)
                else:
                    all_paths.add(urlparse(loc.text).path)
        except: pass

    for sm in sitemaps:
        parse_sitemap(sm)

    # 3. 首页/站内页面递归爬取 & 4. 提取 href & 5. 过滤外部域名
    visited = set()
    to_visit = {TARGET_URL}
    
    while to_visit and len(visited) < 500:
        curr = to_visit.pop()
        if curr in visited: continue
        visited.add(curr)
        
        try:
            r = requests.get(curr, headers=HEADERS, timeout=5)
            all_paths.add(urlparse(curr).path)
            if "text/html" in r.headers.get("Content-Type", ""):
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    full_url = urljoin(curr, a["href"])
                    p_url = urlparse(full_url)
                    if p_url.netloc == domain: # 过滤外部域名
                        to_visit.add(full_url)
        except: continue

    # 6. 统一 URL & 7. 全局去重 & 8. 排序
    return sorted(list(all_paths))

if __name__ == "__main__":
    result = get_all_paths()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for p in result:
            f.write(p + "\n")
    print(f"抓取完成，共 {len(result)} 个路径，已保存至 {OUTPUT_FILE}")
