from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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


def audit_and_extract_real_links(target_url):
  print(f"[*] 正在对目标进行深度指纹审计与链接提取: {target_url}")
  valid_endpoints = set()
  base_url = target_url.rstrip("/")

  try:
    r = requests.get(base_url + "/", headers=HEADERS, timeout=8, verify=False)
    if r.status_code not in [200, 403]:
      print(f"[-] 目标 {target_url} 状态码异常 ({r.status_code})，跳过。")
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
        parsed_base = urlparse(base_url)
        if parsed_full.netloc == parsed_base.netloc:
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
      print(f"[+] 【命中指纹】{base_url}/ 匹配成功，已收录根目录及提取站内真实链接")
      valid_endpoints.add(base_url + "/")
    else:
      print(f"[-] 目标 {target_url} 未检测到代理/订阅指纹特征。")

  except Exception as e:
    print(f"[!] 访问目标 {target_url} 出错: {e}")

  return valid_endpoints


if __name__ == "__main__":
  all_valid_urls = set()

  for target in TARGET_URLS:
    endpoints = audit_and_extract_real_links(target)
    all_valid_urls.update(endpoints)

  final_urls = sorted(list(all_valid_urls))
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url in final_urls:
      f.write(url + "\n")

  print(
      f"\n[+] 审计完成！共生成 {len(final_urls)}"
      f" 个真实有效的候选链接，已保存至 {OUTPUT_FILE}"
  )
