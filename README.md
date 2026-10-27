# 风机效率实时计算（路桥中科成）

路桥中科成污水处理厂 1期/2期鼓风机房 **4 台曝气风机**的实时效率计算。5 个读数进、5 列结果出，
算法与台儿庄、枣庄北控共用一份（ADR 0045），本仓只承载路桥的适配面。

- 模型 ID：`fan-efficiency-luqiao-zhongkecheng`
- 平台实验：`MLModel-2619_V001`（作者 `<owner-id>`）
- 打包格式：MLflow pyfunc（cpu-iot，Python 3.11，mlflow 2.22.2）

## 输入 / 输出

输入：`inlet_flow`(m³/min，实际风量) · `outlet_pressure`(kPa，蜗壳表压) · `motor_power`(kW) · `inlet_temperature`(℃) · `elevation`(m，配置常量 28)

输出：`eta_excel`（生效口径）· `eta_corrected`（对照）· `wp_excel` · `wp_corrected` · `quality`

## 点位绑定（4 台）

| 机组 | 点位编号 | 信号 |
|---|---|---|
| 1期1# | `PS1061-BE_GFJF_0001-C_003_0002` | V_IF / V_OP / V_P / V_ITIT |
| 1期2# | `PS1061-BE_GFJF_0001-C_003_0003` | 同上 |
| 2期5# | `PS1061-BE_GFJF_0002-C_003_0004` | 同上 |
| 2期6# | `PS1061-BE_GFJF_0002-C_003_0001` | 同上 |

> 每台 17 个信号共用同一个点位编号，平台绑定必须带信号名。

## 本仓库是脱敏公开版

不含客户现场数据、内网地址与凭据；内网主机名、厂站码、负责人账号已替换为占位符。

## 目录

```
models/_drafts/fan-efficiency-luqiao-zhongkecheng/   模型工作区（契约、规格、决策、源码、测试）
scripts/deploy-kit/fan-efficiency-luqiao-zhongkecheng/  部署套件（A 通道 deploy.py）
```

## 已知缺口

- 尚无 7~30 天 15 s 历史数据，未建 baseline 与验收断面；
- 海拔 28 m 为 SRTM 估算，待竣工图复核；
- V_P 是否为电机输入功率（含变频器损耗）仍待厂家确认。

<!-- gate check -->
