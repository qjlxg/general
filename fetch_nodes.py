from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import base64
import yaml
import json
import os
import re

INPUT_FILE = "proon_paths.txt"
OUTPUT_NODES_FILE = "nodes.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# 严格的节点协议白名单
VALID_SCHEMES = (
    "vless://", "vmess://", "trojan://", "ssr://", "ss://",
    "hysteria://", "hy2://", "tuic://"
)

def is_valid_node(line):
    """判断是否为真正的节点链接"""
    line = line.strip()
    # 过滤掉普通网页、图片外链、DNS 查询等垃圾链接
    if any(line.startswith(s) for s in VALID_SCHEMES):
        return True
    return False

def extract_nodes(content):
    """从网页内容中提取节点"""
    nodes = []
    # 1. 直接匹配协议行
    for line in content.splitlines():
        if is_valid_node(line):
            nodes.append(line.strip())
            
    # 2. 尝试 Base64 解码后的内容
    try:
        if len(content.strip()) > 10 and len(content.strip()) % 4 == 0:
            decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
            for line in decoded.splitlines():
                if is_valid_node(line):
                    nodes.append(line.strip())
    except:
        pass
        
    # 3. 尝试 YAML 格式 (Clash)
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict) and 'proxies' in data:
            # 如果是合法的 clash 配置文件，我们这里只保存原始数据结构或做转换，为了简单直接存入文件
            nodes.append(f"YAML_CONFIG_FOUND: {content[:50]}...") 
    except:
        pass
        
    return list(set(nodes))

def process_url(url):
    url = url.strip()
    if not url or "://" not in url:
        return []
    
    # 【核心过滤】直接跳过图片、DNS、网页等明显非节点链接
    if any(x in url for x in ["api.lixingyong.com", "dns-query", ".jpg", ".png", ".webp"]):
        return []

    try:
        r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if r.status_code == 200:
            return extract_nodes(r.text)
    except:
        pass
    return []

if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"[!] 请先运行 proon.py 生成 {INPUT_FILE}")
        exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"[*] 开始从 {len(urls)} 个链接中深度提取节点...")
    
    final_nodes = set()
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_url, url): url for url in urls}
        for future in as_completed(futures):
            nodes = future.result()
            for n in nodes:
                final_nodes.add(n)

    with open(OUTPUT_NODES_FILE, "w", encoding="utf-8") as f:
        for node in sorted(list(final_nodes)):
            f.write(node + "\n")

    print(f"[+] 提取完成！已保存 {len(final_nodes)} 个合法节点到 {OUTPUT_NODES_FILE}")
