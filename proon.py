from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests
import os
import uuid

# 1. 在这里配置你的所有目标源（支持域名、IP加端口等）
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

# 兜底基础目录
FALLBACK_BASE_DIRS = [
    "/",
    "/app/",
    "/vless/",
    "/hiddify/",
    "/vpn-android/",
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
]

# 严格收窄：只允许 .yaml 和 .yam 后缀
EXTENSIONS = ["", ".yaml", ".yam"]


def load_dynamic_base_dirs(target_url):
  """针对特定目标安全加载历史资产中的对应目录"""
  dirs = set(FALLBACK_BASE_DIRS)
  parsed_target = urlparse(target_url)
  target_netloc = parsed_target.netloc

  if os.path.exists(OUTPUT_FILE):
    try:
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
          line_str = line.strip()
          if not line_str:
            continue
          # 如果是完整 URL，先解析
          if line_str.startswith("http://") or line_str.startswith(
              "https://"
          ):
            parsed_u = urlparse(line_str)
            # 只提取属于当前目标域名的路径，避免不同目标混淆
            if parsed_u.netloc == target_netloc:
              path = parsed_u.path
              if path.endswith("/"):
                dirs.add(path)
          else:
            if line_str.endswith("/"):
              dirs.add(line_str)
    except Exception as e:
      print(f"[!] 读取历史资产文件出错: {e}，将使用默认兜底目录。")

  return sorted(list(dirs))


def get_soft_404_baseline(target_url):
  """获取指定目标的“软 404”基准特征"""
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
  """生成探测矩阵"""
  payloads = set(base_dirs)
  for base_dir in base_dirs:
    clean_dir = base_dir if base_dir.endswith("/") else base_dir + "/"
    for word in DICTIONARY_WORDS:
      for ext in EXTENSIONS:
        payloads.add(f"{clean_dir}{word}{ext}")
  return sorted(list(payloads))


def check_path(target_url, path, baseline):
  """高精度、防误杀的路径确认逻辑"""
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
  """对单个目标执行完整的探测流程"""
  print(f"\n[*] 开始探测目标: {target_url}")
  base_dirs = load_dynamic_base_dirs(target_url)
  baseline = get_soft_404_baseline(target_url)
  paths_to_test = generate_payloads(base_dirs)

  print(
      f"[-] {target_url} 加载底座 {len(base_dirs)} 个，生成候选"
      f" {len(paths_to_test)} 个..."
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

  # 格式化并筛选结果：仅保留目录或 .yaml/.yam，并转为完整 URL
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

  # 去重并写入文件
  final_urls = sorted(list(set(all_results)))
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url_item in final_urls:
      f.write(url_item + "\n")

  print(
      f"\n[+] 所有目标探测完成！总计产出有效完整 URL 库 {len(final_urls)}"
      f" 个，已保存至 {OUTPUT_FILE}"
  )
