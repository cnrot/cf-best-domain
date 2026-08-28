"""Cloudflare DNS 插件。

config.yml 中 provider 写 cloudflare。
凭据字段：api_token（CF_API_TOKEN），从 GitHub Secrets 注入环境变量。
"""
import os

import requests

PROVIDER_NAME = 'cloudflare'

# 凭据来源规则（由主框架统一解析）：
# config.yml 里 providers.cloudflare.<config_key>   → 明文
# 环境变量 <env_var>                                → 运行时注入（GitHub Secrets / Docker -e）
PROVIDER_CREDENTIALS = [
    {
        'config_key': 'api_token',
        'env_var': 'CF_API_TOKEN',
    },
]

# 可选的额外配置（providers.cloudflare 下，由主框架透传进 credentials）
OPTIONAL_CONFIG_KEYS = []


def get_zone_id_by_domain(api_token, target_domain):
    """列出账号下所有 zone，精确匹配目标域名，返回 (zone_id, zone_name)。"""
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
    }
    page = 1
    while True:
        response = requests.get(
            f'https://api.cloudflare.com/client/v4/zones?per_page=50&page={page}',
            headers=headers
        )
        response.raise_for_status()
        result = response.json()
        zones = result.get('result', [])

        for zone in zones:
            if zone['name'] == target_domain:
                return zone['id'], zone['name']

        total_pages = result.get('result_info', {}).get('total_pages', 1)
        if page >= total_pages:
            break
        page += 1

    raise Exception(f'在 Cloudflare 账号下未找到域名 {target_domain}。'
                    f'请确认该域名已托管到 Cloudflare，且令牌对该域名有编辑权限。')


def list_dns_records(api_token, zone_id, record_name):
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
    }
    response = requests.get(
        f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type=A&name={record_name}',
        headers=headers
    )
    response.raise_for_status()
    return response.json().get('result', [])


def create_dns_record(api_token, zone_id, record_name, ip):
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
    }
    data = {
        "type": "A",
        "name": record_name,
        "content": ip,
        "ttl": 1,
        "proxied": False
    }
    response = requests.post(
        f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records',
        json=data,
        headers=headers
    )
    return response.status_code == 200


def delete_dns_record(api_token, zone_id, record_id, record_ip):
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
    }
    response = requests.delete(
        f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}',
        headers=headers
    )
    return response.status_code == 200


# ---- 主框架契约函数 ----

def lookup_zone(credentials, target_domain):
    """主框架契约：定位域名在 CF 账号下的 zone，返回 (zone_id, zone_name)。"""
    api_token = credentials['api_token']
    return get_zone_id_by_domain(api_token, target_domain)


def update_zone_records(credentials, zone_id, zone_name, subdomains, ip_list, max_ips):
    """主框架调用：为该域名下所有子域名同步 A 记录到 ip_list（前 max_ips 个）。

    规则：先删除不在本次 IP 列表里的旧记录（数量不足时自动清多余），再补缺失的新 IP。
    """
    api_token = credentials['api_token']
    # ip_list 为 [(ip, line), ...]；CF 无线路概念，去线路后按唯一 IP 取前 max_ips 个
    unique_ips = []
    seen = set()
    for item in ip_list:
        ip = item[0] if isinstance(item, (tuple, list)) else item
        if ip not in seen:
            seen.add(ip)
            unique_ips.append(ip)
    max_ips = max_ips or len(unique_ips) if max_ips else len(unique_ips)
    target_ips = unique_ips[:max_ips]
    target_ip_set = set(target_ips)

    print(f"  目标 IP {len(target_ips)} 个（来自 ip.txt 前 {max_ips} 个）")

    for subdomain in subdomains:
        record_name = zone_name if subdomain == '@' else f'{subdomain}.{zone_name}'
        print(f"  更新子域名 {record_name}")

        # 读取现有记录
        try:
            records = list_dns_records(api_token, zone_id, record_name)
        except Exception as e:
            print(f"    读取记录失败: {e}")
            continue

        existing_ips = {r['content'] for r in records}

        # 1) 删除多余/过期记录（不在本次目标集里的）
        for record in records:
            if record['content'] not in target_ip_set:
                ok = delete_dns_record(api_token, zone_id, record['id'], record['content'])
                print(f"    Del {record['content']} {'成功' if ok else '失败'}")
            else:
                print(f"    Keep {record['content']}")

        # 2) 补缺失的新 IP
        for ip in target_ips:
            if ip in existing_ips:
                print(f"    Skip {ip} (已存在)")
                continue
            ok = create_dns_record(api_token, zone_id, record_name, ip)
            print(f"    Add {ip} {'成功' if ok else '失败'}")