"""华为云（国际版）DNS 插件 —— 基于官方 SDK。

config.yml 中 provider 写 huaweicloud。
认证：AK/SK（环境变量 HUAWEICLOUD_SDK_AK/SK 或 config 明文）。
区域型参数（每个域名独立）：
  - region       区域 ID，如 ap-southeast-1（香港）、cn-north-4 等，默认 ap-southeast-1
  - project_id   该区域的项目 ID（必须，否则 SDK 无法定位项目）
  - endpoint     (可选) 自定义端点，指定则优先于 region
记录集：华为云一个 (name, line) 对应一个记录集，records 是多个 IP 数组。
创建/更新统一走 create_record_set_with_line（带 line），支持解析线路选择。
"""
import time

from .huawei_sdk_client import HuaweiDnsClient

PROVIDER_NAME = 'huaweicloud'

PROVIDER_CREDENTIALS = [
    {'config_key': 'access_key', 'env_var': 'HUAWEICLOUD_SDK_AK'},
    {'config_key': 'secret_key', 'env_var': 'HUAWEICLOUD_SDK_SK'},
]

# 域名级可选参数：region / project_id / endpoint / line / ttl
# project_id 只在校验域名时检查（可能来自域名段或环境变量）
OPTIONAL_CONFIG_KEYS = ['region', 'endpoint', 'line', 'ttl']

DEFAULT_REGION = 'ap-southeast-1'
DEFAULT_TTL = 300
DEFAULT_LINE = 'default_view'  # 华为云默认解析线路


def _note_domain(domain: str) -> str:
    return domain if domain.endswith('.') else domain + '.'


def _strip_dot(domain: str) -> str:
    return domain[:-1] if domain.endswith('.') else domain


def merge_domain_config(credentials, domain_config):
    """主框架在 process_domain 开头调用：把域名级 region/endpoint/project_id 合并进凭据。

    返回 None 表示该域名缺必要参数（如华为云必须的 project_id）。
    """
    merged = dict(credentials)
    domain_cfg = domain_config or {}
    for key in ('region', 'endpoint', 'line', 'ttl', 'project_id'):
        val = domain_cfg.get(key)
        if val:
            merged[key] = val

    # 华为云 SDK 需要 project_id，缺失则跳过该域名
    if not merged.get('project_id'):
        print('  [跳过] 华为云域名缺少 project_id（请在域名段或环境变量 HUAWEICLOUD_SDK_PROJECT_ID 配置）')
        return None
    return merged


def _build_client(credentials):
    """构建 SDK 客户端；配置错误(区域/端点/AK/SK)抛出带明确提示的异常。"""
    try:
        return HuaweiDnsClient(credentials)
    except Exception as e:
        raise Exception(f'华为云配置错误(检查 AK/SK/project_id/region/endpoint): {e}')


def lookup_zone(credentials, target_domain):
    client = _build_client(credentials)
    try:
        zones = client.list_public_zones()
    except Exception as e:
        raise Exception(f'华为云查询域名失败: {e}')

    target = _strip_dot(target_domain.strip())
    for zone in zones:
        if _strip_dot(zone.name) == target:
            return zone.id, _strip_dot(zone.name)
    raise Exception(f'在华为云账号下未找到公网域名 {target_domain}，'
                    f'请确认已托管且 AK/SK/project_id 有权限')


