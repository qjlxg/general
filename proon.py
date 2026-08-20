from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
import os
import uuid

TARGET_URLS = [
    "https://pro-on.org",
    "http://8.218.196.8:80",
    "http://8.211.135.202/",
]

OUTPUT_FILE = "proon_paths.txt"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# 细分类型的探测词汇
DICTIONARY_WORDS = [
    "login",
    "admin",
    "api",
    "config",
    "sitemap",
    "robots",
    "index",
    "test",
    "backup",
    "download",
    "feed",
    "search",
    "user",
    "auth",
    "settings",
    "setup",
]

EXTENSIONS = ["", ".yaml", ".yam"]


def crawl_real_paths_from_target(target_url):
  """【核心突破】真正去浏览、解析目标网址的首页、robots.txt 和 sitemap.xml 提取真实路径"""
  discovered_dirs = {"/"}
  target_parsed = urlparse(target_url)
  base_netloc = target_parsed.netloc

  print(f"[*] 正在真实浏览并抓取目标结构: {target_url}")

  # 1. 抓取首页并提取所有同源链接
  try:
    r = requests.get(target_url, headers=HEADERS, timeout=8, verify=False)
    if r.status_code == 200:
      soup = BeautifulSoup(r.text, "html.parser")
      for tag in soup.find_all(["a", "link", "script"], href=True):
        href = tag.get("href")
        if href:
          full_url = urljoin(target_url, href)
          parsed_full = urlparse(full_url)
          # 确保是同源链接
          if parsed_full.netloc == base_netloc:
            path = parsed_full.path
            if path:
              # 如果是目录形式或不带后缀，提取其父目录
              if path.endswith("/"):
                discovered_dirs.add(path)
              else:
                dir_part = os.path.dirname(path) + "/"
                if dir_part != "//":
                  discovered_dirs.add(dir_part)
  except Exception as e:
    print(f"[!] 抓取首页链接出错 ({target_url}): {e}")

  # 2. 尝试读取 robots.txt
  try:
    robots_url = target_url.rstrip("/") + "/robots.txt"
    r = requests.get(robots_url, headers=HEADERS, timeout=5, verify=False)
    if r.status_code == 200:
      for line in r.text.splitlines():
        if (
            line.lower().startswith("allow:")
            or line.lower().startswith("disallow:")
            or line.lower().startswith("sitemap:")
        ):
          parts = line.split(":", 1)
          if len(parts) > 1:
            val = parts[1].strip()
            if val.startswith("/"):
              if val.endswith("/"):
                discovered_dirs.add(val)
              else:
                discovered_dirs.add(os.path.dirname(val) + "/")
  except Exception:
    pass

  # 3. 尝试读取历史资产文件中属于该域名的有效目录（历史沉淀）
  if os.path.exists(OUTPUT_FILE):
    try:
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
          line_str = line.strip()
          if line_str:
            p_u = urlparse(line_str)
            if p_u.netloc == base_netloc and p_u.path.endswith("/"):
              discovered_dirs.add(p_u.path)
    except Exception:
      pass

  print(
      f"[+] 通过真实浏览与解析，共为 {target_url} 发现"
      f" {len(discovered_dirs)} 个真实底座目录。"
  )
  return sorted(list(discovered_dirs))


def get_soft_404_baseline(target_url):
  """获取软 404 基准特征"""
  random_path = f"/__definitely_not_exist_{uuid.uuid4().hex[:8]}__/"
  url = target_url.rstrip("/") + random_path
  baseline = {
      "status": 404,
      "length": 0,
      "title": "",
      "text_snippet": "",
      "location": "",
  }
  try:
    r = requests.get(
        url, headers=HEADERS, timeout=5, allow_redirects=False, verify=False
    )
    baseline["status"] = r.status_code
    baseline["length"] = len(r.content)
    baseline["location"] = r.headers.get("Location", "")

    if "text/html" in r.headers.get("Content-Type", "").lower():
      soup = BeautifulSoup(r.text, "html.parser")
      title = soup.title
      baseline["title"] = (
          title.get_text(" ", strip=True).lower() if title else ""
      )
      baseline["text_snippet"] = r.text[:300].strip().lower()
  except Exception:
    pass
  return baseline


