# cf-best-domain

定时抓取 Cloudflare 优选 IP，并把它们自动同步到 DNS 解析记录，让 `bestcf.<你的域名>` 这类子域名始终指向延迟最低的 IP。

> **免责声明**
>
> CloudFlare 明文禁止优选 IP 和 CF 作为代理节点。使用本服务造成账号封禁，本人概不负责。

---

## 目录

- [功能](#功能)
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

- ✅ 自动从多个网站抓取 Cloudflare 优选 IP（`ip.txt`），结果按**运营商线路 + 延迟**、延迟升序排列
- ✅ 自动把优选 IP 写入 DNS 解析记录，子域名始终指向最快的 IP
  - 支持 **多云厂商**：目前支持 Cloudflare、华为云国际版
  - 支持 **多域名**：一个配置文件管理多个域名
  - 支持 **区域选择**：华为云等区域型厂商，每个域名可独立配置 `line: 电信,联通,移动` 解析线路
- ✅ 控制解析数量：每个子域名最多添加几个 IP，可自行配置（默认 10，上限 10）
- ✅ 采集 IP 数量不足时，自动删除多余的旧 DNS 记录
- ✅ 不要把真实域名写进代码/配置：域名放到 GitHub Secrets 的环境变量里，仓库内不留明文
- ✅ 每 30 分钟自动运行一次（可改）

---

## 使用方法

### 1. 准备

- 一个 **GitHub 仓库**（fork本项目）
- 至少一家云厂商的 DNS 服务及 **API 凭据**：
  - **Cloudflare**：在 [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) 创建「编辑 DNS」权限的令牌（需同时有 `Zone:Read` 权限，用于查找域名；用于新增/删除解析记录）
  - **华为云国际版**：Access Key ID + Secret Access Key（用于签名调用华为云 DNS API）

### 2. 配置

编辑 `config.yml`：

1. 改 `ip_source` 为**你仓库里 `ip.txt` 的 Raw 链接**（到你的 GitHub 仓库页面 → 点开 `ip.txt` 文件 → 点右上角 **Raw** 按钮 → 复制浏览器地址栏链接，形如 `https://raw.githubusercontent.com/用户名/仓库名/refs/heads/main/ip.txt`）。程序会从这个链接拉取优选 IP。
2. 在 `domains` 里按需填你要同步的厂商、域名和子域名（具体怎么填见下方「config.yml 配置说明」）。


### 3. 部署到 GitHub Actions

环境变量（Secrets）全部在 **仓库页面 → Settings → Secrets and variables → Actions** 里建：每行环境变量点一次 **New repository secret**，在弹出的 **Name** 框填变量名、**Value** 框填内容，然后保存。要建的环境变量：

   | 环境变量名 | 填什么 | 必配吗 |
   |-----------|--------|--------|
   | `CF_API_TOKEN` | 你的 Cloudflare API 令牌（一长串字符） | 用 Cloudflare 就必配 |
   | `CF_ZONE` | 你的 Cloudflare 域名，如 `a.com` | Cloudflare 单域名用此；也可改用 `CF_ZONES`，见下 |
   | `CF_ZONES` | (可选) 一个装多个 Cloudflare 域名的变量，如 `{"a":"a.com","b":"b.net"}` | 多域名用，见「多域名配置」 |
   | `HUAWEI_ZONE` | 你的华为云域名，如 `hw.com` | 用华为云就必配 |
   | `HUAWEI_ZONE_PROJECT` | 华为云项目 ID | 用华为云就必配 |
   | `HUAWEICLOUD_SDK_AK` | 华为云 Access Key ID | 用华为云就必配 |
   | `HUAWEICLOUD_SDK_SK` | 华为云 Secret Key | 用华为云就必配 |

   > 不用的厂商可以不配它那份，会自动跳过。

2. 建好后不用管，两个任务会自动定时运行：
   - `Fetch IPs`：每 30 分钟抓取优选 IP → 更新 `ip.txt`
   - `Sync DNS`：每小时的 10/40 分把 `ip.txt` 的 IP 同步到各厂商 DNS
   - `fetch-ips.yml`、`sync-dns.yml` 是仓库里两个 `.github/workflows/` 下的任务定义文件，一般不用改。

3. 也可在仓库 **Actions** 页面手动触发 `workflow_dispatch`（点对应任务 → Run workflow）。

---

## config.yml 配置说明
### 完整示例

```yaml
ip_source: https://raw.githubusercontent.com/用户名/仓库名/refs/heads/main/ip.txt  # 优选 IP 的来源网页（每行一个 IP，见上方「2. 配置」怎么获取）

providers:                                    # 各厂商的通用默认设置（一般保持原样即可）
  cloudflare: {}                              # Cloudflare 的令牌在环境变量 CF_API_TOKEN 里，这里不用写
  huaweicloud:                                # 华为云的 Access Key / Secret Key 在环境变量里，这里不用写
    # region: ap-southeast-1                  # (可选) 默认区域，也可在每个域名段单独写

domains:                                      # 要更新的域名列表，每个域名一段
  - provider: cloudflare                      # 用哪个厂商：cloudflare
    zone_env: CF_ZONE                         # 这个域名的真实域名存在环境变量 CF_ZONE 里（先在 GitHub Secrets 建好）
    subdomains:                               # 要解析的子域名前缀（只写前缀，程序自动补全域名）
      - bestcf
      - api
    max_ips: 5                                # (可选) 每个子域名最多解析几个 IP

  - provider: huaweicloud                     # 华为云（区域型厂商）示例
    zone_env: HUAWEI_ZONE                     # 真实域名在环境变量 HUAWEI_ZONE 里（先在 GitHub Secrets 建好）
    region: ap-southeast-1                    # 区域 ID（如香港）
    project_id_env: HUAWEI_ZONE_PROJECT       # 项目 ID 在环境变量 HUAWEI_ZONE_PROJECT 里（必填，先建好）
    line: 电信,联通,移动                       # (可选) 解析线路，多线路用逗号分隔
    subdomains:
      - cdn
      - download
    max_ips: 3
```

### 字段说明

| 字段 | 位置 | 含义 |
|------|------|------|
| `ip_source` | 顶层 | 优选 IP 的来源网页（每行一个 IP 的文本网址） |
| `providers` | 顶层 | 各厂商的通用默认设置（凭据写在环境变量里，不写在此） |
| `domains` | 顶层 | 要更新的域名列表 |
| `provider` | 域名段 | 用哪个厂商（如 `cloudflare`、`huaweicloud`） |
| `zone_env` | 域名段 | 指定环境变量，真实域名从该变量读取（仓库里不写明文域名） |
| `zone_key` | 域名段 | (可选) 一个环境变量装多个域名时用：填编号，程序按编号取出对应域名，见「多域名配置」 |
| `subdomains` | 域名段 | 要解析的子域名前缀列表；`bestcf` → `bestcf.<域名>` |
| `max_ips` | 域名段 | (可选) 每个子域名最多解析几个 IP，默认 10，上限 10 |
| `ip_source` | 域名段 | (可选) 该域名独立的优选 IP 来源，省略用全局 `ip_source` |
| `region` | 域名段 | (区域型厂商必填) 云厂商区域 ID，如华为云 `ap-southeast-1` |
| `project_id_env` | 域名段 | (区域型厂商必填) 指定环境变量，项目 ID 从该变量读取 |
| `line` | 域名段 | (可选) 解析线路，华为云默认 `default_view`；多线路用逗号分隔，如 `电信,联通,移动` |
| `endpoint` | 域名段 | (可选) 自定义 API 端点，指定则优先于 `region` |

| 环境变量名 | 里面存什么 | `config.yml` 哪一行引用它 |
|---|---|---|
| `CF_API_TOKEN` | Cloudflare 令牌（一长串字符） | （程序自动读取，不用写在 config.yml） |
| `CF_ZONE` | 你的 Cloudflare 域名，如 `a.com` | 域名段写 `zone_env: CF_ZONE` |
| `CF_ZONES` | 多个域名打包在一起（多域名用），如 `{"a":"a.com","b":"b.net"}` | 域名段写 `zone_env: CF_ZONES` + `zone_key: 编号` |
| `HUAWEI_ZONE` | 你的华为云域名，如 `hw.com` | 域名段写 `zone_env: HUAWEI_ZONE` |
| `HUAWEI_ZONE_PROJECT` | 华为云项目 ID | 域名段写 `project_id_env: HUAWEI_ZONE_PROJECT` |
| `HUAWEICLOUD_SDK_AK` / `_SK` | 华为云 Access Key ID / Secret Key | （程序自动读取） |

> 全流程：先在 GitHub 的 Secrets 里建好环境变量 → 再到 `config.yml` 的对应域名段写 `zone_env: 环境变量名` 引用它。Secrets 没建的环境变量，`config.yml` 里引用了也不会报错，只是那个域名会被自动跳过（会打印提示）。

### 多域名配置（同一个账号下有多个域名）

同一个账号（如 Cloudflare）下要对多个域名更新优选 IP 时：**凭据（令牌）共用一个环境变量，每个域名各用一个环境变量存域名**。有两种做法，二选一。

**做法一：一个环境变量存多个域名（推荐，适合域名多的情况）**

第 1 步，在 **Settings → Secrets and variables → Actions**（仓库页面 → Settings → 左侧 Secrets and variables → Actions）建一个环境变量：

- **Name 框**：填 `CF_ZONES`
- **Value 框**：填下面这行（把 `a.com`、`b.net` 换成你自己的两个域名）：

```
{"a":"a.com","b":"b.net"}
```

> 这行怎么读：`"编号":"域名"` 一对一对，中间用英文逗号隔开，最外层用 `{` `}` 包住。`a`、`b` 是给域名起的**编号**（随便取，别重复）；后面跟着的 `a.com`、`b.net` 才是你的真实域名。**域名要写完整**（如 `baidu.com`，不是 `baidu`）。符号全部用英文（`{}` `:` `"` `,`），一行写完，别有多余空格或换行。

第 2 步，打开 `config.yml`，在 `domains` 里给**每个域名写一段**。关键就三个点：`zone_env` 填 `CF_ZONES`（和步骤 1 的名字一致）、`zone_key` 填步骤 1 里给这个域名起的编号、`subdomains` 填你要解析的子域名前缀：

```yaml
domains:
  - provider: cloudflare
    zone_env: CF_ZONES          # 固定填 CF_ZONES，因为步骤 1 建的环境变量就叫这个名字
    zone_key: a                 # 步骤 1 里给第一个域名起的编号是 a → 对应值 a.com
    subdomains:
      - bestcf                  # 子域名前缀，程序会自动补全成 bestcf.a.com
    max_ips: 5

  - provider: cloudflare
    zone_env: CF_ZONES          # 同上，多域名共用这一个环境变量
    zone_key: b                 # 第二个域名的编号是 b → 对应值 b.net
    subdomains:
      - bestcf
      - cdn                     # 会自动补全成 bestcf.b.net、cdn.b.net
    max_ips: 3
```

> 对照关系：步骤 1 里 Value 写的 `{"a":"a.com","b":"b.net"}`，`zone_key: a` 就是告诉程序「去取编号 a 的域名」，取出的是 `a.com`。编号对不上（比如写了 `zone_key: c`）或域名没写进 Value，程序就找不到，这段会被跳过。

第 3 步，把 `config.yml` 的改动提交推送到仓库（GitHub 会自动运行同步）。以后**加新域名**：
1. 回到第 1 步那个 `CF_ZONES` 环境变量，**改它的 Value**，多加一对 `"编号":"域名"`，比如从 `{"a":"a.com","b":"b.net"}` 改成 `{"a":"a.com","b":"b.net","c":"c.org"}`（在 GitHub Secrets 里点 `CF_ZONES` 这行右边的编辑图标改值）；
2. 再到 `config.yml` 照抄一段，`zone_env: CF_ZONES`、`zone_key` 填新编号（如 `c`）、`subdomains` 填子域名。

**做法二：每个域名单独一个环境变量**

域名少时更省事。每个域名在 GitHub 各建一个环境变量（Name 随便起，如 `CF_ZONE2`，Value 就填那个域名本身），`config.yml` 里对应段落写 `zone_env: CF_ZONE2`、**不要**写 `zone_key`：

```yaml
  - provider: cloudflare
    zone_env: CF_ZONE2          # 直接指定：这个环境变量的值就是域名，如 CF_ZONE2 = b.net
    subdomains:
      - cdn
    max_ips: 3
```

两种做法可以混用：一个账号下，部分域名用做法一、部分用做法二都行。

### 常见配置错误

| ❌ 错误写法 | ✅ 正确写法 |
|------------|------------|
| 在 `config.yml` 里直接写真实域名 | 在 GitHub Secrets 里建环境变量，`config.yml` 里用 `zone_env`/`project_id_env` 引用它（公开仓库才不会泄露域名） |
| `subdomains` 里写了完整子域名 `bestcf.a.com` | 只写前缀 `bestcf`（程序会自动补全成 `bestcf.a.com`） |
| 域名段设了 `provider: cloudflare` 但没建 `CF_API_TOKEN` | 在 GitHub Secrets 建好 `CF_API_TOKEN` |
| 华为云域名漏建 `HUAWEI_ZONE_PROJECT` | 在 GitHub Secrets 建好 `HUAWEI_ZONE_PROJECT`（否则该域名被跳过并提示） |
| GitHub Secrets 里建了环境变量，但 `config.yml` 里 `zone_env` 拼写和它不一致 | 让 `config.yml` 里 `zone_env` 的值和 GitHub Secrets 里建的环境变量名**完全一样**（含大小写） |

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

## 的工作原理

它由两个各自独立的任务（GitHub Actions 工作流）组成：

1. **抓取 IP**（`fetch-ips.yml`，每 30 分钟一次）：
   - 从多个网站抓取 Cloudflare 优选 IP（含**线路 + 延迟**）
   - 把线路统一成电信/联通/移动/ANY、丢弃延迟高于 150ms 的 IP、按延迟升序排序，写入 `ip.txt` 并自动提交推送到仓库。

2. **同步 DNS**（`sync-dns.yml`，每小时的 10/40 分一次）：
   - 读取 `config.yml`，按每个域名的 `provider`（用哪个厂商）分发到对应厂商
   - 从 `ip_source` 提供的网页拉取 IP 列表，每个子域名取前 `max_ips` 个写入 DNS（延迟低的优先）
   - 记录和要的目标一致 → 跳过；不一致 → 更新；采集到的 IP 变少 → 自动删除多余的旧记录

---

## 常见问题

**Q：只有部分厂商有凭据，会报错吗？**
不会。没配置凭据（环境变量）的厂商会被自动跳过，其余正常执行。

**Q：`config.yml` 里 `line` 是什么？**
华为云的「解析线路」。默认 `default_view`（全网默认），也可设电信/联通/移动等，让不同运营商访问不同 IP。支持多线路 `line: 电信,联通,移动`，每条线路单独一个记录集，各用延迟最低的 IP。Cloudflare 不支持线路，忽略此参数。

**Q：`max_ips` 太小/太大怎么办？**
每个子域名最多解析 10 个 IP（上限）。若 ip.txt 采集的 IP 数量比设定值少，则按实际数量解析，并自动删除多余的旧记录。

**Q：为什么有的 IP 延迟高？**
采集时已丢弃延迟大于 150ms 的 IP。90ms 以下的 IP 排最前，DNS 优先使用；若某线路内 90ms 以下不够 max_ips，自动续取 90-150ms 的补足。

**Q：公开仓库里不想让人看到我的域名怎么办？**
不要把域名写进 `config.yml`（`zone` 留空、别写），改成在 GitHub Secrets 里建环境变量存域名，域名段用 `zone_env` 指向它，见上方「环境变量各是什么、在哪填」。

**Q：改 `config.yml` 后需要做什么？**
保存后提交推送到 GitHub，`sync-dns.yml` 会在下个定时或手动触发时生效。

---
