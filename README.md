# cf-best-domain

定时抓取 Cloudflare 优选 IP，并把它们自动同步到 DNS 解析记录，让 `bestcf.example.com` 这类子域名始终指向延迟最低的 IP。

---

## 目录

- [功能](#功能)
- [目录结构](#目录结构)
- [使用方法](#使用方法)
  - [1. 准备](#1-准备)
  - [2. 配置](#2-配置)
  - [3. 部署到 GitHub Actions](#3-部署到-github-actions)
- [config.yml 配置说明](#configyml-配置说明)
  - [字段说明](#字段说明)
  - [完整示例](#完整示例)
  - [常见配置错误](#常见配置错误)
- [工作原理](#工作原理)
- [常见问题](#常见问题)

---

## 功能

- ✅ 自动从多个网站抓取 Cloudflare 优选 IP（`ip.txt`）
- ✅ 自动把优选 IP 写入 DNS 解析记录，子域名始终指向最快的 IP
  - 支持 **多云厂商**：目前支持 Cloudflare、华为云国际版
  - 支持 **多域名**：一个配置文件管理多个域名
  - 支持 **区域选择**：华为云等区域型厂商，每个域名可独立配置 `region` / `project_id` / `line`（解析线路）
- ✅ 控制解析数量：每个子域名最多添加几个 IP，可自行配置（默认 10，上限 10）
- ✅ 采集 IP 数量不足时，自动删除多余的旧 DNS 记录
- ✅ 每 30 分钟自动运行一次（可改）

---

## 目录结构

```
.
├── bestdomain.py            # 主框架：读 config.yml，分发到各厂商插件
├── collect_ips.py           # 抓取优选 IP，生成 ip.txt
├── config.yml                # 配置文件（你需要改的地方）
├── ip.txt                    # 抓取到的优选 IP 列表（由 Actions 自动更新）
├── providers/                # 各云厂商插件目录
│   ├── cloudflare.py      # Cloudflare 插件
│   ├── huaweicloud.py     # 华为云国际版插件
│   └── huawei_sdk_client.py # 华为云 SDK 封装
└── .github/workflows/
    ├── fetch-ips.yml           # 定时抓取 IP 并更新 ip.txt
    └── sync-dns.yml            # 定时把 ip.txt 的 IP 同步到 DNS
```

---

## 使用方法

### 1. 准备

- 一个 **GitHub 仓库**（fork本项目）
- 至少一家云厂商的 DNS 服务及 **API 凭据**：
  - **Cloudflare**：在 [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) 创建「编辑 DNS」权限的令牌（用于新增/删除解析记录）
  - **华为云国际版**：Access Key ID + Secret Access Key（用于签名调用华为云 DNS API）

### 2. 配置

编辑 `config.yml`：

1. 改 `ip_source` 为**你仓库里 `ip.txt` 的 Raw 链接**（格式见下方）
2. 在 `domains` 里按需填你要同步的厂商、域名和子域名


### 3. 部署到 GitHub Actions

1. 配置环境变量，转到 **Settings → Secrets and variables → Actions** ：

   | Secret 名 | 说明 |
   |-----------|------|
   | `CF_API_TOKEN` | Cloudflare 令牌（编辑 DNS 权限） |
   | `HUAWEICLOUD_SDK_AK` | 华为云 Access Key ID |
   | `HUAWEICLOUD_SDK_SK` | 华为云 Secret Access Key |

   > 不用的厂商可以不配，会自动跳过。

2. 两个工作流会各每 30 分钟自动运行：
   - `Fetch IPs`：抓取优选 IP → 更新 `ip.txt`
   - `Sync DNS`：把 `ip.txt` 的 IP 同步到各厂商 DNS

3. 也可在仓库 **Actions** 页面手动触发 `workflow_dispatch`。

---

## config.yml 配置说明

### 结构总览

```yaml
ip_source: 全局默认优选IP源          # 每行一个 IP 的文本网址（必须）

providers:                          # 各厂商非凭据可选默认值（凭据用 Secrets 注入，不写在这里）
  cloudflare: {}                    # 凭据用 Secrets 的 CF_API_TOKEN 注入
  huaweicloud:                      # 凭据用 Secrets 的 HUAWEICLOUD_SDK_AK / _SK 注入
    # region: ap-southeast-1        # (可选) 默认区域，也可在每个域名段单独写

domains:                            # 要更新的域名列表
  - provider: cloudflare            # 用哪个厂商
    zone: example.com               # 该厂商下绑定的站点域名
    subdomains:                     # 要解析的子域名前缀
      - bestcf
      - api
    max_ips: 5                      # (可选) 每个子域名最多几个 IP

  - provider: huaweicloud           # 区域型厂商示例
    zone: second.com
    region: ap-southeast-1          # 区域 ID（如香港）
    project_id: 你的项目ID          # 该区域项目 ID（必填）
    line: default_view              # (可选) 解析线路
    subdomains:
      - cdn
```

### 字段说明

| 字段 | 位置 | 含义 |
|------|------|------|
| `ip_source` | 顶层 | 全局默认优选 IP 来源（每行一个 IP 的文本网址） |
| `providers` | 顶层 | 各厂商非凭据可选默认值段（凭据用环境变量注入，不写在此） |
| `domains` | 顶层 | 要更新的域名列表 |
| `provider` | 域名段 | 用哪个厂商（如 `cloudflare`、`huaweicloud`） |
| `zone` | 域名段 | 该厂商下绑定的**站点域名**（必须与该厂商后台注册的一致） |
| `subdomains` | 域名段 | 要解析的子域名前缀列表；`bestcf` → `bestcf.<zone>` |
| `max_ips` | 域名段 | (可选) 每个子域名最多解析几个 IP，默认 10，上限 10 |
| `ip_source` | 域名段 | (可选) 该域名独立 IP 源，省略用全局 `ip_source` |
| `region` | 域名段 | (区域型厂商必填) 云厂商区域 ID，如华为云 `ap-southeast-1` |
| `project_id` | 域名段 | (区域型厂商必填) 该项目区域的项目 ID |
| `line` | 域名段 | (可选) 解析线路，华为云默认 `default_view`，可设为电信/联通/移动等 |
| `endpoint` | 域名段 | (可选) 自定义 API 端点，指定则优先于 `region` |

凭据通过环境变量注入（用于 GitHub Secrets），不在 `config.yml` 写明文：
- `CF_API_TOKEN`：Cloudflare 令牌
- `HUAWEICLOUD_SDK_AK` / `HUAWEICLOUD_SDK_SK`：华为云 Access Key ID / Secret Access Key

未注入对应环境变量的厂商会被自动跳过。

### 完整示例

```yaml
# 全局默认 IP 源：你仓库里 ip.txt 的 Raw 链接
# 获取方法：GitHub 打开 ip.txt → 点右上角 Raw → 复制浏览器地址栏链接
ip_source: https://raw.githubusercontent.com/用户名/仓库名/refs/heads/main/ip.txt

providers:
  cloudflare: {}           # 凭据用 Secrets 的 CF_API_TOKEN 注入
  huaweicloud:             # 凭据用 Secrets 的 HUAWEICLOUD_SDK_AK / _SK 注入
    # region: ap-southeast-1

domains:
  - provider: cloudflare
    zone: example.com
    subdomains:
      - bestcf
      - api
    max_ips: 5

  - provider: huaweicloud
    zone: second.com
    region: ap-southeast-1
    project_id: ca7f0000xxxxxxxx
    line: default_view
    subdomains:
      - cdn
      - download
    max_ips: 3
```

### 常见配置错误

| ❌ 错误写法 | ✅ 正确写法 |
|------------|------------|
| `zone: *.example.com` | `zone: example.com` |
| `zone: bestcf`（漏了主域名） | `zone: example.com`，把 `bestcf` 写进 `subdomains` |
| `subdomains` 里写 `bestcf.example.com` | 写前缀 `bestcf` |
| 域名段设了 `provider: cloudflare` 但没配凭据 | 在 GitHub Secrets 配好 `CF_API_TOKEN` |
| 华为云域名漏写 `project_id` | 补 `project_id`（否则该域名被跳过并提示） |

---

## 工作原理

1. `Fetch IPs`（`fetch-ips.yml`）每 30 分钟运行 `collect_ips.py`：
   - 从配置的多个网站抓取 Cloudflare 优选 IP
   - 去重、排序后写入 `ip.txt` 并提交推送到仓库

2. `Sync DNS`（`sync-dns.yml`）每 30 分钟运行 `bestdomain.py`：
   - 读取 `config.yml`，按每个域名的 `provider` 分发到对应厂商插件
   - 从 `ip_source` 拉取 IP 列表，每个子域名取前 `max_ips` 个写入 DNS
   - 记录与目标一致 → 跳过；不一致 → 更新；采集 IP 变少 → 自动删除多余旧记录

---

## 常见问题

**Q：只有部分厂商有凭据，会报错吗？**
不会。未配置凭据的厂商会被自动跳过，其余正常执行。

**Q：`config.yml` 里 `line` 是什么？**
华为云的「解析线路」。默认 `default_view`（全网默认），也可设电信/联通/移动等，让不同运营商访问不同 IP。Cloudflare 不支持线路，忽略此参数。

**Q：`max_ips` 太小/太大怎么办？**
每个子域名最多解析 10 个 IP（硬上限）。若 ip.txt 采集的 IP 数量比设定值少，则按实际数量解析，并自动删除多余的旧记录。

**Q：改 `config.yml` 后需要做什么？**
保存后提交推送到 GitHub，`sync-dns.yml` 会在下个定时或手动触发时生效。

---