def generate_payloads(base_dirs):
  """基于真实发现的目录矩阵组合字典和 .yaml/.yam"""
  payloads = set(base_dirs)
  for base_dir in base_dirs:
    clean_dir = base_dir if base_dir.endswith("/") else base_dir + "/"
    for word in DICTIONARY_WORDS:
      for ext in EXTENSIONS:
        payloads.add(f"{clean_dir}{word}{ext}")
  return sorted(list(payloads))


def check_path(target_url, path, baseline):
  """高精度路径验证"""
  url = target_url.rstrip("/") + path
  try:
    r = requests.get(
        url, headers=HEADERS, timeout=5, allow_redirects=False, verify=False
    )

    if r.status_code in [404, 500, 502, 503, 504]:
      return None

    if r.status_code in [301, 302, 303, 307, 308]:
      location = r.headers.get("Location", "")
      parsed_loc = urlparse(location)
      loc_path = parsed_loc.path

      if loc_path in ("", "/"):
        return None

      baseline_loc_path = urlparse(baseline["location"]).path
      if (
          baseline["status"] in [301, 302, 303, 307, 308]
          and loc_path == baseline_loc_path
      ):
        return None

      if (
          location.startswith("/")
          or parsed_loc.netloc == urlparse(target_url).netloc
      ):
        return path
      return None

    if r.status_code == 403:
      return path

    if r.status_code == 200:
      if baseline["status"] == 200:
        current_title = ""
        current_snippet = r.text[:300].strip().lower()

        if "text/html" in r.headers.get("Content-Type", "").lower():
          soup = BeautifulSoup(r.text, "html.parser")
          if soup.title:
            current_title = soup.title.get_text(" ", strip=True).lower()

        is_same_title = (
            current_title and current_title == baseline["title"]
        ) or (not current_title and not baseline["title"])
        is_same_snippet = (
            current_snippet == baseline["text_snippet"]
            and len(current_snippet) > 50
        )

        if is_same_title and is_same_snippet:
          return None

      print(f"[发现有效目标] {target_url} -> {path} (200)")
      return path

  except requests.RequestException:
    pass

  return None


def scan_target(target_url):
  # 1. 真正去浏览抓取目标网站的真实目录
  base_dirs = crawl_real_paths_from_target(target_url)
  baseline = get_soft_404_baseline(target_url)
  paths_to_test = generate_payloads(base_dirs)

  print(
      f"[-] 开始深度探测：基于真实发现的 {len(base_dirs)} 个目录，生成"
      f" {len(paths_to_test)} 个候选..."
  )

  found_paths = set(base_dirs)

  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {
        executor.submit(check_path, target_url, p, baseline): p
        for p in paths_to_test
    }
    for future in as_completed(futures):
      res = future.result()
      if res:
        found_paths.add(res)

  valid_urls = []
  for p in found_paths:
    if p.endswith("/") or p.endswith(".yaml") or p.endswith(".yam"):
      full_url = target_url.rstrip("/") + (p if p.startswith("/") else "/" + p)
      valid_urls.append(full_url)

  return valid_urls


if __name__ == "__main__":
  import urllib3

  urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

  all_results = []
  for target in TARGET_URLS:
    try:
      res = scan_target(target)
      all_results.extend(res)
    except Exception as e:
      print(f"[!] 目标 {target} 探测出错: {e}")

  final_urls = sorted(list(set(all_results)))
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url_item in final_urls:
      f.write(url_item + "\n")

  print(
      f"\n[+] 所有目标探测完成！总计产出有效完整 URL 库 {len(final_urls)}"
      f" 个，已保存至 {OUTPUT_FILE}"
  )