def update_zone_records(credentials, zone_id, zone_name, subdomains, ip_list, max_ips):
    """主框架调用：把优选 IP 同步到该域名下所有子域名，支持多线路分组。

    line 配置（credentials['line']）可为：
      - 单值字符串  如 'default_view' 或 '电信'           → 所有目标 IP 进这一条线路
      - 逗号分隔    如 '电信,联通,移动'                   → 每条线路一个记录集
      - 列表        如 ['电信','联通','移动']              → 同上
    多线路分组时：每条线路取该线路的优选 IP（按延迟升序），不足 max_ips 个用 ANY 通用 IP 补足。
    ip.txt 行格式为 `IP#线路#延迟`，无延迟的排在该线路最后。

    策略（始终走 with_line 接口）：
    - (name, line) 记录集 records 一致 → Keep；不一致 → PUT 改写；失败 → 删除重建
    - 仅清理本工具管理的 (name, line) 记录，绝不碰用户其它记录
    """
    client = _build_client(credentials)
    zone_dot = _note_domain(zone_name)
    ttl = int(credentials.get('ttl') or DEFAULT_TTL)

    # 解析目标线路列表（单值 / 逗号分隔 / 列表）
    line_cfg = credentials.get('line') or DEFAULT_LINE
    if isinstance(line_cfg, (list, tuple)):
        target_lines = [str(x).strip() for x in line_cfg if str(x).strip()]
    else:
        target_lines = [x.strip() for x in str(line_cfg).split(',') if x.strip()]
    if not target_lines:
        target_lines = [DEFAULT_LINE]

    # ip_list 为 [(ip, line, latency), ...]，按线路标签分组；组内按延迟升序（无延迟排后）
    line_ips = {}
    for item in ip_list:
        if isinstance(item, (tuple, list)):
            ip, tag = item[0], item[1]
            lat = item[2] if len(item) > 2 else None
        else:
            ip, tag, lat = item, 'ANY', None
        line_ips.setdefault(tag, []).append((ip, lat if lat is not None else float('inf')))
    for tag in line_ips:
        line_ips[tag].sort(key=lambda x: (x[1], x[0]))
    any_ips = [ip for ip, _ in line_ips.get('ANY', [])]

    # 每条目标线路：本线路优选 IP（延迟升序）+ 不足用 ANY 补足，去重后截 max_ips
    max_ips = max_ips or max((len(v) for v in line_ips.values()), default=1)
    plan = {}
    for ln in target_lines:
        ips, seen = [], set()
        for ip, _ in list(line_ips.get(ln, [])) + list(line_ips.get('ANY', [])):
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
        plan[ln] = ips[:max_ips]

    print(f"  目标线路 {target_lines}；每线路上限 {max_ips} IP；TTL={ttl}s；"
          f"region={credentials.get('region') or DEFAULT_REGION}")
    for ln in target_lines:
        print(f"    {ln}: {len(plan[ln])} 个 IP")

    # 期望记录：(name, line) -> 目标 IP 列表
    expected = {}
    for sub in subdomains:
        name = _note_domain(zone_name if sub == '@' else f'{sub}.{zone_name}')
        for ln in target_lines:
            expected[(name, ln)] = plan[ln]

    # 读取带 line 的全部记录集
    try:
        recordsets = client.list_recordsets_with_line(zone_id)
    except Exception as e:
        print(f"  读取记录集失败: {e}")
        return
    a_sets = [r for r in recordsets
              if r.type == 'A' and _note_domain(r.name).endswith(zone_dot)]

    managed_names = {name for (name, _) in expected}
    expected_keys = set(expected.keys())

    def _find(name, ln):
        """在本域名 A 记录里按 (name, line) 精确查找。"""
        for r in a_sets:
            if _note_domain(r.name) == name:
                r_line = getattr(r, 'line', None) or 'default_view'
                if r_line == ln:
                    return r
        return None

    # 1) 更新/创建每个 (name, line)
    for (record_name, ln), target in sorted(expected.items()):
        existing = _find(record_name, ln)
        cur = existing.records if existing else []
        cur = [str(x) for x in cur] if isinstance(cur, list) else [str(cur)]

        if set(cur) == set(target):
            print(f"    Keep {record_name} [{ln}]（记录一致）")
            continue

        if existing:
            try:
                client.update_recordset(zone_id, existing.id, record_name, 'A', target, ttl)
                print(f"    Update {record_name} [{ln}]: {', '.join(target)}")
                continue
            except Exception as e:
                print(f"    Update 失败({e})，尝试删除重建")
                try:
                    client.delete_recordset(zone_id, existing.id)
                except Exception:
                    pass
                time.sleep(1)

        try:
            client.create_recordset_with_line(zone_id, record_name, 'A', target, ttl, ln)
            print(f"    Create {record_name} [{ln}]: {', '.join(target)}")
        except Exception as e:
            print(f"    创建失败: {e}")

    # 2) 清理：本工具管理的 name 上、(name, line) 已不在期望里的记录
    #    （子域名被移除、或线路缩减时触发），绝不碰用户其它子域名/线路的记录
    for r in a_sets:
        rname = _note_domain(r.name)
        if rname not in managed_names:
            continue
        rline = getattr(r, 'line', None) or 'default_view'
        if (rname, rline) not in expected_keys:
            try:
                client.delete_recordset(zone_id, r.id)
                print(f"    清理不再需要的记录 {r.name} [{rline}]")
            except Exception as e:
                print(f"    清理失败: {e}")