# Lease Day v0.7 原型说明

基于 `Lease_Day_v0.7_升级方案.md` 搭建的模块化多智能体仿真底座（纯 Python 标准库，兼容 Python 3.9+；`v0.6` 文件完全不动）。

## 目录结构

```text
prototype_v07/
  board_v07.py          # 24 区棋盘、受益区加量（Z05=24, Z11=16，共 240 间）、40 名房东划分、OLS 区域配套分、房源到站距离
  lease_day_v07.py      # GameV07：时间推进、动态现金+押金账本、硬规则校验、4 步批处理撮合、M12 快照分叉、JSONL 日志与回放
  agents/
    base.py             # LandlordPolicy / TenantPolicy 接口与严格 Schema 校验/截断兜底
    rule.py             # RuleLandlord / RuleTenant（v0.7 对称校准版）与 Rule*V06Compat（v0.6 1,200 间回归版）
    llm.py              # LLMLandlord / LLMTenant、OpenAI 兼容 HTTP 客户端（读 .env）、SQLite 缓存、重试 1 次 + 兜底、MockLLMBackend
  prompts/              # 6 份结构化 JSON 提示词模板（匿名区号，定稿前先跑 diagnose.py）
  diagnose.py           # §5.4 单个决策诊断（房东/租客网格 × 3 种措辞 + 让步率测试）
  run_v07.py            # R / L / M 组 × N / S / P 情景 × 配对种子批量运行（默认共享 M1-12 热身快照）
  analyze_v07.py        # §2.3 全部 5 项预登记指标（含净效应 P-N / M12 原住民面板 / 控制空置率报价 OLS / 个案回放）
  check_v07.py          # §9 全部 6 项验收测试 + 底层健康诊断
```

## 相对 v0.6 的核心底层修复（已内置于 v0.7）

1. **消除小格子退租反降价 Bug**：房东空置率改为分区级 3 个月滚动 + 贝叶斯平滑（`m=10`，先验 5%），避免 240 间下 Z11 便宜单间（仅 1 间）退租即跳到 100% 空置而反向降价。
2. **补齐区域配套固定效应（OLS 残差）与双职工整租偏好**：从 2018 真实整租租金对 CBD 地铁时长的 OLS 残差直接计算各区隐含配套价值（并映射为 1–5 分展示给 LLM），消除 Z05/Z11 开局 0% 空置卡死现象。
3. **40 名房东严格隔离处理组/对照组**：受益区（Z05=24、Z11=16）分配给 7 名专属房东，其余 22 区分配给 33 名对照房东，无跨组混持。
4. **月度 4 步批处理撮合**：新来者与到期搬家者统一进入步骤 4 竞争池触发 `pick_applicant`；到期搬家未中标者安全回退原房续租，不会被迫退市；`at_expiry` 还价失败备选一次性返回，省一轮调用；`search` 为每套申请房源分别绑定合法通勤方式。
5. **动态现金 + 押金账本与松弛展示池**：每月结余按比例入账，搬家真实扣除 500 元搬家费与新押金（同时退还旧押金）；候选展示上限放宽至硬底线（55% 收入且月剩余 ≥ 2,000），允许 LLM 租客在预期下适度越过勉强线。
6. **共享 M1–M12 热身快照**：同一随机种子下，N/S/P 从第 12 月末同一状态分叉，消除公布前漂移并节省约 1/3 LLM 调用量。

## 检阅后修正（提示词信息卫生，2026-11-24）

以下改动改变了 LLM 实际看到的输入，**旧缓存与旧 prompt hash 作废**，需重新冻结 `prompts/`。

