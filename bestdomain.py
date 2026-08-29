"""主框架：读取 config.yml，按 provider 分发到各 DNS 厂商插件。

每个厂商一个插件文件（providers/<厂商>.py），通过插件契约对接：
- PROVIDER_NAME      厂商标识（与 config.yml 中 provider 一致）
- PROVIDER_CREDENTIALS 该厂商需要的凭据字段列表（dict: config_key + env_var；缺失则跳过）
- lookup_zone(credentials, target_domain) -> (zone_id, zone_name)
- update_zone_records(credentials, zone_id, zone_name, subdomains, ip_list, max_ips)

凭据读取由主框架 validate_credentials 统一完成：从环境变量 <env_var> 读取
（GitHub Secrets / Docker -e 注入），不在 config.yml 存放明文密钥。

新增云厂商：在 providers/ 下新建同名 .py 实现上述契约，注册到 PROVIDER_MODULES 即可，
主框架会自动在有凭据配置时调用、无配置时跳过。
"""
import importlib
import json
import os
import traceback

import requests
import yaml

CONFIG_FILE = 'config.yml'
MAX_IPS_DEFAULT = 10          # 每个子域名默认最多解析的 IP 数量
MAX_IPS_CAP = 10              # 硬上限
IP_SOURCE_DEFAULT_ENV = 'IP_SOURCE_URL'   # 允许通过环境变量给默认 IP 源

# 插件清单：厂商标识 -> 插件模块名
PROVIDER_MODULES = {
    'cloudflare': 'providers.cloudflare',
    'huaweicloud': 'providers.huaweicloud',
}


def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not data or 'domains' not in data:
        raise Exception(f'{CONFIG_FILE} 缺少 domains 配置，请检查格式')
    return data


def get_ip_list(url):
    """抓取 IP 源，返回 [(ip, line, latency), ...]。

    支持行格式：
      - `IP#线路#延迟`  带运营商线路 + 延迟(ms，可为空)
      - `IP#线路`       带线路，无延迟
      - `IP`            无线路无延迟，按 ANY 处理
    文件内已按 (线路, 延迟升序) 排序，调用方可直接取前 N 个作为优选。
    """
    response = requests.get(url)
    response.raise_for_status()
    result = []
    for raw in response.text.strip().split('\n'):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split('#')
        ip = parts[0].strip()
        line = parts[1].strip() if len(parts) > 1 and parts[1].strip() else 'ANY'
        latency = None
        if len(parts) > 2 and parts[2].strip():
            try:
                latency = float(parts[2].strip())
            except ValueError:
                latency = None
        if ip:
            result.append((ip, line, latency))
    return result


def load_provider_module(provider_name):
    """加载厂商插件模块；未注册则返回 None。"""
    module_name = PROVIDER_MODULES.get(provider_name)
    if not module_name:
        raise NotImplementedError(f'不支持的云厂商: {provider_name}')
    return importlib.import_module(module_name)


def validate_credentials(module, provider_config):
    """检查该厂商所需凭据是否齐全；缺失返回 None，否则返回凭据 dict。

    凭据从环境变量 <env_var> 读取（GitHub Secrets / Docker -e 注入），
    不在 config.yml 存放明文密钥。
    """
    cred_specs = getattr(module, 'PROVIDER_CREDENTIALS', [])
    if not cred_specs:
        return {}

    # 兼容旧式字符串写法：把 ["CF_API_TOKEN"] 转成 [{'config_key':'api_token','env_var':'CF_API_TOKEN'}]
    normalized = []
    for spec in cred_specs:
        if isinstance(spec, str):
            normalized.append({
                'config_key': spec.lower(),
                'env_var': spec,
            })
        elif isinstance(spec, dict):
            normalized.append(spec)

    provider_config = provider_config or {}
    missing = []
    creds = {}

    for spec in normalized:
        config_key = spec.get('config_key')
        env_var = spec.get('env_var')

        value = None
        # 1) 环境变量（最高优先）
        if env_var:
            value = os.getenv(env_var)
        # 2) config.yml 明文
        if not value and config_key:
            value = provider_config.get(config_key)

        if value:
            creds[config_key or env_var] = str(value).strip()
        else:
            missing.append(f'{config_key or env_var}')

    if missing:
        print(f'  [跳过] 厂商 {getattr(module, "PROVIDER_NAME", "?")} 未配置凭据: {missing}')
        return None
    return creds


