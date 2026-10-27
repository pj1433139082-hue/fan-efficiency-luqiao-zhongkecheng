# 效率与组合合并程序

原始历史→仓库原效率源码分钟聚合与效率→同分钟风量/eta_excel配对→共用v1.1清洗→曲线文件→当前同刻风量驱动推荐。运行命令见根README。

效率只从models/_drafts/fan-efficiency-luqiao-zhongkecheng/src/model.py加载，fan_combination/efficiency_adapter.py不含另一套公式；组合核心只有fan_combination/core.py一份。计算前核对来源摘要。

历史JSON含history_start/history_end（带时区）、cleaning_gap_pct与samples。每行同台同刻，含point_id/observed_at/inlet_flow/outlet_pressure/motor_power/inlet_temperature/elevation/run_flag/dt_s/raw_quality_ok。

单位为工况m³/min、kPa表压、kW、℃、m。海拔必须显式给出，不回退模板38.5m。dt_s是该样本有效代表时长，权重不越过下一样本、分钟末或窗口末；缺失不补零，不拿时间差填缺口。

只用完整分钟；先原函数过滤及时间加权聚合，再计算效率，不先逐点算效率再平均。无效/停机分钟不构造效率点，双效率20%～100%有效性保持原样，不另设D/裕量。

prepare输出曲线、逐分钟审计及质量摘要；recommend只读曲线，不重新计算历史。当前输入与独立策略一致，禁止混入一期/其他厂、跨设备借曲线。所有示例为合成测试，正式数据放仓库外。