1. **S 组开通后信息对齐**：自第 25 个月起，S 与 P 的房东/到期租客都收到同一条中性事实 `OPENED_TEXT`（`already_open: true`）；此前 S 组 LLM 无任何开通信号（`demand_signal` 在送入 LLM 前被剥离），P−S 的 M36 比较会混入信息差。
2. **N 组不再暗示新线**：`contract_months_after_open` 与 `post_open_min` 只在 S/P 出现（新增 `GameV07.line_built`）；此前 N 组开通月后受益区卡片仍显示 12。
3. **隐藏实验设计标签**：送入 LLM 前剥离房东 `treated` 与租客 `group`（日志与规则版仍保留）。Mock 后端改为由收入自行推断档位。
4. **空置损失口径统一**：删除易误读的 `monthly_equiv_vacancy_loss`（月租/12），续租提示词改为“空置 1 个月损失一整个月租金”。
5. **新增验收第 7 项** `7_prompt_leakage`：对实际发送给 LLM 的载荷检查 N 组无任何新线信息、S 组开通前无、P 组公告前无、S/P 开通后文本一致、无设计标签。已用旧行为回注验证三类问题均可被检出。

### 第二轮修正（组员复核意见，全部采纳）

6. **重跑不再重复写日志（P0）**：`_open_logs()` 改为“本对象首次写入某目录一律 `w` 并补写热身记录；同一对象再次 `run_until()` 才 `a`”。此前对同一 `--out` 重跑，`decisions.jsonl`/`monthly.jsonl` 行数翻倍（已复现：2,708→5,416），会使指标 5 样本量翻倍、CI 虚窄。
7. **诊断替换措辞补齐 JSON 格式（P0）**：`TENANT_WORDINGS[1][2]` 末尾附与 `tenant_at_expiry.txt` 相同的“输出格式”块；不合法输出的重试提示也附上该模板的格式块。
8. **API 退避重试（P1）**：仅对 HTTP 429/500/502/503/504、超时与网络错误做 3 次指数退避（1/2/4 秒，尊重 `Retry-After`，上限 60 秒），计入 `transport_retries`，不再算作 LLM 输出不合法；400 等客户端错误不重试。
9. **载荷进一步清理（P1）**：剥离 `floor_rent`；无新线信息时 `announcement` 与 `contract_months_after_open` 键本身不出现；租客侧公告不再带按现住区计算的 `affects_this_zone`/`expected_time_saving_min`（租客看公告正文 + 各卡片的 `post_open_min`/`contract_months_after_open`），房东侧保留。
10. **`monthly.jsonl` 的 `line_open` 改用 `line_built`**（N 组恒为 false）。
11. **搬入现金口径**：`treated_move_in_cash` 改为搬家扣款前的可用资金。
12. **诊断新增切片**：`landlord_post_opening_hike_pct`（已开通 × 租金已高出起租价 0/5/8%，检查是否二次涨价）；`tenant_move_treated_pct_by_cell`（公告 × 距开通 12/6/1 月 × 收入档）。
13. **验收扩展**：第 7 项改为键级检查（任何新线相关键都算痕迹）并覆盖全部 6 类决策（另跑一组规则策略以覆盖 `answer_counter`）；新增第 8 项：8a 日志幂等、8b 退避重试、8c 所有措辞含 JSON 键。每项都已用旧行为回注确认能检出。

### 云端模型对照：hy4-flash（2026-11-25）

目的：区分第 2 轮诊断的三个问题（报价不随空置变化、人设无效、租客几乎全部搬家）来自模型能力还是提示词。同一套冻结提示词和网格，只换模型。

- 网关 `https://api.wokey.ai/v1`，模型 `hy4-flash`，配置在 `rental_game/.env`（本地 Ollama 配置保留为注释）。后台 D 阶段试跑在改配置前已启动，仍在用本地 `qwen3.5:9b`（缓存中只有该模型）。
- **思考模式**：不传参数时，320 个输出 token 全部用于思考，正文为空；`reasoning_effort: "none"`（代码中 `openai` 方式，自动识别）可以关闭，正文正常输出。
- **不确定性**：temperature 0 下同一提示依次发送 6 次，得到 3–4 个不同报价（2850–3150）；加 `seed`、`top_p`、`top_k` 都不能消除。云端结果只能靠缓存复现，单条决策带有随机性，需要在报告中说明。
- 速度：8 个并发约 100 次/分钟。命令：`diagnose --live --samples 24 --parallel 8 --cache runs_diag/diag_cache_hy4.sqlite --out runs_diag/diag_report_hy4.json`。
- **结果：通过条件全部通过**（合法率 100%，0 次 fallback，空置方向三种措辞都成立）。与 qwen 第 2 轮对比（括号内为 qwen；单位为续租涨幅的百分点）：

