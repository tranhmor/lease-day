# 《到期日》（Lease Day）v0.6 交接说明

更新于 2026-11-01。这是规则版仿真，没有接入 LLM，结果只用来检查设计，不代表北京。

## 1. 怎么启动

需要 Python 3.10 或以上。运行游戏只用标准库；`calibrate_modes.py` 额外需要 numpy 和北京通勤调查的 CSV。

```bash
cd prototype
python3 check_v06.py 8
```

这是最快的检查，几秒到半分钟。Python 3.10 下，正常输出的开头是：

```text
seated 1136 low/mid/high 1.0 1.0 0.99 end n 1118 vacancy 0.068
commute 48.2 low 53.0 over60 0.24
```

Windows 用 `python`，并先设置 `set PYTHONUTF8=1`。程序会开 8 个进程。

| 想做什么 | 命令 | 约需时间 | 结果文件 |
|---|---|---|---|
| 核心实验：三个情景加对照 | `python3 scenarios_v06.py 100 > ../analysis/scenarios_v06_output.txt` | 5 分钟 | `analysis/scenarios_v06_output.txt` |
| 同上，换询盘强度（0 为只看空置率） | `python3 scenarios_v06.py 100 0.4 > ../analysis/scenarios_v06_k0.4.txt` | 2–5 分钟 | `analysis/scenarios_v06_k0.txt`、`_k0.4.txt` |
| 分区空置率和市场水平（四组） | `python3 vacancy_v06.py 100 > ../analysis/vacancy_v06_output.txt` | 1 分钟 | `analysis/vacancy_v06_output.txt` |
| 基线和假设检验 | `python3 run_v06.py 30 > ../analysis/run_v06_output.txt` | 8 分钟 | `analysis/run_v06_output.txt` |
| 同上，再加政策试跑（扩展用） | `python3 run_v06.py 30 policies` | 15 分钟 | 自行保存 |
| 租金和工资趋势 | `python3 trend_v06.py > ../analysis/trend_v06_output.txt` | 3 分钟 | 汇总在 `analysis/trend_v06_results.md` |
| 付款方式对比 | `python3 payment_v06.py > ../analysis/payment_v06_output.txt` | 2 分钟 | `analysis/payment_v06_output.txt` |
| 上班方式校准 | `python3 calibrate_modes.py` | 1 分钟 | 把结果手动填回 `lease_day_v06.py` |
| 重建棋盘 | `cd ../analysis && python3 build_board.py` | 几秒 | `board_cbd_v01.json`、`board_cbd_v01.md` |

## 2. 文件在哪里

| 需要的文件 | 位置 | 用途 |
|---|---|---|
| 规则版主程序 | `prototype/lease_day_v06.py` | 房东和租客怎样决策，每月顺序 |
| 实验运行程序 | `prototype/scenarios_v06.py`（核心）、`vacancy_v06.py`、`run_v06.py`、`trend_v06.py`、`payment_v06.py`、`check_v06.py` | 情景、局数和随机种子 |
| 24 区棋盘数据 | `analysis/board_cbd_v01.json`，可读版 `board_cbd_v01.md` | 房量、房型、租金、通勤时间和费用 |
| 参数和规则说明 | `lease_day_v06.py` 第 26–57 行；`prototype/tenant_rules_v01.md`；本文第 4 节 | 没有单独的参数文件 |
| 已有结果及生成方法 | 第 3 节 | 核对数字能否重新算出 |
| 数据来源说明 | 第 5 节 | 区分真实数据、加工估计和假设 |

运行游戏的输入只有两个文件：`analysis/board_cbd_v01.json` 和 `analysis/zone_shock.json`。程序把结果打印到屏幕，用 `>` 保存。随机种子是 0 到局数减 1，同一编号在各情景间配对。

## 3. 汇报数字来自哪里

| 汇报内容 | 文件 | 能否重新算出 |
|---|---|---|
| 第 10 页基线 | `run_v06_output.txt` 的 `no new line, cbd share 1.0` | 能 |
| 第 11 页三个情景 | `scenarios_v06_output.txt` 的 `east_express`，最后一列是交互影响 | 能 |
| 分区空置率 | `vacancy_v06_output.txt` | 能 |
| 第 12 页规则版租金差 | `scenarios_v06_output.txt`、`scenarios_v06_k0.4.txt` 的 `watch_rent` | 能 |
| 第 12 页低价房减少 | `run_v06_output.txt` 末尾的假设检验 | 能 |
| 第 12 页真实新线租金差 | `analysis/line_rent_results.md`、`center_compare_results.md` | **暂不能**，见第 6 节 |
| 第 5 页方向和单间数字 | `center_compare_results.md`、`zone_listings.json` | **暂不能**，见第 6 节 |

## 4. 规则和代码对照

行号指 `prototype/lease_day_v06.py` 当前版本。

