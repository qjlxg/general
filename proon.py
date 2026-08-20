from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests
import os
import uuid

TARGET_URL = "https://pro-on.org"
OUTPUT_FILE = "proon_paths.txt"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# 兜底基础目录（当本地尚无历史资产文件时使用）
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

# 严格收窄：只允许 .yaml 和 .yam 后缀（空字符串用于保留目录底座）
EXTENSIONS = ["", ".yaml", ".yam"]


def load_dynamic_base_dirs():
  """安全加载明确的目录型底座（支持完整 URL 或相对路径的兼容读取）"""
  dirs = set(FALLBACK_BASE_DIRS)

  if os.path.exists(OUTPUT_FILE):
    print(
        f"[*] 发现历史路径资产文件 {OUTPUT_FILE}，正在安全加载明确的目录型底座..."
    )
    try:
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
          line_str = line.strip()
          if not line_str:
            continue
          # 兼容处理：如果是完整 URL，提取出它的 path 部分
          if line_str.startswith("http://") or line_str.startswith(
              "https://"
          ):
            parsed_u = urlparse(line_str)
            path = parsed_u.path
          else:
            path = line_str

          # 只有明确以 / 结尾的路径才作为下一轮目录底座
          if path.endswith("/"):
            dirs.add(path)
      print(f"[*] 成功安全加载 {len(dirs)} 个有效目录作为探测基底。")
    except Exception as e:
      print(f"[!] 读取历史资产文件出错: {e}，将使用默认兜底目录。")
  else:
    print("[*] 未发现本地历史资产文件，使用默认兜底目录启动。")

  return sorted(list(dirs))


def get_soft_404_baseline():
  """获取“软 404”基准特征"""
  random_path = f"/__definitely_not_exist_{uuid.uuid4().hex[:8]}__/"
  url = TARGET_URL.rstrip("/") + random_path
  baseline = {
      "status": 404,
      "length": 0,
      "title": "",
      "text_snippet": "",
      "location": "",
  }
  try:
    r = requests.get(
        url, headers=HEADERS, timeout=5, allow_redirects=False, verify=True
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
  print(
      f"[-] 软 404 基准校准完成 (状态码: {baseline['status']},"
      f" 长度: {baseline['length']})"
  )
  return baseline


def generate_payloads(base_dirs):
  """基于严格清洗后的目录矩阵组合字典和 .yaml/.yam 后缀"""
  payloads = set(base_dirs)
  for base_dir in base_dirs:
    clean_dir = base_dir if base_dir.endswith("/") else base_dir + "/"
    for word in DICTIONARY_WORDS:
      for ext in EXTENSIONS:
        payloads.add(f"{clean_dir}{word}{ext}")
  return sorted(list(payloads))


def check_path(path, baseline):
  """高精度、防误杀的路径确认逻辑"""
  url = TARGET_URL.rstrip("/") + path
  try:
    r = requests.get(
        url, headers=HEADERS, timeout=5, allow_redirects=False, verify=True
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
          or parsed_loc.netloc == urlparse(TARGET_URL).netloc
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

      print(f"[发现有效目标] {path} (200)")
      return path

  except requests.RequestException:
    pass

  return None


def run_fuzzing():
  base_dirs = load_dynamic_base_dirs()
  baseline = get_soft_404_baseline()
  paths_to_test = generate_payloads(base_dirs)
  print(
      f"开始高精度防误杀深度探测：加载安全目录底座 {len(base_dirs)} 个，共生成"
      f" {len(paths_to_test)} 个候选目标..."
  )

  found_paths = set(base_dirs)

  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {
        executor.submit(check_path, p, baseline): p for p in paths_to_test
    }
    for future in as_completed(futures):
      res = future.result()
      if res:
        found_paths.add(res)

  return sorted(list(found_paths))


if __name__ == "__main__":
  raw_results = run_fuzzing()

  # 过滤规则：只保留目录型路径（以 / 结尾）或者以 .yaml / .yam 结尾的完整链接
  filtered_results = []
  for p in raw_results:
    if p.endswith("/") or p.endswith(".yaml") or p.endswith(".yam"):
      # 统一拼接转换成完整的绝对 URL 输出
      full_url = TARGET_URL.rstrip("/") + (p if p.startswith("/") else "/" + p)
      filtered_results.append(full_url)

  # 写入文件
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url_item in sorted(list(set(filtered_results))):
      f.write(url_item + "\n")

  print(
      f"探测完成，最终产出纯净有效完整 URL 库 {len(filtered_results)}"
      f" 个（仅保留目录及 .yaml/.yam），已保存至 {OUTPUT_FILE}"
  )