| 项目 | 默认 | 措辞 1 | 措辞 2 |
|---|---|---|---|
| 空置高 − 空置低 | −0.88，t = −7.7（+0.03） | −1.47，t = −11.5（+0.19） | −1.20，t = −11.4（−0.47） |
| 愿意等 − 怕空置 | +1.24，t = 11.5（−0.13） | +1.56，t = 12.4（−0.70） | +0.91，t = 8.3（+0.10） |
| 有公告 − 无公告（只报告） | +0.42，t = 3.6（+0.94） | +0.85，t = 6.2（+1.27） | +0.62，t = 5.5（+1.76） |

- 还价接受率：低空置还价 5% 71%，还价 10% 46%，高空置 75%，有公告 88%。开通后再涨约 0.5–1.3 个百分点。把“已公告”写成“已开通”3.2%。
- 租客（默认模板）：432 条中搬家 327、续租 72、还价 33（qwen 为 431 条搬家）；低收入户有 46% 续租、15% 还价，中高收入户几乎全部搬家。备选措辞下仍以搬家为主（387、411 条）。有公告时首选受益区的比例，三种措辞都更高（76.9 对 40.3、83.8 对 70.4、84.7 对 70.8）。
- 结论：房东侧的两个问题（报价不随空置变化、人设无效）**主要来自 qwen 9B 的能力**，同一提示词换模型后消失。租客“几乎全部搬家”只部分缓解，可能与诊断情境本身（候选房更便宜、通勤更短）或模板有关，需看整局试跑。

### C 阶段诊断第 2 轮（2026-11-25，空置方向仍未通过；按事先规定冻结提示词）

`diagnose --live --samples 24 --parallel 4 --out runs_diag/diag_report_r2.json`，3,408 次调用，43 分钟，合法率 100%，0 次 fallback。

- **空置方向仍未通过**：续租涨幅（空置高 − 空置低），默认 +0.03 个百分点（t = 0.2），措辞 1 +0.19（t = 1.0），措辞 2 −0.47（t = −2.7）。读法问题已解决：默认模板空置高的 288 条理由中 229 条写“空置率高/较高”（第 1 轮常写“空置率低”），空置低时 227 条写“空置率低/极低”。即**模型读对了空置率，并在理由中提到它，但报价不随之变化**。按事先规定不再修改，作为局限报告。
- 人设：“愿意等”减“怕空置”，默认 −0.13（t = −0.9），措辞 1 −0.70（t = −3.7，方向与标签含义相反），措辞 2 +0.10。补上定义后人设仍基本不起作用。
- 只报告：有公告时涨幅更高，三种措辞都成立（+0.94、+1.27、+1.76 个百分点，t ≥ 6.5）；有公告时，“怕空置”+1.47、“愿意等”+1.17。还价接受率：低空置还价 5% 58%，还价 10% 21%，高空置还价 5% 71%，有公告 67%（均低于第 1 轮）。开通后再涨：起租后已涨 0/5/8% 时，比无新线高 1.6/1.4/1.2 个百分点。租客把“已公告”写成“已开通”4.3%。
- 租客：默认模板 432 条中 431 条选择搬家；措辞 1 有 24 条还价；措辞 2 约一半续租。措辞 2 下“有公告时首选受益区”方向仍相反（44.9% 对 63.4%）。
- **冻结的提示词哈希**：answer_counter `2e6d88ffaafc5ed6`，pick_applicant `9d1d7a72d159b4d3`，price_vacant `aca4576ec2075f17`，renewal_offer `ee1f9bcd71be46db`，at_expiry `a555e82cb835970a`，search `1819435663d2d233`。

### C 阶段第 2 轮修改（2026-11-25，第 1 轮诊断之后；最后一轮）

预先说明：本轮之后，如果“空置高时报价更低”仍不通过，就不再修改提示词，作为局限写进报告。

