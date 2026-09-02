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
#   https://cf.090227.xyz/{ct,cmcc,cu}  分线路纯文本，格式 `IP#线路`（电信/移动/联通优选，无延迟）
# ip.164746.xyz 改抓首页表格（含延迟），原 ipTop10.html 仅 1 个 IP 且无延迟。
urls = [
    'https://ip.164746.xyz/',
    'https://cf.090227.xyz/ct',
    'https://cf.090227.xyz/cmcc',
    'https://cf.090227.xyz/cu',
    'https://api.uouin.com/cloudflare.html',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
]

# 正则表达式用于匹配IP地址
ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'

# 延迟阈值（毫秒）：超过 MAX_LATENCY 的 IP 丢弃，不写入 ip.txt。
# 90ms 以下的优先使用——由 ip.txt 内按延迟升序排序 + 同步端取前 N 个 自动保证。
MAX_LATENCY = 90.0

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
    # 直接命中中文线路名
    for name in ('电信', '联通', '移动'):
        if name in tag:
            return name
    # "多线"/"通用"等不区分运营商的，归为 ANY
    if any(k in tag for k in ('多线', '通用', '全部', '默认')):
        return 'ANY'
    return 'ANY' if tag in ('', 'ANY') else tag


def parse_latency(text):
    """从文本中提取延迟数值（毫秒，float）。无法解析返回 None。

    兼容：`136.85ms`、`132 毫秒`、`69.56`、`<1` 等。
    """
    if not text:
        return None
    s = text.strip()
    # 取第一个 数字(.数字) 片段
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def add_ip(ip, line_tag, latency=None):
    """记录 (IP, 线路, 延迟)。

    同一 IP 可属于多条线路（如 090227 的三网通用优选 IP）。
    同一 (IP, 线路) 以更小的延迟覆盖（取最优延迟）。
    """
    line = normalize_line(line_tag)
    key = (ip, line)
    existing = all_ips.get(key)
    if existing is None:
        all_ips[key] = latency
    else:
        # 已存在：取更小延迟（None 视为无穷大，不覆盖有值延迟）
        if latency is not None and (existing is None or latency < existing):
            all_ips[key] = latency


# 检查ip.txt文件是否存在,如果存在则删除它
if os.path.exists('ip.txt'):
    os.remove('ip.txt')

# 存储 (IP, 线路) -> 延迟(ms 或 None)
all_ips = {}

for url in urls:
    try:
        print(f"正在处理: {url}")
        # 发送HTTP请求获取网页内容
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"  HTTP状态码: {response.status_code}, 跳过")
            continue

        text = response.text

        if url == 'https://ip.164746.xyz/':
            # 首页表格：表头 [IP地址, 已发送, 已接收, 丢包率, 平均延迟, 下载速度, 测速时间]
            # 无线路列 → ANY；IP 在 <a> 里，延迟在第5个 td
            soup = BeautifulSoup(text, 'html.parser')
            count = 0
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 5:
                    continue
                a = tds[0].find('a')
                ip = a.get_text(strip=True) if a else tds[0].get_text(strip=True)
                if not re.fullmatch(ip_pattern, ip):
                    continue
                latency = parse_latency(tds[4].get_text(strip=True))
                add_ip(ip, 'ANY', latency)
                count += 1
            print(f"  从{url}找到{count}个IP")
            time.sleep(1)
            continue

        if url in ('https://cf.090227.xyz/ct', 'https://cf.090227.xyz/cmcc', 'https://cf.090227.xyz/cu'):
            # 分线路纯文本，格式 `IP#线路`（全为同一线路的优选 IP，无延迟）
            # /ct→电信、/cmcc→移动、/cu→联通；行尾线路标签如 'CF 电信优选'
            # 直接用路径映射线路；延迟留空(None)，排序时对该线路排最后。
            line_map = {'ct': '电信', 'cmcc': '移动', 'cu': '联通'}
            line = line_map[url.rsplit('/', 1)[1]]
            count = 0
            for raw in text.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                ip = raw.split('#')[0].strip()
                if re.fullmatch(ip_pattern, ip):
                    # 该站为 CM 付费精选源，无延迟但优选度极高。
                    # 用自增序当哨兵延迟(0,1,2..)：既让它们排在该线路所有真实延迟最前参与竞争，
                    # 又保持上游内部顺序（小延迟→优先）；且不会被 MAX_LATENCY 丢弃。
                    add_ip(ip, line, float(count))
                    count += 1
            print(f"  从{url}找到{count}个IP")
            continue

        if url == 'https://api.uouin.com/cloudflare.html':
            # 数据行 td: [线路, IP, 丢包, 延迟, 速度, 带宽, Colo, 时间]
            # （表头在 thead 多一个 # 列，数据行 tbody 无 # 列）
            # 线路=td[0], IP=td[1], 延迟=td[3]（如 136.85ms）
            soup = BeautifulSoup(text, 'html.parser')
            count = 0
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 4:
                    continue
                line = tds[0].get_text(strip=True)
                ip = tds[1].get_text(strip=True)
                if not re.fullmatch(ip_pattern, ip):
                    continue
                latency = parse_latency(tds[3].get_text(strip=True))
                add_ip(ip, line, latency)
                count += 1
            print(f"  从{url}找到{count}个IP")
            time.sleep(1)
            continue

        if url == 'https://www.wetest.vip/page/cloudflare/address_v4.html':
            # 数据行 td: [线路, IP, 网络带宽, 峰值速度, 往返延迟, 数据中心, 更新时间]
            # 线路=td[0], IP=td[1], 延迟=td[4]（如 121 毫秒）
            soup = BeautifulSoup(text, 'html.parser')
            count = 0
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 5:
                    continue
                line = tds[0].get_text(strip=True)
                ip = tds[1].get_text(strip=True)
                if not re.fullmatch(ip_pattern, ip):
                    continue
                latency = parse_latency(tds[4].get_text(strip=True))
                add_ip(ip, line, latency)
                count += 1
            print(f"  从{url}找到{count}个IP")
            time.sleep(1)
            continue

    except requests.exceptions.Timeout:
        print(f"处理 {url} 时超时，跳过")
    except Exception as e:
        print(f"处理 {url} 时出错：{e}")

# 写入 ip.txt，格式 `IP#线路#延迟`，按 (线路, 延迟升序, IP) 排序
# 延迟为 None 时写空，排序时 None 排在该线路最后
def sort_key(item):
    (ip, line), latency = item
    return (line, latency if latency is not None else float('inf'), ip)


dropped = 0
with open('ip.txt', 'w', encoding='utf-8') as file:
    for (ip, line), latency in sorted(all_ips.items(), key=sort_key):
        # 丢弃延迟超过阈值的 IP（无延迟 None 的保留，排在该线路最后）
        if latency is not None and latency > MAX_LATENCY:
            dropped += 1
            continue
        lat_str = f'{latency:g}' if latency is not None else ''
        file.write(f'{ip}#{line}#{lat_str}\n')

kept = len(all_ips) - dropped
unique_ip_count = len({ip for (ip, _) in all_ips.keys()})
print(f'总共 {len(all_ips)} 条线路记录：保留 {kept} 条，丢弃 {dropped} 条（延迟>{MAX_LATENCY:g}ms）')
print(f'唯一IP {unique_ip_count} 个，已保存到 ip.txt。')
