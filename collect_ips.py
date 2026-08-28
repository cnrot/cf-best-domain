import requests
from bs4 import BeautifulSoup
import re
import os
import time

# 设置请求头，模拟浏览器访问
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 目标URL列表
# 已移除 https://stock.hostmonit.com/CloudFlareYes（站点转型为 VPS 监控，CF 优选 IP 业务下线）。
# https://cf.090227.xyz 已改为前端 JS 渲染，但其后端纯文本接口可直连：
#   https://addressesapi.090227.xyz/CloudFlareYes  格式为 `IP#运营商线路`
urls = [
    'https://ip.164746.xyz/ipTop10.html',
    'https://addressesapi.090227.xyz/CloudFlareYes',
    'https://api.uouin.com/cloudflare.html',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
]

# 正则表达式用于匹配IP地址
ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'

# 运营商线路标签归一化：
#   090227 的 CM-Default / CU-Default / CT-Default → 移动 / 联通 / 电信
#   无线路信息的 IP 统一标记为 ANY（通用），供华为云按线路分组时补足、CF 忽略线路。
LINE_PREFIX_MAP = {
    'CM': '移动',
    'CU': '联通',
    'CT': '电信',
}


def normalize_line(tag):
    """把原始线路标签归一化为 电信/联通/移动/ANY。"""
    tag = (tag or '').strip()
    up = tag.upper()
    for prefix, name in LINE_PREFIX_MAP.items():
        if up.startswith(prefix):
            return name
    return 'ANY' if tag in ('', 'ANY') else tag


def add_ip(ip, line_tag):
    """记录 (IP, 线路)。同一 IP 可属于多条线路（如 090227 的三网通用优选 IP）。"""
    all_ips.add((ip, normalize_line(line_tag)))


# 检查ip.txt文件是否存在,如果存在则删除它
if os.path.exists('ip.txt'):
    os.remove('ip.txt')

# 存储 (IP, 线路) 对（去重；同一 IP 可有多条线路）
all_ips = set()

for url in urls:
    try:
        print(f"正在处理: {url}")
        # 发送HTTP请求获取网页内容
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"  HTTP状态码: {response.status_code}, 跳过")
            continue

        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 根据网站的不同结构找到包含IP地址的元素
        # 注意：cf.090227.xyz 与 stock.hostmonit.com 已改为前端 JS 渲染，
        # requests 拿不到 IP，已从 urls 中移除。
        if url == 'https://ip.164746.xyz/ipTop10.html':
            # 纯文本，逗号分隔，无线路信息
            for ip in re.findall(ip_pattern, response.text):
                add_ip(ip, 'ANY')
            print(f"  从{url}找到{len(re.findall(ip_pattern, response.text))}个IP")
            continue
        elif url == 'https://addressesapi.090227.xyz/CloudFlareYes':
            # 纯文本，格式为 `IP#运营商线路`（如 104.17.245.114#CT-Default）
            count = 0
            for raw in response.text.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                if '#' in raw:
                    ip, _, tag = raw.partition('#')
                else:
                    ip, tag = raw, 'ANY'
                ip = ip.strip()
                if re.fullmatch(ip_pattern, ip):
                    add_ip(ip, tag)
                    count += 1
            print(f"  从{url}找到{count}个IP")
            continue
        elif url == 'https://api.uouin.com/cloudflare.html':
            elements = soup.find_all('td')
        elif url == 'https://www.wetest.vip/page/cloudflare/address_v4.html':
            elements = soup.find_all('td', attrs={'data-label': '优选地址'})
        else:
            elements = soup.find_all('li')

        # 遍历所有元素,查找IP地址（这些站点无线路信息，统一标 ANY）
        ip_count = 0
        for element in elements:
            element_text = element.get_text()
            ip_matches = re.findall(ip_pattern, element_text)

            # 如果找到IP地址,则添加到集合
            for ip in ip_matches:
                add_ip(ip, 'ANY')
                ip_count += 1

        print(f"  从{url}找到{ip_count}个IP")
        time.sleep(1)  # 避免请求过快

    except requests.exceptions.Timeout:
        print(f"处理 {url} 时超时，跳过")
    except Exception as e:
        print(f"处理 {url} 时出错：{e}")

# 将去重后的 IP 写入文件，格式 `IP#线路`，按 (线路, IP) 排序便于阅读
with open('ip.txt', 'w', encoding='utf-8') as file:
    for ip, line in sorted(all_ips, key=lambda x: (x[1], x[0])):
        file.write(f'{ip}#{line}\n')

# 唯一 IP 数（按 IP 去重统计，便于日志可读）
unique_ip_count = len({ip for ip, _ in all_ips})
print(f'总共找到 {unique_ip_count} 个唯一IP（{len(all_ips)} 条线路记录），已保存到 ip.txt 文件中。')
