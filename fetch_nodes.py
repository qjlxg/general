from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import base64
import yaml
import os

INPUT_FILE = "proon_paths.txt"
OUTPUT_NODES_FILE = "nodes.txt"
HEADERS = {"User-Agent": "Clash/1.0"}

def parse_yaml_proxies(content):
    """深度解析 YAML 配置文件中的代理节点"""
    nodes = []
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict) and 'proxies' in data:
            # 提取 proxies 列表里的所有节点名称或完整信息
            for proxy in data['proxies']:
                nodes.append(str(proxy))
    except:
        pass
    return nodes

def process_url(url):
    url = url.strip()
    # 过滤明显的垃圾链接
    if any(x in url for x in ["api.lixingyong.com", "dns-query", ".jpg", ".png"]):
        return []

    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if r.status_code != 200:
            return []

        content = r.text
        found = []

        # 1. 尝试 YAML 解析 (Clash)
        found.extend(parse_yaml_proxies(content))

        # 2. 尝试 Base64 解码 (订阅链接)
        try:
            decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
            for line in decoded.splitlines():
                if any(line.startswith(s) for s in ["vless://", "vmess://", "ss://", "trojan://"]):
                    found.append(line.strip())
        except:
            pass

        return found
    except:
        return []

if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"[!] 请先运行 proon.py")
        exit(1)

    with open(INPUT_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"[*] 正在从 {len(urls)} 个链接中解析 YAML/Base64 配置...")
    
    final_nodes = set()
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_url, url): url for url in urls}
        for future in as_completed(futures):
            final_nodes.update(future.result())

    with open(OUTPUT_NODES_FILE, "w", encoding="utf-8") as f:
        for node in final_nodes:
            f.write(node + "\n")

    print(f"[+] 提取完成！共提取 {len(final_nodes)} 个节点，已保存至 {OUTPUT_NODES_FILE}")
