"""各云厂商 DNS 解析插件目录。

新增云厂商步骤：
1. 在此目录新建 <厂商>.py
2. 实现以下两个对象：
   - PROVIDER_NAME：厂商名（与 config.yml 中 provider 一致）
   - PROVIDER_CREDENTIALS：该厂商需要的凭据字段列表（缺失则主框架跳过该厂商）
3. 实现 main_frame 契约函数：
   - lookup_zone(api_token, target_domain) -> (zone_id, zone_name)
   - update_zone_records(credentials, zone_id, zone_name, subdomains, ip_list, max_ips)
"""