def process_domain(module, provider_id, credentials, domain_config, ip_list):
    """对单个域名执行「校验域名 - 同步记录」。"""
    # 允许插件在域名级合并自己的区域/端点等参数（如华为云的 region/project_id）
    if hasattr(module, 'merge_domain_config'):
        credentials = module.merge_domain_config(credentials, domain_config)
        if credentials is None:
            print('  跳过：域名级参数缺失（如 project_id）')
            return

    # zone 读取优先级：
    #   1) 域名段 zone_key + zone_env → 把环境变量当作 JSON 映射 {"key": "zone"}，按 zone_key 取值
    #      （用于多域名同账号场景：所有真实域名塞进同一个 Secret，域名段用 zone_key 区分）
    #   2) zone_env 指定的环境变量（直接是该域名 zone）
    #   3) config.yml zone 明文
    # 这样公开仓库可把真实域名隐藏，通过 GitHub Secrets 注入环境变量。
    zone = ''
    zone_env = domain_config.get('zone_env', '').strip()
    zone_key = domain_config.get('zone_key', '').strip()
    raw = os.getenv(zone_env, '').strip() if zone_env else ''
    if zone_key and raw:
        import json
        try:
            mapping = json.loads(raw)
            zone = str(mapping.get(zone_key, '')).strip() if isinstance(mapping, dict) else ''
        except json.JSONDecodeError:
            zone = ''
    elif zone_env:
        zone = raw
    if not zone:
        zone = domain_config.get('zone', '').strip()
    if zone_key and not zone:
        print(f'  跳过：zone 为空（Secret {zone_env} 里缺少 zone_key={zone_key}，'
              f'或它不是合法的 JSON 映射）')
        return
    subdomains = domain_config.get('subdomains', []) or []
    if not subdomains:
        print('  跳过：subdomains 为空')
        return
    if not zone:
        print(f'  跳过：zone 为空（未设置 {zone_env or "zone"} 环境变量，config.yml 也未填 zone）')
        return

    max_ips = domain_config.get('max_ips', MAX_IPS_DEFAULT)
    try:
        max_ips = min(int(max_ips), MAX_IPS_CAP)
    except (TypeError, ValueError):
        max_ips = MAX_IPS_DEFAULT

    print(f"\n=== [{provider_id}] 处理域名 {zone} ===")

    # 定位域名在该厂商下的 zone
    try:
        zone_id, zone_name = module.lookup_zone(credentials, zone)
    except Exception as e:
        print(f"  跳过 {zone}：查找域名失败 {e}")
        return
    print(f"  找到 zone: {zone_name} ({zone_id})")

    # 调用厂商插件的同步函数
    try:
        module.update_zone_records(credentials, zone_id, zone_name, subdomains, ip_list, max_ips)
    except Exception as e:
        print(f"  更新失败: {e}")
        traceback.print_exc()


def main():
    config = load_config()
    providers_config = config.get('providers', {}) or {}
    domains = config['domains']

    # 读取默认 IP 源（环境变量优先，其次 config 顶层 ip_source，最后报错）
    default_ip_source = (
        os.getenv(IP_SOURCE_DEFAULT_ENV)
        or config.get('ip_source')
    )
    if not default_ip_source:
        raise Exception('未设置 IP 源：请在 config.yml 顶层加 ip_source，'
                        '或设置环境变量 IP_SOURCE_URL')

    # 抓取全局 IP 列表一次，供所有域名/厂商共用
    try:
        ip_list = get_ip_list(default_ip_source)
    except Exception as e:
        print(f"抓取 IP 失败: {e}")
        return
    print(f"共获取到 {len(ip_list)} 个优选 IP")

    # 按域名分发到对应厂商插件
    for domain_config in domains:
        provider_id = (domain_config.get('provider') or 'cloudflare').strip().lower()
        try:
            module = load_provider_module(provider_id)
        except NotImplementedError as e:
            print(f"[跳过] {e}")
            continue

        provider_config = providers_config.get(provider_id, {})
        credentials = validate_credentials(module, provider_config)
        if not credentials:
            print(f"[跳过] provider={provider_id} 凭据未配置，跳过域名 {domain_config.get('zone')}")
            continue

        # 把厂商可选的额外配置（endpoint/line/ttl 等）透传给插件，供其自行读取
        if hasattr(module, 'OPTIONAL_CONFIG_KEYS'):
            for opt_key in module.OPTIONAL_CONFIG_KEYS:
                if opt_key in provider_config and opt_key not in credentials:
                    credentials[opt_key] = provider_config[opt_key]

        # 域名级 ip_source 可由 config 顶层 ip_source 或环境变量 IP_SOURCE_URL 覆盖（见上方 default_ip_source）
        domain_ip_source = (domain_config.get('ip_source')
                            or os.getenv(IP_SOURCE_DEFAULT_ENV))
        domain_ips = ip_list
        if domain_ip_source and domain_ip_source != default_ip_source:
            try:
                domain_ips = get_ip_list(domain_ip_source)
                print(f"  域名 {domain_config.get('zone')} 使用独立 IP 源: {domain_ip_source}")
            except Exception as e:
                print(f"  域名 {domain_config.get('zone')} 获取独立 IP 失败: {e}")
                continue

        process_domain(module, provider_id, credentials, domain_config, domain_ips)


if __name__ == "__main__":
    main()