from bs4 import BeautifulSoup
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

COMMON_PATHS = [
    "",
    "/config.yaml",
    "/sub",
    "/api/v1/client/subscribe",
    "/clash/config",
    "/api/v1/client/subscribe?token=",
]


def audit_and_expand_target(target_url):
  print(f"[*] 正在对目标进行 FOFA 式指纹审计: {target_url}")
  valid_endpoints = set()
  base_url = target_url.rstrip("/")

  try:
    r = requests.get(base_url, headers=HEADERS, timeout=8, verify=False)
    if r.status_code not in [200, 403]:
      print(f"[-] 目标 {target_url} 状态码异常 ({r.status_code})，跳过。")
      return valid_endpoints

    content_text = r.text.lower()
    headers_text = str(r.headers).lower()
    title_text = ""
    if "text/html" in r.headers.get("Content-Type", "").lower():
      soup = BeautifulSoup(r.text, "html.parser")
      if soup.title:
        title_text = soup.title.get_text(" ", strip=True).lower()

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
      print(f"[+] 【命中指纹】{target_url} 匹配成功，开始衍生扩展路径...")
      for p in COMMON_PATHS:
        valid_endpoints.add(base_url + p)
    else:
      print(f"[-] 目标 {target_url} 未检测到代理/订阅指纹特征。")

  except Exception as e:
    print(f"[!] 访问目标 {target_url} 出错: {e}")

  return valid_endpoints


if __name__ == "__main__":
  all_valid_urls = set()

  for target in TARGET_URLS:
    endpoints = audit_and_expand_target(target)
    all_valid_urls.update(endpoints)

  final_urls = sorted(list(all_valid_urls))
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url in final_urls:
      f.write(url + "\n")

  print(
      f"\n[+] FOFA 式指纹审计与路径扩展完成！共生成 {len(final_urls)}"
      f" 个精准候选链接，已保存至 {OUTPUT_FILE}"
  )