- **空置率改用百分数**：提示里的 `zone_vacancy_smooth: 0.13` 改为 `zone_vacancy_pct: 13.0`（在 `_strip_private` 中换算；引擎、规则策略和日志仍用小数）。模板中这一字段的说明加了示例；`zone_vacancy_smooth` 加入 `FORBIDDEN_KEYS`。mock 后端相应改读百分数。
- **房东人设说明**：4 个房东模板的字段说明第一条解释 `landlord`，只写约束、不写行为（“怕空置”＝空置一个月对现金流影响较大；“愿意等”＝现金流能承受较长时间空置）。`pick_applicant` 补上“结合身份、风险偏好自行权衡”一句。`landlord`、`landlord_vacant_rooms` 移到 JSON 最前面（`month` 之后），公告仍在最后。
- **租客**：到期决策恢复显示自己的 `tenure_months`（找房时仍隐藏）；两个模板补 `couple`、`car` 的说明；到期模板写明搬家“找房和打包还要花时间和精力”（规则版的 `MOVE_HASSLE` 已有此项）。
- **不采用**：按收入设定比例的 `priority`（会把 H2 的结论事先写进模型）、`move_attitude`（比例无依据）、`commute_pref`（可选，暂不加）、受益区房东分层配额（会改动 `runs_r/`，报告中改为列出每个种子的人设构成）。
- **诊断**：两种备选措辞补上与默认模板相同的字段说明，三种措辞只在表述上不同；新增只报告的 `landlord_renewal_hike_pct_by_persona_x_ann`。
- **分析**：`evaluate_preregistered` 输出新增 `exploratory_persona`（每个种子的人设构成；受益区 13–24 月报价变动的 P − S 按人设拆分），标为“探索性，不属于预先登记的判定”，在 L 组运行前加入。
- 验证：R 组 60 局重跑与 `runs_r/` 逐字节一致；`check_v07` 14 项通过。改前文件备份在临时目录 `pre_r2/`。

### C 阶段诊断第 1 轮（2026-11-25，未通过，提示词未冻结）

`python3 -m prototype_v07.diagnose --live --samples 24 --parallel 4 --cache runs_diag/diag_cache.sqlite --out runs_diag/diag_report.json`，共 3,408 次调用，40 分钟，合法率 100%，0 次 fallback。提示词哈希与 B 组改完后一致。

- **通过条件“空置高时报价更低”未通过。** 续租涨幅（空置高 − 空置低）：默认模板 +0.33 个百分点（t = 2.2，方向相反），措辞 1 −0.02（t = −0.1），措辞 2 −0.55（t = −2.9）。默认模板下，空置高的格子里有不少理由写着“空置率低”“空置风险低”，说明模型可能把 0.13 这样的小数读成了低空置。
- 只报告的结果：有公告时涨幅更高，三种措辞都成立（+0.83、+0.77、+1.90 个百分点）。还价接受率：低空置时还价 5% 为 91.7%，还价 10% 为 50%，高空置时还价 5% 为 91.7%，有公告时还价 5% 为 70.8%。开通后，即使租金已比起租价高 8%，报价仍比无新线时高约 1.1 个百分点。租客在开通前的理由里把新线写成“已开通”的比例为 3.5%（23/648）。
- 租客对措辞很敏感：默认模板 100% 选择搬家，措辞 1 多数选择还价，措辞 2 多数选择续租；措辞 2 下“有公告时搬入受益区”的方向相反。备选措辞没有 B 组新增的字段说明，信息量比默认模板少，所以这项比较本身有混淆。

### B2：本地模型稳定性和速度（2026-11-25）

`python3 -m prototype_v07.bench_b2 --per-decision 8 --repeats 3 --parallel 4 --out runs_b2/b2_report.json`。用规则策略跑一局 P 组（种子 0），取 48 条真实提示：6 类决策各 8 条，租客两类包含最长的 2 条。模型为 `qwen3.5:9b`（Q4_K_M），上下文 8192。

