# 《到期日》Lease Day v0.7：LLM 房东与租客 + “新线预期”

UGOD 5066（AI Agents for Human Mobility）期末项目。一个北京 CBD 通勤圈的租赁市场仿真：40 名房东和约 228 户租客全部由大语言模型（LLM）扮演，用一个情景回答：

> 东向快线**提前一年公布**后、正式开通前，房东会不会提前涨价，租客会不会提前搬进，好处最后归谁？

- **进度**：见 [`PROGRESS.md`](../PROGRESS.md)（一页纸，先看这个）
- **设计变更时间线**：见 [`DECISIONS.md`](../DECISIONS.md)
- **实验设计主文档**：[`Lease_Day_v0.7_升级方案.md`](../Lease_Day_v0.7_升级方案.md)
- **英文报告初稿**：[`report/Lease_Day_v0.7_report_draft_EN.md`](../report/Lease_Day_v0.7_report_draft_EN.md)

## 实验设计一览

| 情景 | 第 13 个月 | 第 25 个月 |
|---|---|---|
| N 无新线 | — | — |
| S 突然开通 | — | 开通 |
| P 公布后开通 | 所有人收到公告 | 开通 |

- **R 组**：规则房东 + 规则租客，20 个种子，零基准（规则主体不看公告，所以 P = S）。
- **L 组**：LLM 房东 + LLM 租客，5 个种子，主实验。模型 `hy4-flash`（云端）；`qwen3.5:9b`（本地）做交叉核验。
- 规模：24 区、240 间房、36 个月；受益区 Z05（省 12 分钟）和 Z11（省 15 分钟）。
- 同一种子的 N/S/P 共享前 12 个月，并使用共同随机数，三组之间只有“决策”不同。

**假设**（判定标准在看到 LLM 结果之前写定，见升级方案第 9c 节）：

- **H1**：P 组受益区房东在开通前就上调报价（主要证据：决策层面 P − S 配对回归）。
- **H2**：P 组提前迁入受益区的租客更富裕。
- **H3**：LLM 房东是否过于让步（低空置也不涨价、还价几乎全接受）。

## 目录

| 路径 | 内容 |
|---|---|
| `PROGRESS.md`、`DECISIONS.md` | 进度和设计决策记录 |
| `Lease_Day_v0.7_升级方案.md` | 实验设计、接口、验收和验证标准（第 9b/9c/9d 节为预先登记的判定） |
| `Lease_Day_v0.7_理论与实证依据.md` | 空置率实证、验证框架、V1.2 诊断 |
| `prototype_v07/` | 现行代码；`prompts/` 是 6 个已冻结的提示词；`README.md` 是逐条改动记录 |
| `prototype_v07/PROMPT_REVIEW_draft.md` | 提示词与输入字段审查 |
| `runs_r/` | R 组正式基线（60 局，已固定，不再改动） |
| `runs_diag/*.json` | 单决策诊断：qwen 两轮 + hy4 一轮 |
| `runs_b2/` | 本地模型稳定性和速度测试 |
| `figs_r/` | R 组图 |
| `report/` | 英文报告初稿（标 **[L]** 处等 LLM 结果） |
| `analysis/` | 棋盘构建、通勤与房源数据处理、文献核对、V2.2 目标值核查 |
| `docs/history/` | 之前的研究方案、研究设计 v14、v0.6 结果（PDF/Word） |
| `prototype/`、`README.md`（根目录）、`lease_day_v06_*` | **v0.6 规则版（历史版本，不再修改）** |

## 怎么运行

需要 Python 3.9+，只用标准库（画图另需 matplotlib）。在仓库根目录下：

```bash
python3 -m prototype_v07.check_v07                 # 验收测试（离线，不调模型）
python3 -m prototype_v07.run_v07 --group R --seeds 2 --out runs_try   # 规则组试跑
python3 -m prototype_v07.diagnose --mock --samples 5   # 单决策诊断（mock，不花钱）
```

调用真实模型需要在仓库根目录建 `.env`（**不要提交**，已在 `.gitignore` 中）：

```
LLM_BASE_URL=https://api.wokey.ai/v1
LLM_MODEL=hy4-flash
LLM_API_KEY=<向组长私下索取>
```

更多命令见 `prototype_v07/README.md` 的“快速命令”。

## 数据来源与许可

- 房源租金：DRUM 挂牌数据，DOI 10.13020/ejpy-2r93（CC0），仅保存分区汇总。
- 线路和站点：© OpenStreetMap contributors，ODbL（`analysis/bj_routes_full.json`、`stations.json`、`zone_modes.py` 的路网距离）。
- 北京通勤调查原始 CSV 不在仓库中；仓库只含据此拟合的参数。
- 通勤目标值：中规院/百度地图《中国主要城市通勤监测报告》，见 `analysis/v22_commute_target.md`。

仿真结果只用于研究设计和方法演示，**不代表北京真实市场**。
