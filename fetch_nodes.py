from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import requests
import base64
import yaml
import json
import csv
import os

INPUT_FILE = "proon_paths.txt"
OUTPUT_CSV = "node_stats.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# 常见代理节点的关键词特征（用于粗略或精确判定有效节点行）
NODE_SCHEMES = (
    "vless://",
    "vmess://",
    "trojan://",
    "ssr://",
    "ss://",
    "hysteria://",
    "hy2://",
    "tuic://",
    "http://",
    "https://",
)


def is_base64(s):
  """检查字符串是否为有效的 Base64 编码"""
  if not isinstance(s, str):
    return False
  s = s.strip()
  if len(s) % 4 != 0:
    return False
  try:
    # 尝试解码并重新编码以验证
    decoded = base64.b64decode(s, validate=True)
    return True
  except Exception:
    return False


def count_nodes_in_content(content_text, content_bytes):
  """智能解析多种格式（明文、Base64、YAML、JSON），计算节点总数"""
  nodes = set()

  # 1. 尝试直接按文本按行解析（明文多链接格式）
  for line in content_text.splitlines():
    line = line.strip()
    if any(line.startswith(scheme) for scheme in NODE_SCHEMES):
      nodes.add(line)

  # 如果直接按行找到很多，优先返回
  if len(nodes) > 0:
    return len(nodes)

  # 2. 尝试作为 Base64 解码（常见的机场订阅格式）
  cleaned_text = content_text.strip()
  if is_base64(cleaned_text):
    try:
      decoded_bytes = base64.b64decode(cleaned_text)
      decoded_text = decoded_bytes.decode("utf-8", errors="ignore")
      for line in decoded_text.splitlines():
        line = line.strip()
        if any(line.startswith(scheme) for scheme in NODE_SCHEMES):
          nodes.add(line)
      if len(nodes) > 0:
        return len(nodes)
    except Exception:
      pass

  # 3. 尝试作为 YAML 解析（Clash 配置文件格式）
  try:
    yaml_data = yaml.safe_load(content_text)
    if isinstance(yaml_data, dict):
      # Clash 的 proxies 字段通常存放节点
      proxies = yaml_data.get("proxies", [])
      if isinstance(proxies, list) and len(proxies) > 0:
        return len(proxies)
  except Exception:
    pass

  # 4. 尝试作为 JSON 解析
  try:
    json_data = json.loads(content_text)
    if isinstance(json_data, list):
      return len(json_data)
    elif isinstance(json_data, dict):
      # 某些 JSON 会把节点放在 nodes 或 proxies 键里
      for key in ["nodes", "proxies", "list"]:
        if key in json_data and isinstance(json_data[key], list):
          return len(json_data[key])
  except Exception:
    pass

  return len(nodes)


def process_url(url):
  """请求单个链接并统计节点数"""
  url = url.strip()
  if not url or url.endswith("/"):
    return {"url": url, "status": "SKIP_DIRECTORY", "node_count": 0}

  try:
    r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
    if r.status_code == 200:
      text_content = r.text
      byte_content = r.content
      count = count_nodes_in_content(text_content, byte_content)
      return {"url": url, "status": 200, "node_count": count}
    else:
      return {"url": url, "status": r.status_code, "node_count": 0}
  except Exception as e:
    return {"url": url, "status": "ERROR", "node_count": 0}


if __name__ == "__main__":
  import urllib3

  urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

  if not os.path.exists(INPUT_FILE):
    print(
        f"[!] 未找到上一轮的资产文件 {INPUT_FILE}，请先运行路径探测脚本！"
    )
    exit(1)

  urls_to_fetch = []
  with open(INPUT_FILE, "r", encoding="utf-8") as f:
    for line in f:
      u = line.strip()
      if u:
        urls_to_flex = urls_to_fetch.append(u)

  print(
      f"[*] 成功加载资产文件，共计 {len(urls_to_fetch)}"
      f" 个链接，开始并发抓取与节点统计..."
  )

  results = []
  # 使用 20 线程并行请求链接
  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(process_url, url): url for url in urls_to_fetch}
    for future in as_completed(futures):
      res = future.result()
      if res["node_count"] > 0:
        print(
            f"[有效节点源] {res['url']} -> 发现节点数: {res['node_count']}"
        )
      results.append(res)

  # 写入 CSV 统计表（符合你的CSV规范：日期、代码等或者此处适配链接与节点统计）
  # 按照要求输出 CSV 文件格式
  with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    # CSV 表头
    writer.writerow(["URL", "Status", "NodeCount"])
    for r in results:
      writer.writerow([r["url"], r["status"], r["node_count"]])

  print(
      f"\n[+] 统计完成！共生成 {len(results)} 条记录的统计表，已保存至"
      f" {OUTPUT_CSV}"
  )
