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
OUTPUT_NODES_FILE = "nodes.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

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
    base64.b64decode(s, validate=True)
    return True
  except Exception:
    return False


def extract_nodes_from_content(content_text):
  """智能解析多种格式，返回提取到的节点列表"""
  nodes = []

  # 1. 尝试直接按行解析
  for line in content_text.splitlines():
    line = line.strip()
    if any(line.startswith(scheme) for scheme in NODE_SCHEMES):
      nodes.append(line)

  if len(nodes) > 0:
    return nodes

  # 2. 尝试作为 Base64 解码
  cleaned_text = content_text.strip()
  if is_base64(cleaned_text):
    try:
      decoded_bytes = base64.b64decode(cleaned_text)
      decoded_text = decoded_bytes.decode("utf-8", errors="ignore")
      for line in decoded_text.splitlines():
        line = line.strip()
        if any(line.startswith(scheme) for scheme in NODE_SCHEMES):
          nodes.append(line)
      if len(nodes) > 0:
        return nodes
    except Exception:
      pass

  # 3. 尝试作为 YAML 解析
  try:
    yaml_data = yaml.safe_load(content_text)
    if isinstance(yaml_data, dict):
      proxies = yaml_data.get("proxies", [])
      if isinstance(proxies, list):
        pass
  except Exception:
    pass

  # 4. 尝试作为 JSON 解析
  try:
    json_data = json.loads(content_text)
    if isinstance(json_data, list):
      for item in json_data:
        if isinstance(item, str) and any(
            item.startswith(s) for s in NODE_SCHEMES
        ):
          nodes.append(item)
    elif isinstance(json_data, dict):
      for key in ["nodes", "proxies", "list"]:
        if key in json_data and isinstance(json_data[key], list):
          for item in json_data[key]:
            if isinstance(item, str) and any(
                item.startswith(s) for s in NODE_SCHEMES
            ):
              nodes.append(item)
  except Exception:
    pass

  return nodes


def process_url(url):
  """请求单个链接，提取节点并返回结果（确保任何情况下都包含 count 键）"""
  url = url.strip()
  if not url or url.endswith("/"):
    return {"url": url, "status": "SKIP_DIRECTORY", "nodes": [], "count": 0}

  try:
    r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
    if r.status_code == 200:
      extracted_nodes = extract_nodes_from_content(r.text)
      return {
          "url": url,
          "status": 200,
          "nodes": extracted_nodes,
          "count": len(extracted_nodes),
      }
    else:
      return {"url": url, "status": r.status_code, "nodes": [], "count": 0}
  except Exception:
    return {"url": url, "status": "ERROR", "nodes": [], "count": 0}


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
        urls_to_fetch.append(u)

  print(
      f"[*] 成功加载资产文件，共计 {len(urls_to_fetch)}"
      f" 个链接，开始并发抓取节点..."
  )

  all_results = []
  global_nodes = set()

  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(process_url, url): url for url in urls_to_fetch}
    for future in as_completed(futures):
      res = future.result()
      # 安全获取 count，防止任何意外的 KeyError
      cnt = res.get("count", 0)
      if cnt > 0:
        print(f"[成功提取] {res['url']} -> 发现节点数: {cnt}")
        for n in res.get("nodes", []):
          global_nodes.add(n)
      all_results.append(res)

  # 1. 写入 CSV 统计表
  with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["URL", "Status", "NodeCount"])
    for r in all_results:
      writer.writerow([r["url"], r["status"], r.get("count", 0)])

  # 2. 写入汇总的节点文件 nodes.txt
  final_nodes_list = sorted(list(global_nodes))
  with open(OUTPUT_NODES_FILE, "w", encoding="utf-8") as f:
    for node in final_nodes_list:
      f.write(node + "\n")

  print(
      f"\n[+] 抓取完成！"
      f"\n    - 统计报表已保存至: {OUTPUT_CSV}"
      f"\n    - 聚合节点总数: {len(final_nodes_list)} 个，已保存至"
      f" {OUTPUT_NODES_FILE}"
  )
