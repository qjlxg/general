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
OUTPUT_NODES_FILE = "nodes.txt"  # 汇总保存所有提取出的节点

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

  # 1. 尝试直接按行解析（明文多链接或 Clash 节点行）
  for line in content_text.splitlines():
    line = line.strip()
    if any(line.startswith(scheme) for scheme in NODE_SCHEMES):
      nodes.append(line)

  if len(nodes) > 0:
    return nodes

  # 2. 尝试作为 Base64 解码（常见机场订阅）
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

  # 3. 尝试作为 YAML 解析（Clash 配置文件格式，提取 proxies 里的节点）
  try:
    yaml_data = yaml.safe_load(content_text)
    if isinstance(yaml_data, dict):
      proxies = yaml_data.get("proxies", [])
      if isinstance(proxies, list):
        # 如果是 clash 节点字典，可以转为字符串或保持原样（这里我们把整个 yaml 或将其转化为通用格式，或者如果 clash 原文需要保存，可按需处理。由于标准节点订阅通常是 uri，这里主要提取 uri 或将 clash 节点转换。大部分情况直接存解析出来的代理字典或跳过。通常 YAML 直连是用原文件或提取 clash 节点。若直接是文本订阅，上面两步已涵盖。）
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
  """请求单个链接，提取节点并返回结果"""
  url = url.strip()
  if not url or url.endswith("/"):
    return {"url": url, "status": "SKIP_DIRECTORY", "nodes": []}

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
  global_nodes = set()  # 全局节点去重池

  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(process_url, url): url for url in urls_to_fetch}
    for future in as_completed(futures):
      res = future.result()
      if res["count"] > 0:
        print(
            f"[成功提取] {res['url']} -> 发现节点数: {res['count']}"
        )
        for n in res["nodes"]:
          global_nodes.add(n)
      all_results.append(res)

  # 1. 写入 CSV 统计表
  with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["URL", "Status", "NodeCount"])
    for r in all_results:
      writer.writerow(
          [r["url"], r["status"], r.get("count", len(r.get("nodes", [])))]
      )

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