| 项目 | 结果 |
|---|---|
| 第一次输出就合法 | 48/48 |
| 同一提示依次发送 3 次，原文相同 | 48/48 |
| 4 个并发和依次发送相比，原文相同 | 27/48（56%） |
| 4 个并发和依次发送相比，决策相同（不含理由） | 46/48（96%），两条不同的都是租客选房 |
| 最长提示 | 2,629 token，距 8192 还有 5,243 token，没有截断；输出都正常结束 |
| 速度 | 依次 48.5 次/分钟，4 个并发 98.2 次/分钟 |
| L 组 5 个种子（约 2.5–2.8 万次调用，按真实决策比例加权） | 依次约 10 小时，4 个并发约 5 小时 |

并发时，Ollama 把多条请求放在一起计算，浮点运算顺序会变，所以 temperature 0 也不能保证输出完全相同。缓存保证了同一实验内相同提示得到相同回答，重跑也能复现；但不用缓存从头再跑时，结果会和第一次略有不同。


依据 `PROMPT_REVIEW_draft.md`。只影响 LLM 的输入和输出处理，R 组 60 局重跑后与 `runs_r/` 逐字节一致（`summary.json` 只多出 `guardrail_counts`）。

1. `recent_apps_per_vacant`：本区窗口内没有空房时返回 `None`（JSON 中为 null），不再显示 0.0，以免把紧张市场误报成“没有需求”。
2. 越界报价：续租和空房定价低于当前租金 0.5 倍或高于 2 倍，判为不合法（`rent_out_of_range`），重试一次，仍不合法记为 fallback；在 0.5–2 倍之间，仍截断到 0.7–1.3 倍，并记 `clamped`。
3. 还价回复“接受”但成交价等于原报价，改记为拒绝（`repaired=accept_at_offer_to_reject`），让 H3(b) 的接受率按严格口径计算。
4. 租客还价的 `if_rejected` 被代码改写时，写入 `repaired`；字符串 `"null"`/`"None"`/`""` 视为 null，`tenant_id` 接受数字字符串。
5. 截断和修正次数按“类型:决策”写进 `summary.json` 的 `guardrail_counts`，作为运行质量指标报告，不作为通过条件。

### 提示词审查后修正 C 组：诊断和验收（2026-11-25）

1. 第 4 项和 `diagnose.py`：“有公告时报价更高”是 H1 本身，改为只报告（`reported_only`），不再作为通过条件；通过条件是 `pass_gate`，即合法率 ≥ 98% 且三种措辞下“空置高时报价更低”都成立。
2. 第 7 项增加模板禁用词扫描（`TEMPLATE_BANNED`）：系统提示词在 N、S、P 三组都会发送，所以不能出现新线、设计或假设相关的词。
3. 诊断网格的区域、风险态度、房型、房东类型改为完全交叉（之前 Z05 总是“怕空置”，便宜单间总是“托管机构”），新增输出 `landlord_renewal_hike_pct_by_factor`。每格样本数为 24 的倍数时完全平衡。

### 提示词审查后修正 B 组：提示词和输入字段（2026-11-25）

改变了 LLM 的输入，**之前的缓存和提示词哈希全部作废**。R 组 60 局重跑后与 `runs_r/` 逐字节一致。改前的模板备份在会话临时目录 `prompts_preB/`。

