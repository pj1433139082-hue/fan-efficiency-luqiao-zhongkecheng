# 贡献指南

## 先理解这个仓库的形态

本仓是 **导出快照**：内容由内部框架仓 `learn-model` 的 `scripts/export-model-repo.py --public` 生成。
原效率导出目录仍按导出快照管理。经仓库所有者2026-10-27明确要求，本仓另维护组合策略与合并程序；以下「本地资产」必须在后续同步时保留：

| 不会被同步覆盖 | 说明 |
|---|---|
| `README.md` | 根说明，人工维护 |
| `.gitignore` / `.gitattributes` | 仓库配置 |
| `.github/` | issue 表单、PR 模板、CI 工作流 |
| `SECURITY.md` / `CONTRIBUTING.md` / `LICENSE` | 社区健康文件 |
| `apps/` / `fan_combination/` | 独立策略、合并程序及平台公开适配，共用组合核心 |
| `docs/` / `tests/` / `requirements.txt` / `source_manifest.json` | 新增程序文档、回归测试、依赖与来源 |
| `scripts/check_public_content.py` | 公开内容检查，不包含认证配置 |

原`models/`及`scripts/deploy-kit/`中的导出内容仍应回源仓维护；新增人工目录可以通过本仓PR维护。后续导出同步不得删除人工目录，CI会运行其测试；外部导出脚本不在本仓，本次不猜测或修改它的配置。

## 本地跑起来

```bash
# 1) 模型行为断言（23 个 unittest，纯 pandas，无需 mlflow）
cd models/_drafts/fan-efficiency-luqiao-zhongkecheng
python -m pip install pandas
python -m unittest discover -s tests

# 2) 用 MLflow pyfunc 加载打包产物（需要 mlflow 2.22.2 + Python 3.11）
cd release-bundle/service
python -c "import mlflow.pyfunc as p; m=p.load_model('.'); print(m.predict({'inlet_flow':[46.1],'outlet_pressure':[46.2],'motor_power':[42.2],'inlet_temperature':[25.5],'elevation':[38.5]}))"
```

预期：第 1 步 `OK`；第 2 步输出 `eta_excel≈0.7177`、`quality=VALID`。数字对不上就发 issue。

## 提交 PR

1. 开一个分支，改完推上来；
2. 标题写清范围（`docs:` / `ci:` / `fix:` 前缀加分）；
3. 描述里用 `Refs #N` 关联 issue——`Closes #N` 会在合并时直接关掉它，只在确实要关闭时使用；
4. 确认 CI 的 `checks` 通过：模型断言、脱敏自检两步都必须是绿的。

新增程序还须通过合并版与独立策略/可选时间回归。所有示例必须明确为合成；不要提交现场原始数据、真实曲线、认证明文/密文、内部服务地址或序列化服务包。GitHub源码修复不代表内部MLflow Run已更新，发布状态需分别说明。

## 提交信息

沿用仓库历史风格：`feat(scope): 说明` / `fix(scope): 说明` / `docs: 说明`，正文说清「为什么」。
