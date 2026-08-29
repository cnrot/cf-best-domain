# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

定时抓取 Cloudflare 优选 IP，并自动同步到多云厂商（Cloudflare、华为云国际版）的 DNS 解析记录，让 `bestcf.<域名>` 这类子域名始终指向延迟最低的 IP。整个流程由 GitHub Actions 定时驱动，无需常驻服务器。

## 常用命令

无构建/打包/测试流程，直接运行 Python 脚本。

```bash
# 抓取 Cloudflare 优选 IP，生成 ip.txt（覆盖现有文件）
python collect_ips.py

# 读 config.yml，把 ip.txt 的优选 IP 同步到各厂商 DNS
python bestdomain.py
```

依赖（`pip install`）：
- 采集端：`requests`、`beautifulsoup4`
- 同步端：`requests`、`pyyaml`、`huaweicloudsdkdns`、`huaweicloudsdkcore`

本地运行 `bestdomain.py` 时需先设置环境变量（如 `CF_API_TOKEN=... python bestdomain.py`），因为凭据只从环境变量读取；未配置的厂商会自动跳过，不会报错。

## 架构

项目由两个解耦的入口 + 一个插件体系组成，各自被独立的 GitHub Actions 工作流驱动：

### 1. 采集端 `collect_ips.py`（工作流 `fetch-ips.yml`，每 30 分钟）
- 从 `URLS` 列表抓取多家上游站的 Cloudflare 优选 IP，每站用不同解析逻辑（表格/纯文本）。
- 关键参数在文件顶部：`MAX_LATENCY`（>150ms 丢弃）、`LINE_PREFIX_MAP`（CM/CU/CT→移动/联通/电信）、`normalize_line()` 把线路归一化为 `电信/联通/移动/ANY`。
- 输出 `ip.txt`，行格式 `IP#线路#延迟`，按 `(线路, 延迟升序)` 排序（无延迟的排该线路最后）。
- 脚本会 `os.remove('ip.txt')` 重建文件（Windows 下若本地运行且文件被占用需注意）。

### 2. 同步端主框架 `bestdomain.py`（工作流 `sync-dns.yml`，每小时 10/40 分）
- 读 `config.yml`，抓取全局 IP 列表一次，遍历 `domains` 按 `provider` 分发到插件。
- 凭据统一由 `validate_credentials()` 从环境变量 `<env_var>` 读取（GitHub Secrets 注入），缺失则跳过该厂商；从不由 `config.yml` 读明文密钥。
- zone 读取优先级：域名段 `zone_key` + `zone_env`（环境变量为 JSON 映射 `{"编号":"域名"}`，按 `zone_key` 取）> 仅 `zone_env`（环境变量即该域名）> config.yml 的 `zone` 明文。多域名同账号可用一个 `CF_ZONES` 环境变量 + 各域名不同 `zone_key`。
- `max_ips` 默认 10，硬上限 10。

### 3. 厂商插件体系 `providers/`（核心扩展点）
每个厂商一个模块，实现固定「插件契约」，主框架通过 `PROVIDER_MODULES` 映射 `provider` 名→模块加载：

- `PROVIDER_NAME`：厂商标识（与 config.yml 的 `provider` 一致）
- `PROVIDER_CREDENTIALS`：凭据字段列表（元素为 `{'config_key', 'env_var'}` 或旧式字符串），缺失则主框架跳过
- `merge_domain_config(credentials, domain_config)`：可选，合并域名级参数；返回 `None` 表示该域名缺必要参数
- `OPTIONAL_CONFIG_KEYS`：可选，主框架把这些非凭据配置透传进 credentials
- `lookup_zone(credentials, target_domain) -> (zone_id, zone_name)`
- `update_zone_records(credentials, zone_id, zone_name, subdomains, ip_list, max_ips)`

**新增云厂商**：在 `providers/` 新建同名 `.py` 实现上述契约，把它加进 `bestdomain.py` 的 `PROVIDER_MODULES` 即可；无凭据配置时自动跳过。

### 插件差异（重要）
- `cloudflare.py`：无线路概念，按延迟升序合并去重取前 `max_ips` 个；策略为「删掉不在目标集的旧记录 + 补缺失新 IP」。
- `huaweicloud.py`：区域型厂商，用官方 SDK（`huawei_sdk_client.py` 薄封装）。支持 `line` 解析线路（单值/逗号多线路），每条线路一个记录集；`project_id` 必填。记录集一致则 Keep，不一致则 Update，失败则删除重建。
- `huawei_sdk_client.py`：华为云 SDK 封装，含区域表兜底（`_REGION_FALLBACK`），仅被 `huaweicloud.py` 使用。

## 配置

`config.yml` 是所有行为的源头：
- 顶层 `ip_source`：默认优选 IP 源 URL（也可用环境变量 `IP_SOURCE_URL` 覆盖）；域名段可各自覆盖 `ip_source`。
- `providers`：各厂商非凭据默认值段。
- `domains`：要同步的域名列表，关键字段 `provider` / `zone_env` / `subdomains` / `max_ips` / `ip_source`，区域型厂商还有 `region` / `project_id_env` / `line` / `endpoint`；多域名同账号时加 `zone_key`（配 `zone_env` 指向 JSON 映射环境变量）。

设计约束：**真实域名、项目 ID 一律通过 GitHub Secrets 注入环境变量**（避免公开仓库泄露），`zone_env` / `project_id_env` 指向对应环境变量名。详见 README 的环境变量表。

## 工作流

- `fetch-ips.yml`：`cron '*/30 * * * *'` 跑 `collect_ips.py` 并把 `ip.txt` 用 bot 账号 commit+push 回仓库。
- `sync-dns.yml`：`cron '10,40 * * * *'`（错开采集约 10 分钟等 Raw 缓存刷新）跑 `bestdomain.py`，把所有 Secrets 注入环境。
- **改环境变量时注意**：`sync-dns.yml` 的 `env:` 是硬编码的环境变量名清单，新增环境变量（如新域名）必须同步加进该文件；引用不存在的 Secret 会得到空串、无害（该域名被自动跳过）。`CF_ZONES` / `HUAWEI_ZONES` 已预置用于多域名 JSON 映射。
- 两者都支持 `workflow_dispatch` 手动触发。
