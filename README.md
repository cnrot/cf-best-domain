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
- [ip.txt 格式](#iptxt-格式)
- [工作原理](#工作原理)
- [常见问题](#常见问题)

---

## 功能

- ✅ 自动从多个网站抓取 Cloudflare 优选 IP（`ip.txt`）
- ✅ 抓取结果包含**运营商线路 + 延迟**，按延迟升序排列
- ✅ 自动丢弃延迟 **>150ms** 的 IP，优先使用 **90ms 以下** 的 IP 做解析
- ✅ 自动把优选 IP 写入 DNS 解析记录，子域名始终指向最快的 IP
  - 支持 **多云厂商**：目前支持 Cloudflare、华为云国际版
  - 支持 **多域名**：一个配置文件管理多个域名
  - 支持 **区域选择**：华为云等区域型厂商，每个域名可独立配置 `region` / `project_id` / `line`（解析线路）
  - 支持 **多线路分组**：华为云可设 `line: 电信,联通,移动`，每条运营商线路单独一个记录集、各用最低延迟 IP
- ✅ 控制解析数量：每个子域名最多添加几个 IP，可自行配置（默认 10，上限 10）
- ✅ 采集 IP 数量不足时，自动删除多余的旧 DNS 记录
- ✅ 敏感域名可从 `config.yml` 隐藏，通过环境变量（GitHub Secrets）注入
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
  - **Cloudflare**：在 [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) 创建「编辑 DNS」权限的令牌（需同时有 `Zone:Read` 权限，用于查找域名；用于新增/删除解析记录）
  - **华为云国际版**：Access Key ID + Secret Access Key（用于签名调用华为云 DNS API）

### 2. 配置

编辑 `config.yml`：

1. 改 `ip_source` 为**你仓库里 `ip.txt` 的 Raw 链接**（格式见下方）
2. 在 `domains` 里按需填你要同步的厂商、域名和子域名


### 3. 部署到 GitHub Actions

1. 配置环境变量，转到 **Settings → Secrets and variables → Actions** ：

   | Secret 名 | 说明 |
   |-----------|------|
   | `CF_API_TOKEN` | Cloudflare 令牌（需 `Zone:Read` + `DNS:Edit` 权限） |
   | `CF_ZONE` | (可选) 你托管在 Cloudflare 的域名，配合 `zone_env` 隐藏真实域名 |
   | `HUAWEICLOUD_SDK_AK` | 华为云 Access Key ID |
   | `HUAWEICLOUD_SDK_SK` | 华为云 Secret Access Key |

   > 不用的厂商可以不配，会自动跳过。

2. 两个工作流会自动定时运行：
   - `Fetch IPs`：每 30 分钟抓取优选 IP → 更新 `ip.txt`
   - `Sync DNS`：每小时的 10/40 分把 `ip.txt` 的 IP 同步到各厂商 DNS

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
    zone_env: HUAWEI_ZONE           # (可选) 隐藏域名：zone 留空时从此环境变量读取
    region: ap-southeast-1          # 区域 ID（如香港）
    project_id: 你的项目ID          # 该区域项目 ID（必填）
    line: 电信,联通,移动             # (可选) 解析线路，多线路用逗号分隔
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
| `zone_env` | 域名段 | (可选) 隐藏域名用：`zone` 留空时，从该环境变量读取真实域名（见下文「隐藏域名」） |
| `subdomains` | 域名段 | 要解析的子域名前缀列表；`bestcf` → `bestcf.<zone>` |
| `max_ips` | 域名段 | (可选) 每个子域名最多解析几个 IP，默认 10，上限 10 |
| `ip_source` | 域名段 | (可选) 该域名独立 IP 源，省略用全局 `ip_source` |
| `region` | 域名段 | (区域型厂商必填) 云厂商区域 ID，如华为云 `ap-southeast-1` |
| `project_id` | 域名段 | (区域型厂商必填) 该项目区域的项目 ID |
| `line` | 域名段 | (可选) 解析线路，华为云默认 `default_view`；多线路用逗号分隔，如 `电信,联通,移动` |
| `endpoint` | 域名段 | (可选) 自定义 API 端点，指定则优先于 `region` |

凭据通过环境变量注入（用于 GitHub Secrets），不在 `config.yml` 写明文：
- `CF_API_TOKEN`：Cloudflare 令牌
- `HUAWEICLOUD_SDK_AK` / `HUAWEICLOUD_SDK_SK`：华为云 Access Key ID / Secret Access Key

未注入对应环境变量的厂商会被自动跳过。

### 隐藏域名

若你的仓库是公开的、不想暴露真实托管域名，可把域名段的 `zone` 留空、配 `zone_env` 指向一个环境变量（该变量从 GitHub Secrets 注入），真实域名只存在 Secret 里：

```yaml
domains:
  - provider: cloudflare
    zone: ""              # 留空，不写明文
    zone_env: CF_ZONE     # 真实域名从 Secret CF_ZONE 读取
    subdomains:
      - bestcf
```

- zone 读取优先级：`zone_env` 指定的环境变量 → 域名段 `zone` 明文。
- 未设置相应 Secret 时自动回退到 `zone` 明文；`zone` 也为空则跳过该域名并提示。
- 每个域名段可各自指定不同的 `zone_env`（如 `CF_ZONE`、`HUAWEI_ZONE`），互不影响。

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
    zone_env: HUAWEI_ZONE
    region: ap-southeast-1
    project_id: ca7f0000xxxxxxxx
    line: 电信,联通,移动
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

## ip.txt 格式

`ip.txt` 由 `Fetch IPs` 工作流自动生成，每行一个 IP，格式为：

```
<IP>#<线路>#<延迟>
```

- **线路**：`电信` / `联通` / `移动`（来自上游标注，或 `CM/CU/CT` 归一化）；无线路信息或不区分运营商的标 `ANY`
- **延迟**：毫秒数（如 `57.88`），来自上游公布的测速值；无数值则留空（如 090227 的 IP）
- 文件按 `(线路, 延迟升序)` 排列：延迟低的排前，无延迟的排该线路最后

示例：
```
104.18.35.186#ANY#68.4
162.159.58.65#联通#57.88
198.41.208.14#联通#          # 无延迟（留空）
```

延迟 **>150ms** 的 IP 在采集时被丢弃（阈值见 `collect_ips.py` 顶部 `MAX_LATENCY`）。

---

## 工作原理

1. `Fetch IPs`（`fetch-ips.yml`）每 30 分钟运行 `collect_ips.py`：
   - 从多个网站抓取 Cloudflare 优选 IP（含**线路 + 延迟**）
   - 归一化线路、丢弃 >150ms 的 IP、按延迟升序排序，写入 `ip.txt` 并提交推送到仓库

2. `Sync DNS`（`sync-dns.yml`）每小时的 10/40 分运行 `bestdomain.py`：
   - 读取 `config.yml`，按每个域名的 `provider` 分发到对应厂商插件
   - 从 `ip_source` 拉取 IP 列表，每个子域名取前 `max_ips` 个写入 DNS（延迟低的优先）
   - 记录与目标一致 → 跳过；不一致 → 更新；采集 IP 变少 → 自动删除多余旧记录

---

## 常见问题

**Q：只有部分厂商有凭据，会报错吗？**
不会。未配置凭据的厂商会被自动跳过，其余正常执行。

**Q：`config.yml` 里 `line` 是什么？**
华为云的「解析线路」。默认 `default_view`（全网默认），也可设电信/联通/移动等，让不同运营商访问不同 IP。支持多线路 `line: 电信,联通,移动`，每条线路单独一个记录集，各用延迟最低的 IP。Cloudflare 不支持线路，忽略此参数。

**Q：`max_ips` 太小/太大怎么办？**
每个子域名最多解析 10 个 IP（硬上限）。若 ip.txt 采集的 IP 数量比设定值少，则按实际数量解析，并自动删除多余的旧记录。

**Q：为什么有的 IP 延迟高？**
采集时已丢弃 >150ms 的 IP。90ms 以下的 IP 排最前，DNS 优先使用；若某线路内 <90ms 不够 max_ips，自动续取 90-150ms 的补足。

**Q：公开仓库里不想让人看到我的域名怎么办？**
把该域名段的 `zone` 留空、加 `zone_env` 指向一个环境变量（真实域名放 GitHub Secrets），见上文「隐藏域名」。

**Q：改 `config.yml` 后需要做什么？**
保存后提交推送到 GitHub，`sync-dns.yml` 会在下个定时或手动触发时生效。

---
