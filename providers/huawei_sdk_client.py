"""华为云 DNS 插件的 SDK 调用封装（使用官方 huaweicloud-sdk-python-v3）。

依赖：pip install huaweicloudsdkdns huaweicloudsdkcore
由 providers/huaweicloud.py 使用，勿直接 import 到主框架。
"""
import os

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import (
    DnsClient,
    CreateRecordSetRequest,
    CreateRecordSetRequestBody,
    CreateRecordSetWithLineRequest,
    CreateRecordSetWithLineRequestBody,
    DeleteRecordSetsRequest,
    ListPublicZonesRequest,
    ListRecordSetsByZoneRequest,
    ListRecordSetsWithLineRequest,
    UpdateRecordSetRequest,
    UpdateRecordSetReq,
)
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
# 备选区域表（region_id → endpoint）。DnsRegion.value_of 已内置主要区域，
# 这里额外覆盖几个国际版常用区域，便于无内置时兜底。
_REGION_FALLBACK = {
    'ap-southeast-1': 'https://dns.ap-southeast-1.myhuaweicloud.com',
    'ap-southeast-3': 'https://dns.ap-southeast-3.myhuaweicloud.com',
    'cn-north-4': 'https://dns.cn-north-4.myhuaweicloud.com',
}


class HuaweiDnsClient:
    """薄封装：负责按配置构建 DnsClient，并提供读/写记录集的方法。"""

    def __init__(self, credentials: dict):
        ak = credentials['access_key']
        sk = credentials['secret_key']
        project_id = credentials.get('project_id')
        region_id = credentials.get('region') or 'ap-southeast-1'
        endpoint = credentials.get('endpoint')

        builder = DnsClient.new_builder()

        # 显式 endpoint 优先于 region 表
        if endpoint:
            region_obj = None
        else:
            # 尝试用 SDK 内置区域表
            try:
                region_obj = DnsRegion.value_of(region_id)
            except Exception:
                region_obj = None

        basic = BasicCredentials(ak, sk)
        if project_id:
            basic.project_id = project_id

        builder.with_credentials(basic)

        if endpoint:
            builder.with_endpoint(endpoint)
        elif region_obj is not None:
            builder.with_region(region_obj)
        else:
            # 兜底：用备选区域表
            fb = _REGION_FALLBACK.get(region_id)
            if fb:
                builder.with_endpoint(fb)
            else:
                raise Exception('无法解析华为云区域/端点，请在配置里提供 region 或 endpoint')

        self.client = builder.build()

    # ---------- 读 ----------
    def list_public_zones(self):
        """返回所有公网域名 [zone对象]，字段：id/name/status..."""
        request = ListPublicZonesRequest(type='public')
        response = self.client.list_public_zones(request)
        return response.zones or []

    def list_recordsets(self, zone_id, limit=5000):
        request = ListRecordSetsByZoneRequest(zone_id=zone_id, limit=limit)
        response = self.client.list_record_sets_by_zone(request)
        return response.recordsets or []

    def list_recordsets_with_line(self, zone_id, line_id=None, limit=5000):
        """查询带解析线路的记录集。recordsets 元素含 line 字段。"""
        kwargs = {'zone_id': zone_id, 'limit': limit}
        if line_id:
            kwargs['line_id'] = line_id
        request = ListRecordSetsWithLineRequest(**kwargs)
        response = self.client.list_record_sets_with_line(request)
        return response.recordsets or []

    # ---------- 写 ----------
    # 说明：CreateRecordSetRequestBody / UpdateRecordSetReq 均无 line 字段（走默认 line）。
    # 若要解析线路生效，必须用 WithLine 接口：create_record_set_with_line。
    def create_recordset(self, zone_id, name, record_type, records, ttl):
        body = CreateRecordSetRequestBody(
            name=name,
            type=record_type,
            records=records,
            ttl=ttl,
        )
        request = CreateRecordSetRequest(zone_id=zone_id, body=body)
        self.client.create_record_set(request)

    def create_recordset_with_line(self, zone_id, name, record_type, records, ttl, line):
        """创建带指定解析线路的记录集（官方 CreateRecordSetWithLine 接口）。"""
        body = CreateRecordSetWithLineRequestBody(
            name=name,
            type=record_type,
            records=records,
            ttl=ttl,
            line=line,
        )
        request = CreateRecordSetWithLineRequest(zone_id=zone_id, body=body)
        self.client.create_record_set_with_line(request)

    def update_recordset(self, zone_id, recordset_id, name, record_type, records, ttl, line=None):
        body = UpdateRecordSetReq(
            name=name,
            type=record_type,
            records=records,
            ttl=ttl,
        )
        request = UpdateRecordSetRequest(zone_id=zone_id, recordset_id=recordset_id, body=body)
        self.client.update_record_set(request)

    def delete_recordset(self, zone_id, recordset_id):
        request = DeleteRecordSetsRequest(zone_id=zone_id, recordset_id=recordset_id)
        self.client.delete_record_sets(request)