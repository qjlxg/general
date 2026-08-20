from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TARGETS_FILE = "targets.txt"
OUTPUT_FILE = "proon_paths.txt"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

FINGERPRINTS = [
    "vless",
    "vmess",
    "trojan",
    "hysteria",
    "hy2",
    "tuic",
    "proxies:",
    "clash",
    "v2ray",
    "sub_store",
    "hiddify",
]


def format_target_url(raw_target):
  raw_target = raw_target.strip()
  if not raw_target:
    return []
  
  urls = []
  if not raw_target.startswith("http://") and not raw_target.startswith("https://"):
    # 纯 IP 或域名，尝试同时生成 http 和 https 候选
    urls.append(f"http://{raw_target}")
    urls.append(f"https://{raw_target}")
  else:
    urls.append(raw_target)
  return urls


def audit_and_extract_real_links(target_url):
  valid_endpoints = set()
  parsed_u = urlparse(target_url)
  base_url = f"{parsed_u.scheme}://{parsed_u.netloc}"

  try:
    r = requests.get(base_url + "/", headers=HEADERS, timeout=6, verify=False)
    if r.status_code not in [200, 403]:
      return valid_endpoints

    content_text = r.text.lower()
    headers_text = str(r.headers).lower()
    title_text = ""
    
    content_type = r.headers.get("Content-Type", "").lower()
    if "text/html" in content_type:
      soup = BeautifulSoup(r.text, "html.parser")
      if soup.title:
        title_text = soup.title.get_text(" ", strip=True).lower()

      for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_link = urljoin(base_url, href)
        parsed_full = urlparse(full_link)
        if parsed_full.netloc == parsed_u.netloc:
          valid_endpoints.add(full_link)

    matched = False
    for fp in FINGERPRINTS:
      if (
          fp in content_text
          or fp in headers_text
          or fp in title_text
          or fp in target_url.lower()
      ):
        matched = True
        break

    if matched:
      valid_endpoints.add(base_url + "/")

  except Exception:
    pass

  return valid_endpoints


if __name__ == "__main__":
  if not os.path.exists(TARGETS_FILE):
    print(f"[!] 未找到目标配置文件 {TARGETS_FILE}，请先创建！")
    exit(1)

  target_urls_to_test = []
  with open(TARGETS_FILE, "r", encoding="utf-8") as f:
    for line in f:
      target_urls_to_test.extend(format_target_url(line))

  all_valid_urls = set()
  print(f"[*] 已从 {TARGETS_FILE} 加载目标，开始并发指纹审计...")

  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(audit_and_extract_real_links, url): url for url in target_urls_to_test}
    for future in as_completed(futures):
      res = future.result()
      if res:
        all_valid_urls.update(res)

  final_urls = sorted(list(all_valid_urls))
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url in final_urls:
      f.write(url + "\n")

  print(f"\n[+] 审计完成！共生成 {len(final_urls)} 个真实有效的候选链接，已保存至 {OUTPUT_FILE}")
