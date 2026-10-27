# 路桥中科成风机效率与组合策略

Python 3.11。原效率模型保留一期1#/2#与二期5#/6#；**本次新增组合程序只处理二期5#、6#**。原效率导出目录保持原样，新增目录为人工维护资产。

| 程序 | 输入及职责 | 入口 |
|---|---|---|
| 原效率模型 | 风量/压力/功率/温度/海拔→双口径效率和质量码 | [原源码](models/_drafts/fan-efficiency-luqiao-zhongkecheng/src/model.py) |
| 独立组合策略 | 已计算的同分钟风量及效率点→逐台清洗→组合分配 | [apps/strategy_only](apps/strategy_only/README.md) |
| 效率与组合合并版 | 原始数值历史→分钟聚合→仓库唯一效率实现→组合 | [apps/integrated](apps/integrated/README.md) |
| 平台公开适配版 | 厂区及编码数组→当前同刻快照→冻结曲线组合 | [apps/platform_adapter](apps/platform_adapter/README.md) |

共用组合核心只有一份：[fan_combination/core.py](fan_combination/core.py)。原v1.1清洗、枚举、排序、容量×均效分配保持原样；规则最优不代表已证明最低功耗。

## 快速运行

在仓库根目录安装合并版及测试依赖：

```bash
python -m pip install -r requirements.txt
python apps/integrated/run.py prepare --input apps/integrated/examples/history_synthetic.json --output outputs/integrated_history
python apps/integrated/run.py recommend --curves outputs/integrated_history/curves.json --input apps/integrated/examples/current_synthetic.json --output outputs/integrated_current
```

独立策略运行：

```bash
python apps/strategy_only/run.py prepare --input apps/strategy_only/examples/efficiency_points_synthetic.json --output outputs/strategy_history
python apps/strategy_only/run.py recommend --curves outputs/strategy_history/curves.json --input apps/strategy_only/examples/current_synthetic.json --output outputs/strategy_current
```

输出目录必须尚不存在。这两条路线的合成结果一致：目标101，5#约40.4726224784、6#约60.5273775216m³/min。**所有随仓数据均为合成测试，不是现场测量、厂家能力或节能效果。**

## 参数与发布状态

- 目标为二期5#/6#同刻实际进口风量之和，容差±5%，单位工况m³/min。
- 历史窗、清洗F、海拔由输入显式提供。本地试跑曾用近7天、F=5%、H=28m，不能推广为厂家认证参数。
- 原效率源码仍有38.5m模板默认值及旧规格文字；合并程序强制显式海拔，见[参数与来源边界](docs/parameters-and-source-boundaries.md)。
- [2622发布与空数组状态](docs/2622-deployment-status.md)：新增源码已兼容可选`as_of: []`，**不代表已发布MLflow Run自动升级**。

每次输出一行五列：`RESULT_VALID/TARGET_FLOW/TOTAL_FLOW/FAN5_FLOW/FAN6_FLOW`。四个风量均m³/min，无单一主输出。有效标志0时其余0为无效占位，不表示全停机；诊断另存。

## 测试与公开范围

```bash
python -m unittest discover -s models/_drafts/fan-efficiency-luqiao-zhongkecheng/tests -v
python -m unittest discover -s apps/integrated/tests -v
python -m unittest discover -s tests -v
python scripts/check_public_content.py
```

仓库不含现场原始数据、真实历史曲线、内部服务地址、认证载荷或MLflow服务pickle。已公开设备编码用于核对绑定。在线适配只用外部IOT_*环境变量及私有曲线，不会自动部署、上传、改绑或控制设备。