1. 房东三个定价模板（续租、还价、空房）同时写出两种损失：空置期间没有租金，以及少收的租金在整份 12 个月租约中每月都会发生。删除 `one_month_vacancy_loss` 字段（第 7 项会把它当作禁用键）；删除“匿名代号分区，不要猜测真实地名”一句。
2. 租客模板删除关于新线的说明。相关解释改放在公告字段的 `note` 里，只在允许看到新线信息时出现。房东公告新增 `lease_months_after_open`（本房新租约中位于开通之后、且本区受益的月数；不受益的区域为 0）和对应的 `note`；删除与 `month` 重复的 `current_month`。**公告原文 `ANNOUNCEMENT_TEXT` / `OPENED_TEXT` 不变。**
3. 每个模板都加了字段说明（单位、比例、单程分钟、家庭收入、`null` 的含义）；租客模板说明了申请可能落空以及落空后的结果；`at_expiry` 的输出格式改为四种动作各给一个完整示例；`rent` 要求填具体金额，不能填涨幅或倍数。
4. 字段顺序固定，按语义分组（`KEY_ORDER`）：房源 → 人 → 市场 → 公告。之前按字母排序，`announcement` 总在最前，P 组因此多了一个“排在首位”的差异。
5. 精简卡片（只影响提示词，校验器和规则策略仍读完整 ctx）：删除重复的 `zone`、候选卡片的 `current_rent/offer_rent`、现房卡片的 `rent/upfront_cash_needed/cash_gap`、`contract_months`、不可行的上班方式和 `feasible` 字段、`transfers=0`、租客的 `good_standing/tenure_months/hard_floor`、申请人卡片中在同一套房内恒定的 `offered_rent/requested_up_front/cash_verified`。上班方式按固定名称顺序排列，不再按隐藏的广义成本排序（之前第一项总是规则最优解）。P 组第 13–24 月实测平均长度：`at_expiry` 4,729 → 3,741 字符（−21%），`search` 3,831 → 3,051 字符（−20%）。即使租客 payload 多了 `note`，总长度仍然下降。
6. 诊断措辞：租客措辞 2 删除“新线开通”字样（无公告的格子也会发送这段措辞）。

### 设计调整 A3：V1.2 改为正规市场 + 同房型口径

`summary.json` 新增 `burden_cells`（末 12 月按“房型 | 收入组”汇总的平均租金收入比和租客-月数）。`--validate` 的 V1.2 改为：正规市场房源（剔除低价房）低 > 中 > 高至少 80% 种子成立，且每种房型内部严格递减；原全口径照常输出但不作为通过条件。A3 之前生成的结果没有 `burden_cells`，V1.2 会显示 UNKNOWN，需要重跑。R 组 20 个种子：正规市场 18/20，同房型 4/4，原全口径 0/20，判定通过。

### 设计调整 A2：三组共用外部事件（共同随机数）

新来者改用单独的 `arrival_rng`；流失、看房抽样、处理顺序和规则房东的续租随机数改为 `_keyed_rng(种子, 类别, 编号, 月份)`。每局的 `external_log` 记录每月在场名单、流失名单和新来者属性，供 8e 核对。R 组 20 个种子，S−N 差值的种子间标准差：

| S − N | A2 之前 | A2 之后 |
|---|---|---|
| 受益区租金指数（第 36 月） | +0.61 ± 1.15 | +0.45 ± 0.75 |
| 受益区空置率（第 25–36 月，百分点） | −1.10 ± 1.73 | −0.74 ± 1.13 |
| 平均通勤（第 25–36 月，分钟） | −1.64 ± 0.43 | −1.54 ± 0.40 |

### 设计调整 A1：开局入住改为“抽到住满为止”

`initialize()` 默认 `initial_fill="until_full"`：逐个抽取申请者，直到入住 95%。20 个种子的对照（R 组 N 情景）：

| | 旧做法 `fixed_pool` | 新做法 `until_full` |
|---|---|---|
| 第 1 个月空置率 | 18.0% | 5.7% |
| 第 10–12 月 / 第 25–36 月空置率 | 12.2% / 6.6% | 6.7% / 5.5% |
| 两段差值（均值） | 5.6 个百分点 | 1.25 个百分点 |
| 租金指数 第 1 → 12 → 36 月 | 99.9 → 97.3 → 96.7 | 100.1 → 99.6 → 99.2 |

新增验收 3b，旧做法在 3b 下不通过。第 2 项（v0.6 回归）不受影响，因为兼容模式仍走旧路径。

注：Mock 后端的行为（中高收入提前搬入、房东公告后涨价）是硬编码的，只用于验证管线，**不是研究发现**。

## 快速命令（在 `rental_game/` 目录下运行）

