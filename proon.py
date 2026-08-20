from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
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

# 核心盲打字典（当页面无链接、无robots时，直接以此作为初始探测种子）
CORE_SEEDS = [
    "/",
    "/app/",
    "/api/",
    "/config/",
    "/vless/",
    "/v2ray/",
    "/hiddify/",
    "/sub/",
    "/downloads/",
    "/backup/",
    "/share/",
    "/node/",
    "/data/",
]

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
    "sub",
    "list",
    "pool",
]

EXTENSIONS = ["", ".yaml", ".yam"]


def harvest_real_paths(target_url):
  """多路资产收集：首页抓取 + robots/sitemap 尝试 + 历史沉淀"""
  discovered_dirs = set(CORE_SEEDS)
  target_parsed = urlparse(target_url)
  base_netloc = target_parsed.netloc

  print(f"[*] 正在对目标进行全方位结构探测: {target_url}")

  # 1. 尝试抓取首页超链接
  try:
    r = requests.get(target_url, headers=HEADERS, timeout=6, verify=False)
    if r.status_code == 200:
      soup = BeautifulSoup(r.text, "html.parser")
      for tag in soup.find_all(["a", "link", "script"], href=True):
        href = tag.get("href")
        if href:
          full_url = urljoin(target_url, href)
          p_full = urlparse(full_url)
          if p_full.netloc == base_netloc and p_full.path:
            path = p_full.path
            if path.endswith("/"):
              discovered_dirs.add(path)
            else:
              dir_part = os.path.dirname(path) + "/"
              if dir_part != "//":
                discovered_dirs.add(dir_part)
  except Exception:
    pass

  # 2. 尝试读取 robots.txt
  try:
    r = requests.get(
        target_url.rstrip("/") + "/robots.txt",
        headers=HEADERS,
        timeout=4,
        verify=False,
    )
    if r.status_code == 200:
      for line in r.text.splitlines():
        if ":" in line:
          val = line.split(":", 1)[1].strip()
          if val.startswith("/"):
            discovered_dirs.add(
                val if val.endswith("/") else os.path.dirname(val) + "/"
            )
  except Exception:
    pass

  # 3. 历史资产文件加载
  if os.path.exists(OUTPUT_FILE):
    try:
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
          l_str = line.strip()
          if l_str:
            p_u = urlparse(l_str)
            if p_u.netloc == base_netloc and p_u.path.endswith("/"):
              discovered_dirs.add(p_u.path)
    except Exception:
      pass

  return sorted(list(discovered_dirs))


def get_soft_404_baseline(target_url):
  """软 404 基准校准"""
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
      if soup.title:
        baseline["title"] = soup.title.get_text(" ", strip=True).lower()
      baseline["text_snippet"] = r.text[:300].strip().lower()
  except Exception:
    pass
  return baseline


def check_path(target_url, path, baseline):
  """高精度防误杀验证"""
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

        if (
            current_title == baseline["title"]
            and current_snippet == baseline["text_snippet"]
            and len(current_snippet) > 50
        ):
          return None

      print(f"[发现有效目标] {target_url} -> {path} (200)")
      return path

  except requests.RequestException:
    pass

  return None


def scan_target(target_url):
  # 1. 搜集基础种子目录（即使没 robots 也能靠 CORE_SEEDS 盲打）
  base_dirs = harvest_real_paths(target_url)
  baseline = get_soft_404_baseline(target_url)

  # 2. 多轮递归探测（确保即使网站结构隐藏得很深也能一层层剥开）
  found_paths = set(base_dirs)
  current_bases = base_dirs

  for round_idx in range(2):  # 最多进行 2 轮递归
    print(
        f"[*] 开启第 {round_idx + 1} 轮探测，当前基底目录数:"
        f" {len(current_bases)}"
    )

    payloads = set()
    for b in current_bases:
      clean_b = b if b.endswith("/") else b + "/"
      for w in DICTIONARY_WORDS:
        for ext in EXTENSIONS:
          payloads.add(f"{clean_b}{w}{ext}")

    new_discovered_dirs = set()
    with ThreadPoolExecutor(max_workers=20) as executor:
      futures = {
          executor.submit(check_path, target_url, p, baseline): p
          for p in payloads
      }
      for future in as_completed(futures):
        res = future.result()
        if res:
          found_paths.add(res)
          # 如果新发现的路径是个目录（以 / 结尾），加入下一轮递归队列
          if res.endswith("/"):
            new_discovered_dirs.add(res)

    # 把新发现的目录作为下一轮的基底
    if not new_discovered_dirs:
      break
    current_bases = sorted(list(new_discovered_dirs))

  # 3. 统一格式化过滤：仅保留目录或 .yaml / .yam 格式的完整链接
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
      f"\n[+] 探测完成！总计产出有效完整 URL 库 {len(final_urls)} 个，已保存至"
      f" {OUTPUT_FILE}"
  )
