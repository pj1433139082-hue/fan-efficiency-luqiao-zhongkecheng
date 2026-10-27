"""当前8信号的只读IoT适配；沿用311 REST契约，绝不打印认证信息。"""
from datetime import timedelta
import json
import math
import os
from urllib.parse import urlparse

import pandas as pd
import requests
from .bindings import POINTS, SIGNALS, parse_time


class IotReadError(RuntimeError):
    pass


def credentials():
    names = {"client_id": "IOT_CLIENT_ID", "client_secret": "IOT_CLIENT_SECRET", "tenant_id": "IOT_TENANT_ID",
             "token_url": "IOT_TOKEN_URL", "data_url": "IOT_DATA_URL"}
    values = {key: os.environ.get(name) for key, name in names.items()}
    if not all(isinstance(v, str) and v.strip() for v in values.values()):
        raise IotReadError("CONFIG_REQUIRED: use external IOT_* environment variables")
    return values


class IotClient:
    def __init__(self):
        self.credentials = credentials()
        self.session = requests.Session()
        hosts = [urlparse(self.credentials[key]).hostname for key in ("token_url", "data_url")]
        allowed = {v.strip() for v in os.environ.get("IOT_ALLOWED_HOSTS", "").split(",") if v.strip()}
        if not allowed or any(not h or h not in allowed for h in hosts):
            raise IotReadError("DESTINATION_NOT_APPROVED")
        for name in ("NO_PROXY", "no_proxy"):
            os.environ[name] = ",".join(filter(None, [os.environ.get(name), *hosts]))

    def _post(self, url, stage, **kwargs):
        try:
            response = self.session.post(url, **kwargs)
        except requests.RequestException:
            raise IotReadError(stage + "_CONNECTION_OR_TIMEOUT") from None
        if not 200 <= response.status_code < 300:
            raise IotReadError(stage + "_HTTP_" + str(response.status_code))
        try:
            body = response.json()
        except ValueError:
            raise IotReadError(stage + "_INVALID_JSON") from None
        if not isinstance(body, dict):
            raise IotReadError(stage + "_INVALID_BODY")
        return body

    def fetch(self, start, end):
        start, end = parse_time(start.isoformat()), parse_time(end.isoformat())
        c = self.credentials
        token = self._post(c["token_url"], "TOKEN", data={"client_id": c["client_id"],
            "client_secret": c["client_secret"], "grant_type": "client_credentials"}, timeout=30).get("access_token")
        if not isinstance(token, str) or not token:
            raise IotReadError("TOKEN_MISSING")
        headers = {"Authorization": "Bearer " + token, "X-Tenant-Id": c["tenant_id"], "Content-Type": "application/json"}
        columns = [(p, s) for p in POINTS for s in SIGNALS]
        rows, chunks = [], []
        left = start
        while left < end:
            right = min((left + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0), end)
            body = self._post(c["data_url"], "HISTORY", headers=headers, timeout=45, json={
                "detail": {"returnBounds": False, "startTime": str(int(left.timestamp() * 1000)),
                           "endTime": str(int(right.timestamp() * 1000)), "maxSizePerNode": 1500},
                "nodes": [{"namespace": p, "id": s} for p, s in columns]})
            nodes = body.get("results")
            if body.get("code") != 0 or not isinstance(nodes, list) or len(nodes) != len(columns):
                raise IotReadError("HISTORY_NODE_COUNT_OR_APPLICATION_ERROR")
            counts = {}
            for (point, signal), node in zip(columns, nodes):
                node = {} if node is None else node
                if not isinstance(node, dict):
                    raise IotReadError("NODE_TYPE")
                if ("namespace" in node and node["namespace"] != point) or ("id" in node and node["id"] != signal):
                    raise IotReadError("NODE_IDENTITY")
                history = node.get("historyData", []) or []
                if not isinstance(history, list) or len(history) >= 1500 or node.get("continuationPoint"):
                    raise IotReadError("HISTORY_TRUNCATED_OR_INVALID")
                counts[point + "|" + signal] = len(history)
                for item in history:
                    if not isinstance(item, dict):
                        raise IotReadError("RECORD_TYPE")
                    stamp = pd.to_datetime(item.get("t"), unit="ms", utc=True, errors="coerce")
                    if pd.isna(stamp):
                        raise IotReadError("TIMESTAMP_INVALID")
                    if not left <= stamp.to_pydatetime() < right:
                        continue
                    value = item.get("v")
                    try:
                        numeric = float(value) if not isinstance(value, bool) else math.nan
                    except (ValueError, TypeError, OverflowError):
                        numeric = math.nan
                    rows.append({"data_time": stamp.tz_convert("Asia/Shanghai").isoformat(),
                                 "column": point + "|" + signal, "value": numeric,
                                 "status": json.dumps(item.get("s"), ensure_ascii=False)})
            chunks.append({"start": left.isoformat(), "end_exclusive": right.isoformat(), "counts": counts})
            left = right
        return pd.DataFrame(rows, columns=["data_time", "column", "value", "status"]), chunks

