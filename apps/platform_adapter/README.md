# 2622平台公开适配源码

本目录提供特征工程/后处理接口，可接内部311 ProductionWrapper；不复制共享框架、凭据载荷或私有服务包。

在线只读二期5#/6#的V_IF/S_RUN/A_FLT/A_SAG各两条。输入为factory_code=PS1061、四组完整编码Array(string)、可选as_of；顺序固定5#/6#，见examples/request.json。输出有效标志及四个风量，无在线压力/功率/温度或target必填项。

使用私有冻结曲线，当前搜索范围1小时只是工程取数范围，不代表小时均值目标、调度或新鲜度门槛。必须共同完整同刻，故障/喘振设备排除推荐，其实际风量仍计入目标。本模块不下发控制。

## 可选时间修复

1.0.1-source新增as_of=[]按未填写处理；省略、null、空白字符串也按未填，NaN只用于内部DataFrame缺值。非空列表（包括[[]]）、字典、数字及无时区时间仍拒绝。**必填测点数组不能为空，不适用时间兼容规则。**

此前内部发布的1.0.0 Run不包含此修复。本次仅提交GitHub源码，未重新上传MLflow或改绑平台。见[发布状态](../../docs/2622-deployment-status.md)。

## 外部配置

使用者提供IOT_CLIENT_ID/IOT_CLIENT_SECRET/IOT_TENANT_ID/IOT_TOKEN_URL/IOT_DATA_URL和IOT_ALLOWED_HOSTS。最后一项是明确允许的主机名列表，用英文逗号分隔；只有这些主机绕代理。不嵌入地址，不关闭TLS校验，不记录认证正文。

```bash
python apps/platform_adapter/run.py --request apps/platform_adapter/examples/request.json --curves /path/to/private/frozen_curves.json
```

私有曲线须由本厂真实数据按已确认口径生成。examples/curves_synthetic.json仅测试，不能用于真实建议。配置不全明确拒绝，不回退内置账号。

