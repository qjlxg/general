from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests
import os
import uuid

# 你的目标源列表
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

# 核心盲打种子目录
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

# 探测字典词汇
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

# 【核心卡口】严格限定只抓取文件后缀，绝不留空目录作为最终结果
EXTENSIONS = [".yaml", ".yam"]


def harvest_real_paths(target_url):
  """收集基础目录种子"""
  discovered_dirs = set(CORE_SEEDS)
  target_parsed = urlparse(target_url)
  base_netloc = target_parsed.netloc

  print(f"[*] 正在对目标进行全方位结构探测: {target_url}")

  # 1. 尝试抓取首页超链接中的目录
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

  # 2. 历史资产文件加载（只提取属于该域名的目录）
  if os.path.exists(OUTPUT_FILE):
    try:
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
          l_str = line.strip()
          if l_str:
            p_u = urlparse(l_str)
            if p_u.netloc == base_netloc:
              path = p_u.path
              if path.endswith("/"):
                discovered_dirs.add(path)
              else:
                dir_part = os.path.dirname(path) + "/"
                if dir_part != "//":
                  discovered_dirs.add(dir_part)
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
  }
  try:
    r = requests.get(
        url, headers=HEADERS, timeout=5, allow_redirects=False, verify=False
    )
    baseline["status"] = r.status_code
    baseline["length"] = len(r.content)
    if "text/html" in r.headers.get("Content-Type", "").lower():
      soup = BeautifulSoup(r.text, "html.parser")
      if soup.title:
        baseline["title"] = soup.title.get_text(" ", strip=True).lower()
      baseline["text_snippet"] = r.text[:300].strip().lower()
  except Exception:
    pass
  return baseline


def check_path(target_url, path, baseline):
  """高精度验证：严格过滤 HTML 网页及软 404"""
  url = target_url.rstrip("/") + path
  try:
    r = requests.get(
        url, headers=HEADERS, timeout=6, allow_redirects=False, verify=False
    )

    # 过滤明显的错误状态码
    if r.status_code in [404, 500, 502, 503, 504]:
      return None

    # 【关键卡口 1】强制过滤网页类型（Content-Type 包含 text/html 的绝不可能是 yaml 节点文件）
    content_type = r.headers.get("Content-Type", "").lower()
    if "text/html" in content_type:
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
      # 如果是 yaml 后缀且返回 403（有文件但不可直接列目录/无权限），也可以视作潜在目标保留，或按需调整
      if path.endswith(".yaml") or path.endswith(".yam"):
        return path
      return None

    if r.status_code == 200:
      # 再次做软 404 文本相似度对比检查
      if baseline["status"] == 200:
        current_snippet = r.text[:300].strip().lower()
        if (
            current_snippet == baseline["text_snippet"]
            and len(current_snippet) > 50
        ):
          return None

      print(f"[发现有效文件] {target_url} -> {path} (200)")
      return path

  except requests.RequestException:
    pass

  return None


def scan_target(target_url):
  base_dirs = harvest_real_paths(target_url)
  baseline = get_soft_404_baseline(target_url)

  found_paths = set()
  current_bases = base_dirs

  # 两轮递归探测
  for round_idx in range(2):
    payloads = set()
    for b in current_bases:
      clean_b = b if b.endswith("/") else b + "/"
      for w in DICTIONARY_WORDS:
        for ext in EXTENSIONS:  # 严格限制为 .yaml / .yam
          payloads.add(f"{clean_b}{w}{ext}")

    new_dirs = set()
    with ThreadPoolExecutor(max_workers=20) as executor:
      futures = {
          executor.submit(check_path, target_url, p, baseline): p
          for p in payloads
      }
      for future in as_completed(futures):
        res = future.result()
        if res:
          found_paths.add(res)

    if not found_paths:
      break

  # 【关键卡口 2】最终格式化输出时：绝对只保留以 .yaml 或 .yam 结尾的完整绝对 URL
  valid_urls = []
  for p in found_paths:
    if p.endswith(".yaml") or p.endswith(".yam"):
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
      f"\n[+] 路径探测完成！过滤后纯净的 YAML/YAM 节点配置文件链接共计"
      f" {len(final_urls)} 个，已保存至 {OUTPUT_FILE}"
  )