```bash
# 1. 运行全部验收测试（1–7、3b、8a–8f）+ 健康检查
python3 -m prototype_v07.check_v07

# 2. 离线跑单决策诊断（零 API 费用；换 --live 调真实模型）
python3 -m prototype_v07.diagnose --mock --samples 5
# 正式诊断（§5.4：每格 20 样本，跑完后记录 prompt_hashes 并冻结 prompts/）
python3 -m prototype_v07.diagnose --live --samples 20 --out runs/diag_live.json

# 3. 跑规则基准 R 组（示例 20 种子；正式可设 --seeds 100 --no-decision-log）
python3 -m prototype_v07.run_v07 --group R --seeds 20 --out runs_r
python3 -m prototype_v07.analyze_v07 --runs runs_r --group R --replay

# 4. 离线全流程冒烟（Mock LLM 跑 L 组 5 种子，验证缓存、指标与回放）
python3 -m prototype_v07.run_v07 --group L --mock --seeds 5 --out runs_mock
python3 -m prototype_v07.analyze_v07 --runs runs_mock --group L --replay

# 外部验证（Axtell & Epstein 第 0–3 级，标准见升级方案第 9b 节）
python3 -m prototype_v07.analyze_v07 --runs runs_r --group R --validate
python3 -m prototype_v07.analyze_v07 --runs runs_r --group R --table      # 配对差值 + 95% CI 的 Markdown 表
python3 -m prototype_v07.analyze_v07 --runs runs_l --group L --prereg --baseline-runs runs_r   # A5 预登记判定（H1–H3、质量、偏差 B）
python3 -m prototype_v07.analyze_v07 --runs runs_l --group L --crosscheck runs_cloud          # 云端 1 个种子交叉核验
python3 -m prototype_v07.analyze_v07 --runs runs_l --group L --validate --baseline-runs runs_r

# 5. 正式 API 试跑（先跑 1 个种子 × 12 个月核对实际 token 与限速）
python3 -m prototype_v07.run_v07 --group L --live --seeds 1 --months 12 --scenarios N --out runs_pilot
```

## 接入真实 API（`.env` 配置）

`agents/llm.py` 会自动读取工作区根目录或 `rental_game/` 下的 `.env`（支持 `LLM_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `CLASS_API_TOKEN`），可选设置 `LLM_BASE_URL` 与 `LLM_MODEL`。

其他可选项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_THINKING` | `auto` | 关闭混合思考模式的方式：`auto`（按地址/模型推断：`:11434`→ollama，dashscope→dashscope，deepseek→deepseek）/ `ollama` / `dashscope` / `vllm` / `deepseek` / `none` |
| `LLM_TIMEOUT` | 90 | 单次请求超时（秒）；本地模型首次加载可设 300 |
| `LLM_MAX_TOKENS` | 320 | 输出上限 |
| `LLM_USE_PROXY` | 1 | 走 Tailscale / 局域网地址时设 0，绕开系统代理 |

### 本地 GPU（Windows + Ollama，经 Tailscale 调用）

Windows 端：系统环境变量 `OLLAMA_HOST=0.0.0.0:11434`、`OLLAMA_NUM_PARALLEL=4`、`OLLAMA_CONTEXT_LENGTH=8192`（Ollama 在 16 GB 以下显存默认只给 4K 上下文，租客最长提示约 3.9K token，会被截断）；重启 Ollama，防火墙放行 TCP 11434；`ollama pull <模型>`；`ollama ps` 确认 `100% GPU`。

Mac 端 `rental_game/.env`：

```
LLM_BASE_URL=http://100.116.15.70:11434/v1
LLM_MODEL=qwen3.5:9b
LLM_API_KEY=local
LLM_USE_PROXY=0
LLM_TIMEOUT=300
```

```bash
python3 -m prototype_v07.diagnose --ping          # 2 次真实调用：连通、思考已关、JSON 合法、单次耗时
caffeinate -i python3 -m prototype_v07.run_v07 --group L --live --seeds 5 --workers 4 --out runs_l --cache runs_l/llm_cache.sqlite
```

`--live` 默认 1 个进程（适合限速网关）；本地 GPU 显式传 `--workers`，不超过 `OLLAMA_NUM_PARALLEL`。缓存键包含模型名，不同模型可共用一个缓存文件。
