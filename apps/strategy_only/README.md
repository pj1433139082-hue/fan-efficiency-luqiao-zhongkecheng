# 独立风机组合策略

接收上游已计算的eta_excel有效结果及同台同分钟风量，形成逐台区间，再按当前同刻实际总风量求组合与分配。Python 3.11标准库即可运行，不联网、不重复效率计算。运行命令见仓库根README。

历史JSON包含history_start/history_end（带时区、左闭右开）、cleaning_gap_pct和efficiency_points列表。每点含point_id、observed_at、flow_m3min、小数效率eta_excel、quality。例如0.65表示65%，不能填65。仅VALID点进入历史；无历史不借其他设备曲线。

当前JSON的current数组含二期5#/6#各一条point_id/observed_at/inlet_flow/run_flag/raw_quality_ok/eligible。两台必须严格同刻，且不早于历史终点。eligible=false时，该台实际供风仍计入目标。上游须保证原始质量、运行检查及效率与风量时间口径一致。

与合并版共用根目录fan_combination/core.py和strategy.py。输出有效标志及四个风量数值、独立诊断。无效占位0不是停机指令。所有示例明确为合成数据。

