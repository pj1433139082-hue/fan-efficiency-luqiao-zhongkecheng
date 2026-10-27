"""只规范可选时间空值；测点数组不使用本函数，非空容器仍明确拒绝。"""
import math


def optional_time(value):
    """None/空白字符串/NaN/JSON空数组→未填写，其余非字符串拒绝。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list) and not value:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    raise ValueError("as_of must be an ISO timestamp string, null, or an empty array []")