| 规则 | 取值 | 代码位置 |
|---|---|---|
| 规模和时长 | 1,200 间，占用率 95%（1,140 户），60 个月，第 25 个月开通（代码从 0 数，`LINE_OPENS = 24`） | 第 26–29 行 |
| 房量分配 | 存量 × exp(−地铁分钟 / 40) | `allocate`，第 77 行 |
| 收入和家庭 | 工资组 57 / 29 / 14%，双职工 35–46%，第二份收入 × 1.8 | 第 48、51–52 行，`Tenant` |
| 占比线 | 舒适 / 勉强：20/40、25/40、25/35，各浮动 ±5 个百分点 | 第 49 行，`Tenant` |
| 存款和有车 | 存款 = 家庭收入 × 1–3 倍；有车资格 40 / 40 / 35% | `Tenant`，第 50 行 |
| 付款方式 | 按房型抽取押一付一、付二、付三 | 第 39 行，`Game.__init__` 第 143 行 |
| 看房 | 5 条预算内的随机空房 | `best`，第 285 行 |
| 硬规则 | 月剩余不少于 2,000 元；搬家需要该房的押金和预付租金加 500 元 | `allowed`，第 197 行 |
| 上班方式 | 成本最低；常数和偏好来自校准 | `travel`，第 157 行；第 55–57 行 |
| 选住处 | 房租 + 方式成本 + 房型罚分 + 越线罚分 + 搬家罚分 | `score`，第 206 行 |
| 房东按空置调价 | 低于 4% +6%；低于 8% +2%；低于 12% −1%；否则 −4% | `market_rate`，第 216 行 |
| 房东看询盘 | 最近 12 个月询盘 / 开通前 12 个月，强度 0.2，每年最多 ±10% | `demand` 第 221 行，`browse` 第 231 行 |
| 续租 | 30% 不涨，其余按上述幅度的一半 | `renewal`，第 239 行 |
| 房间空出 | 按上述幅度全额调整，不低于起始价 90% | `vacate`，第 259 行 |
| 空房降价 | 空出后第 2 个月起每月 −3%，不低于起始价 90% | `run`，第 361 行 |
| 流动 | 每月 2% 离开；新租客每人看房 3 次，最多换 10 人 | `run`，第 365–373 行 |
| 冻结租金 | 第 25 个月起，续租不变、空出不调价、空房不降价 | `frozen` 第 154 行；第 241、265、361 行 |
| 出行冲击 | 只减少地铁和骑车接地铁的时间 | `open_line`，第 301 行 |
| 上班方式可负担检查（默认关闭） | `afford_modes`：允许改用负担得起的方式 | `travel`，第 157 行 |

## 5. 数据来源

| 类别 | 内容 | 来源 |
|---|---|---|
| 真实数据 | 区域租金（2018 年要价）、2015 年整租租金 | [DRUM 挂牌数据](https://doi.org/10.13020/ejpy-2r93)，CC0，汇总在 `zone_listings.json` |
| 真实数据 | 各区租房户和月租分档（2020） | [普查表 9-4](https://nj.tjj.beijing.gov.cn/tjnj/rkpc-2020/e/zk/html/B0904.jpg)、[表 9-5](https://nj.tjj.beijing.gov.cn/tjnj/rkpc-2020/e/zk/html/B0905.jpg)，人工读图并核对总数，写在 `build_board.py` |
| 真实数据 | CBD 岗位和行业（2013） | [第三次经济普查公报](https://tjj.beijing.gov.cn/tjsj_31433/tjgb_31445/jpgb_31447/202002/P020200216793108628647.pdf) |
| 真实数据 | 地铁线路、道路、公交线路 | OpenStreetMap，ODbL，`bj_routes_full.json`、`zone_modes.json` |
| 加工估计 | 区域房量、房型比例、低价房和便宜单间的租金 | 普查和挂牌份额推算，同一区内差别被抹平 |
| 加工估计 | 收入构成 | CBD 行业人数 × 北京行业中位薪酬，部分行业工资是假设 |
| 加工估计 | 地铁门到门时间、`zone_shock.json` 的省时 | OSM 路网，手写年代筛选，45 公里/小时 |
| 校准 | 上班方式常数、偏好幅度、骑车疲劳、有车资格 | [北京通勤调查](https://doi.org/10.24433/CO.4363875.v1)，CC BY-NC，不随包提供 |
| 依据不足的假设 | 付款方式比例 | [住建委提示](https://finance.sina.com.cn/jjxw/2024-03-18/doc-inantzvr0251039.shtml)和[媒体调查](https://xinwen.bjd.com.cn/content/s608b606de4b054f0ea7d1046.html)只说明常见做法，没有比例 |
| 人为假设 | 占比线、2,000 元底线、存款、第二份收入、时间价值、房型罚分、空置率阈值和涨幅、询盘强度、2% 流动率、90% 下限、衰减常数 40 | 见第 4 节 |

## 6. 已知问题

- **挂牌原文件不在包里：** `data/` 是空的。当时直接下载被拦截，分析在浏览器内存里完成。要从数据页手动下载。
- **两份真实数据结果暂时不能一键重算：** `line_rent_results.md` 和 `center_compare_results.md` 写明了方法，但当时的浏览器脚本没有保存。`zone_listings.json` 的方法保存在 `analysis/listing_zones_browser.js`，也需要改写才能在本地运行。
- **基线年份不一致：** 租金 2018，工资 2020，岗位 2013，车速和公交线路 2026。
- **出行时间未校准：** 速度是假设，没有高峰拥挤。高德校准表还没填。
- **询盘强度没有依据：** 0.2 是假设，没有按真实溢价调参。强度 0.4 时结果也没有明显接近真实值。
- **旧版本：** v0.1–v0.5 和旧走廊结果已作废，不在包里。
- **政策试跑：** `run_v06.py` 保留政策组，默认不跑，供以后的扩展使用。

## 7. 核对建议

1. 先跑 `check_v06.py 8`，确认输出和第 1 节一致。
2. 用第 4 节逐条核对规则和代码。例如“空房第 2 个月起降 3%，冻结时关闭”在第 361 行：`if r.vacant_for > 1 and not self.frozen`。
3. 重跑 `scenarios_v06.py 100`，和 `analysis/scenarios_v06_output.txt` 比较。换 Python 版本或系统后，随机结果可能有小差别。
