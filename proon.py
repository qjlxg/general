from bs4 import BeautifulSoup
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 你需要探测的目标源
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

# 【核心：像 FOFA 一样的指纹特征库】
# 只要网页的 Title、Body 或响应头里包含这些关键词，就判定它含有节点资产
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


def audit_target_with_fofa_logic(target_url):
  """像 FOFA 一样，通过分析网页 Title、Body 指纹来判断目标是否有效"""
  print(f"[*] 正在对目标进行 FOFA 式指纹审计: {target_url}")

  try:
    # 直接请求目标网址（可按需连带请求几个常见订阅路径，但核心是看内容指纹）
    r = requests.get(target_url, headers=HEADERS, timeout=8, verify=False)

    if r.status_code not in [200, 403]:
      print(f"[-] 目标 {target_url} 状态码异常 ({r.status_code})，跳过。")
      return False

    content_text = r.text.lower()
    headers_text = str(r.headers).lower()

    # 提取 Title
    title_text = ""
    if "text/html" in r.headers.get("Content-Type", "").lower():
      soup = BeautifulSoup(r.text, "html.parser")
      if soup.title:
        title_text = soup.title.get_text(" ", strip=True).lower()

    # 检查是否命中任何一个 FOFA 特征指纹
    matched_tags = []
    for fp in FINGERPRINTS:
      if (
          fp in content_text
          or fp in headers_text
          or fp in title_text
          or fp in target_url.lower()
      ):
        matched_tags.append(fp)

    if matched_tags:
      print(
          f"[+] 【命中指纹】{target_url} 成功匹配特征: {list(set(matched_tags))}"
      )
      return True
    else:
      print(f"[-] 目标 {target_url} 未检测到代理/订阅指纹特征。")
      return False

  except Exception as e:
    print(f"[!] 访问目标 {target_url} 出错: {e}")
    return False


if __name__ == "__main__":
  valid_targets = []

  for target in TARGET_URLS:
    if audit_target_with_fofa_logic(target):
      valid_targets.append(target)

  # 将通过指纹审计的目标写入文件，供后续节点抓取脚本使用
  with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for url in valid_targets:
      f.write(url + "\n")

  print(
      f"\n[+] FOFA 式指纹审计完成！共筛选出符合特征的高价值目标"
      f" {len(valid_targets)} 个，已保存至 {OUTPUT_FILE}"
  )
