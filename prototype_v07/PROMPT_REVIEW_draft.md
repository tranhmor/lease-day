# Lease Day v0.7 提示词与输入字段审查（草稿）

> 审查对象：`prototype_v07/prompts/*.txt`（6 个模板）、`agents/llm.py`（`_strip_private`、`render_user_prompt`）、`lease_day_v07.py`（`_announcement_payload`、`_landlord_base_ctx`、`_build_room_card`、`_tenant_profile_dict`、申请人卡片）、`agents/base.py`（6 个 validator）、`diagnose.py`、`check_v07.py` 第 7 项。
> 本文件**只是草稿**，没有改动任何现有文件。所有“建议改写”都要等组里确认；一旦采用，必须重新记录提示词哈希、重跑 §5.4 诊断和 check 7，而且要在看到 L 组结果**之前**定稿。
> 记号：**【事实】** 指代码实际怎么做（附文件:行号）；**【判断】** 是我的评估或建议。
> 数据来源：我用 R 组（规则策略）跑了 seed 0/1，从第 12 个月快照分叉出 N/S/P，再把记录下来的 ctx 交给 `_strip_private` + `render_user_prompt` 重新渲染，所以下面的长度和分布都是**真实发给 LLM 的 payload**。只读运行，没有写盘。

---

## 0. 结论摘要（按优先级）

| # | 严重度 | 类别 | 一句话 |
|---|---|---|---|
| 1 | 高 | a | 房东提示词只讲“报价高→空置损失”，不讲“报价低→少收租金”，`one_month_vacancy_loss` 字段又加重这种损失框架，可能**人为制造 H3（过度让步）**，也会压低 H1 的效应量。 |
| 2 | 高 | b/d | `recent_apps_per_vacant` 在本区**没有空房**时显示 0.0（申请数 0 ÷ 人为下限 1）。紧张市场（空置率 <4%）中有 46% 的报价看到“0 申请”，传递的是“需求弱”这一**错误信号**，同样推向 H3。 |
| 3 | 高 | e | 续租和空房定价在超出 [0.7,1.3]× 时**静默截断**。9B 模型如果输出倍数或涨幅（如 `1.03`、`3`），会被截成 0.7× 当前租金，等于降租 30%，且不触发重试，也不算 fallback。 |
| 4 | 高 | a（流程） | `diagnose.py:317` 和 `check_v07.py:431` 把“有公告时报价更高”（`landlord_direction_ann_ok`）当成**通过条件**，设计文档 §5.4 第 2 点也这么写。这等于把 H1 写进验收标准，容易诱导“改提示词直到 H1 出现”。 |
| 5 | 中-高 | c/a | 租客的**系统提示词**在 N 和 S 情景下也写着“若存在新线公告……post_open_min……”。check 7 只扫描 payload，不扫描系统提示词，所以没测出来。房东模板没有对应说明，造成房东与租客在“理解锁价时长”上的**不对称辅助**。 |
| 6 | 中 | e | `answer_counter` 允许 `accept:true` 而 `rent` 等于原报价，这实际上是拒绝，却被记成“接受”，会**抬高 H3(b) 的还价接受率**。 |
| 7 | 中 | e | `at_expiry` 的输出格式用 `"renew|counter|move|leave"`、`"方式名或null"` 这种写法，9B 模型容易照抄字面量或输出字符串 `"null"`。`counter + if_rejected=move` 但 `apply` 为空时，会被**静默改成** accept_offer/leave，不记录。 |
| 8 | 中 | b | 租客不知道“搬家申请没成功会按原报价续租”（`lease_day_v07.py:1158, 1238-1246`），也不知道同一套房可能有人竞争。“move”因此看起来比实际风险大，影响 H2 迁入量。 |
| 9 | 中 | a/c | `sort_keys=True`（`llm.py:350`）让 `announcement` 成为房东 payload 的**第一个字段**，P 组公告因此获得首位显著性。 |
| 10 | 中 | d/g | 字段没有单位说明（vacancy 是小数、min 是单程、income 是家庭收入、income_to_rent 是倍数），卡片里还有大量冗余字段（`rent`=`offer_rent`=`current_rent`、不可行方式等）。精简后租客 payload 约可**减少 27%** 字符。 |
| 11 | 中 | 诊断设计 | `diagnose.py` 的房东网格中 zone 与 risk 都由 `idx % 2` 决定（83、89 行），Z05 永远是“怕空置”，Z11 永远是“愿意等”，二者完全混淆；房型与房东类型也都由 `idx % 3` 决定。 |

---

## 1. 决策总览表（事实）

payload 统一渲染方式：`当前决策信息（JSON）：\n` + 单行紧凑 JSON，`sort_keys=True`（`llm.py:348-350`）。`_strip_private`（`llm.py:390-409`）会删除：以 `_` 开头的键、`cell_vacancy`、`demand_signal`、`floor_rent`、`landlord.treated`、`tenant.group`、卡片上的 `rule_score`、`rule_best_mode`、`rule_within_stretch`；`announcement=None` 时整个键不出现。

### 1.1 房东侧公共字段（`_landlord_base_ctx`，`lease_day_v07.py:538-567`），删除隐藏字段后

`_decision, month, room_id, zone, zone_label, amenity_score, kind, current_rent, start_rent, up_front, vacant_for, last_vacant_months, landlord{landlord_id,kind,risk,zones,n_rooms}, landlord_vacant_rooms, zone_vacancy_smooth, nearby_avg_rent, recent_apps_per_vacant, one_month_vacancy_loss`，P 组公告后（以及 S/P 开通后）另有 `announcement{text, opens_at_month, current_month, months_to_opening, already_open, affects_this_zone, expected_time_saving_min}`（`522-536`）。

| 决策 | 模板 | 额外字段 | 输出 schema | validator 约束（`agents/base.py`） | 实测 payload 字符数（均值/最大，P 组开通前） |
|---|---|---|---|---|---|
| renewal_offer | `landlord_renewal_offer.txt` | `tenant_tenure_months, tenant_good_standing`（1086-1087） | `{"rent", "reason"}` | rent 必须能转成 float 且 >0；**超出 [0.7,1.3]×current_rent 时截断**，不重试（69-77, 48-56） | 622 / 743 |
| price_vacant | `landlord_price_vacant.txt` | —（vacant_for=0 表示刚空出；≥2 表示月度复价；实测 vacant_for=1 从不调用） | `{"rent", "up_front", "reason"}` | rent 同上截断；up_front 必须是 int 2/3/4，缺失时沿用原值（80-91） | 569 / 688 |
| answer_counter | `landlord_answer_counter.txt` | `tenant_*`、`initial_offer, counter_rent`（1112-1116） | `{"accept", "rent", "reason"}` | accept 必须是 bool；accept=true 时 rent 截到 [counter, offer] 区间，缺失时取 counter；accept=false 时 rent 强制为 offer（94-112） | 662 / 785 |
| pick_applicant | `landlord_pick_applicant.txt` | `applicants[{tenant_id, offered_rent, requested_up_front, income_to_rent, cash_verified, household_size, good_standing}]`（1189-1200） | `{"tenant_id", "reason"}` | tenant_id 必须是 null 或列表中的 id；bool 和字符串 id 都会被拒（115-123） | 1205 / 2534 |
| at_expiry | `tenant_at_expiry.txt` | `tenant{...}, current_room{card}, candidates[card×≤5], hard_floor`，可能有 `announcement`（不含 zone 字段） | `{"action","mode","rent","if_rejected","apply","reason"}` | 见 §1.2 | 4729 / 6106 |
| search | `tenant_search.txt` | `tenant, candidates, hard_floor`，可能有 `announcement` | `{"apply":[{room_id,mode}], "reason"}` | apply 最多 2 项（多余的静默截掉）；room_id 必须在候选中且不重复；mode 缺失时取第一个可行方式，非法则整条无效（126-154, 234-242） | 3831 / 5218 |

### 1.2 租客卡片与 `at_expiry` 校验（事实）

- 卡片（`_build_room_card`，569-620）字段：`room_id, zone, zone_label, amenity_score, kind, rent, current_rent, offer_rent, rent_pct_income, up_front, upfront_cash_needed, cash_gap, station_dist_m, modes[{mode,min,transfers,month_fare,monthly_residual,feasible,(post_open_min)}], affordable, contract_months`；`line_info_visible` 时另有 `contract_months_after_open`（受益区=12-剩余月数，非受益区=0）。`post_open_min` 只在“P 组已公告且未开通”时出现在地铁类方式上（570, 386-387）。
- 租客档案（622-636）：`tenant_id, income, couple, car, cash, locked_deposit, available_move_cash, comfort_ratio, stretch_ratio, good_standing, tenure_months`（`group` 已删除）。
- `validate_at_expiry`（157-231）：
  - `leave`：总是合法。
  - `renew`：要求 `current_room.affordable`，并且有可行方式；mode 为空时取第一个可行方式；rent 一律改成 offer_rent。
  - `move`：apply 经 `_validate_apply_list` 校验，且不能为空；也接受顶层的 `room_id`。
  - `counter`：rent 必须 ≤ offer_rent，超出则整条无效；之后截断到 [0.75,1.30]×current_rent；要求 rent ≤ income − 2000（**没有扣通勤费**，与 feasible 的定义不一致）；if_rejected 非法时自动补全；if_rejected=move 但 apply 无效或为空时，**静默改成** accept_offer 或 leave。
- 重试：第一次输出不合法时，把原因和“输出格式”块追加到 user prompt 后重试 1 次（`llm.py:467-479`），仍失败则使用规则策略并记为 fallback。

---

## 2. 问题清单（含改写草案）

### A. 引导性措辞与需求特征（类别 a）

**A1【高】房东模板只讲空置损失，属于单边框架，可能制造 H3**
- 事实：`landlord_renewal_offer.txt:5` 写的是“若报价过高导致租客搬走，空置 1 个月即损失一整个月的租金（见 one_month_vacancy_loss）”；`landlord_answer_counter.txt:5` 写的是“如果你拒绝，租客可能……搬走导致房间空置”；`landlord_price_vacant.txt:5` 写的是“付款条款越严……可能延长空置时间”。三个模板都**没有**提到报价偏低的代价。`one_month_vacancy_loss`（`lease_day_v07.py:562`）就是 current_rent 的复制，作为独立字段出现，提高了损失的显著性。
- 判断：模型被反复提示“空置=损失”，却没有“少涨=12 个月少收”的对应提示。这会系统性地压低涨价、提高接受率，而这正是 H3 要检验的“过度让步”。在 P 和 S 中这种偏差同时存在，不会直接造成 P−S 差异，但会压缩 H1 的可检测幅度，并让 H3 的结论有一部分来自提示词。`diagnose.py:53-56` 的措辞 2 是双边的，说明组里已经意识到这个问题，只是冻结模板没有改。
- 改写草案（renewal_offer 第 2 条）：
  > 2. 报价越高，续租后每月收入越多，但租客搬走、房间空出并需要重新招租的可能也越大；报价越低则相反。请根据下方事实自行权衡。
- answer_counter 第 2 条：
  > 2. 若接受，租约按成交价续签 12 个月；若拒绝，租客可能接受原报价，也可能搬走，房间空出后需要重新招租。
- price_vacant 第 2 条：
  > 2. 报价和付款条款越高，签约后收入越多，但符合条件、愿意申请的租客越少，空置时间可能越长；反之亦然。
- 字段：建议删除 `one_month_vacancy_loss`（需要改代码，并把它加入 `HIDDEN_TOP_KEYS`）。若要保留，应同时给出对称字段，例如 `annual_gain_per_1pct = round(current_rent*0.01*12,1)`。【判断】直接删除最干净。

**A2【高】诊断和验收把 H1 方向当成“通过条件”**
- 事实：`diagnose.py:317` 定义 `dir_ann_ok = all(ann_1 > ann_0)`；`check_v07.py:431` 把它放进 Check 4 的 PASS 条件（目前只对 mock 运行，而 mock 本身在 `llm.py:269-274` 里写死了公告涨价）；设计文档 §5.4 第 2 点写的是“有公告时报价应更高”。
- 判断：H1 正是待检验的假设，不能作为提示词冻结前的门槛。否则当真实模型“不涨”时，最自然的反应就是改措辞直到它涨，这是需求特征在流程层面的体现。空置方向（vac_hi < vac_lo）属于常识性理性检查，可以保留为门槛。
- 改写草案（设计文档 §5.4 第 2 点）：
  > 2. 方向检查：空置率高时报价应不高于空置率低时（门槛）；有无公告对报价的影响**只报告、不设门槛**，冻结前不得据此修改提示词。
- 代码草案：`diagnose.py` 中把 `landlord_direction_ann_ok` 改名为 `landlord_ann_effect_reported`，从 `check_v07.py:431` 的 c4_ok 中移除（mock 下仍可作为管线连通测试单独打印）。

**A3【中】“你管理匿名代号分区……不要猜测真实地名”暴露了实验框架**
- 事实：只有 `landlord_renewal_offer.txt:4` 有这一句，其他 5 个模板没有。
- 判断：这句话告诉模型“这是被设计过的情境”，会增加角色扮演和需求特征的风险，而且 4 个房东模板之间不一致。匿名化已经由 `zone_label` 实现，这句话没有必要。
- 改写草案：删除第 1 条，后续编号顺延。

**A4【中】租客模板中的“请注意……”是指令式表述**
- 事实：`tenant_at_expiry.txt:5` 和 `tenant_search.txt:5` 写的是“若存在新线公告，请注意合同期限为 12 个月，开通前的月份仍按当前通勤时间……”。
- 判断：内容是事实，但“请注意”加上专门一条，把模型注意力引向锁价时长计算。房东模板没有对应说明，形成不对称辅助（见 C1）。
- 改写草案：见 C1，把说明移进 payload 中的 announcement 对象，并改成陈述句。

**A5【低】人设标签“愿意等 / 怕空置”**
- 事实：`board_v07.py:34`；两种人设在 P、S 中分布相同。
- 判断：不会造成 P−S 差异，但“愿意等”在语义上接近“可以涨价、可以空置”，可能与公告产生交互，放大效应。建议在诊断中报告人设 × 公告的交互（§4），不需要改词。

### B. 信息缺失或多余（类别 b）

**B1【高】`recent_apps_per_vacant` 在紧张市场显示 0**
- 事实：`zone_vacant_hist` 记的是 `max(emp,1)`（`lease_day_v07.py:1261`），`recent_apps_per_vacant` 等于 apps/vacs（484-489）。本区近 3 个月一套空房都没有时，没有人能申请，所以 apps=0，显示 0.0。实测（P 组，seed 0/1，1188 条续租报价）：31% 显示 0.0；在 `zone_vacancy_smooth<0.04` 的报价中，**46%** 显示 0.0。
- 判断：真实房东在“满租”时感受到的是需求旺盛，而这里看到的是“没人申请”，信号方向相反，推动 H3。
- 改写草案（代码）：近 3 个月实际空房总数为 0 时返回 `null`。字段说明写成：
  > recent_apps_per_vacant：本区近 3 个月平均每套空房收到的申请数；null 表示近期本区没有空房可供申请（房源全部出租）。

**B2【中】租客不知道搬家申请失败后的结局，也不知道存在竞争**
- 事实：搬家者在两个志愿都落空时，若原报价负担得起，按原报价续租（`lease_day_v07.py:1158, 1238-1246`）；同一套房可能有多人申请，由房东挑选（1180-1205）；新来者没有申请成功就离开市场（1234-1236）。三个模板都没有说明这些。
- 判断：模型可能把“move”当作不可撤回的冒险，从而少申请受益区，影响 H2 的样本量和构成。这是真实租客通常知道的信息（可以边住边找房）。
- 改写草案（at_expiry 新增一条）：
  > 搬家时你最多申请 2 套空房，同一套房可能有其他人申请，由房东挑选。若两套都没有租到，你将按当前续租报价继续住（前提是 current_room 的 affordable 为 true）。
- search 新增：
  > 同一套房可能有其他人申请，由房东挑选；如果本月没有租到，你将离开本市场。

**B3【中】房东看到公告，但没有“本份租约有几个月在开通后”**
- 事实：租客卡片有 `contract_months_after_open`（595, 619），房东的 announcement 只有 `months_to_opening`。
- 判断：真实房东能算出这个数，9B 模型不一定算得对。这是 P 组内部的信息对称问题，也会影响 H1 的“临近开通涨幅更大”这类剂量反应。字段只在 announcement 存在时出现，不会泄露给 N 或 S。
- 改写草案（`_announcement_payload` 有 zone 时追加）：`"lease_months_after_open": max(0, 12 - months_to_opening)`，并在对象内说明（见 C1 中的 note）。

**B4【中】`nearby_avg_rent` 的含义与名称不符**
- 事实：它是本区同房型**其他所有房间**（包括已出租房间的现行合同租金）的均值（478-482），不是挂牌价；设计文档 §5.3 写的是“附近挂牌价”。
- 改写草案（字段说明）：
  > nearby_avg_rent：本区同房型其他房间当前合同月租的平均值（元/月，含已出租房间，不是挂牌价）。

**B5【中】`pick_applicant` 中有几个字段没有信息量，或会误导**
- 事实：`offered_rent` 永远等于 room.rent，`requested_up_front` 永远等于 room.up_front，`cash_verified` 永远为 true（1192-1195）。模板第 4 行却要求“依据出价……首期现金是否核验通过”。tenant_id 是全局编号，新来者编号更大。
- 判断：要求模型比较实际相同的“出价”，可能引入噪声，或让它按 id 或位置选人。id 可能泄露“新来者还是老租客”。
- 改写草案（模板第 1 条）：
  > 1. 所有申请人接受相同的月租和付款条款，首期现金均已核验。请依据收入房租比（income_to_rent，收入是月租的几倍）、家庭人数和履约记录（good_standing）选择。
- 代码草案：申请人改用本次列表内编号 1..n，按随机键排序，再在代码中映射回 tenant_id。

**B6【低】租客看到自己的 `good_standing`、`tenure_months`、`hard_floor`**
- 判断：`good_standing` 是房东侧信息，对租客没有用；`hard_floor` 已经体现在 feasible 中。建议删除，以节省 token、减少干扰。

**B7【低】LLM 租客没有偏好异质性**
- 事实：规则租客有 Gumbel 口味（`lease_day_v07.py:190, 377`），LLM 租客看不到口味；`modes` 按 `gen_cost` 排序（389），实测第一个方式 100% 等于规则最优方式。
- 判断：在同样的数字面前，LLM 租客行为会趋同；`modes` 的顺序本身也是隐性锚（第一个就是“推荐”）。建议 modes 改按固定的方式名顺序排列，或在诊断中做顺序置换测试（§4）。

### C. P 与 S/N 之间的不对称（公告本身以外，类别 c）

**C1【中-高】系统提示词在 N/S 中也提到新线，且 check 7 测不到**
- 事实：`tenant_at_expiry.txt:5` 和 `tenant_search.txt:5` 的系统提示词在所有情景中相同，都含有“新线公告 / post_open_min / contract_months_after_open”。`check_v07.py:41-103` 只检查 `_strip_private(rec["inputs"])`，即 payload，不检查系统提示词。房东模板中没有这一类文字。
- 判断：
  1. N 组和 S 组开通前的租客被告知“可能有新线公告”，这本身就是一种暗示。虽然 P 和 S 都这样，不直接造成 P−S 差异，但会让 S 组租客对“没有公告”产生推断，也违背了“N 永远看不到新线信息”的精神。
  2. 租客有专门的计算说明，房东没有，这是 P 组内部的能力不对称，会影响 H1 和 H2 的相对强度。
- 改写草案：
  - 两个租客模板删除第 2 条。
  - 在 `_announcement_payload` 中给租客和房东都加上：
    `"note": "合同期 12 个月。开通前的月份按 min 通勤，开通后的月份按 post_open_min 通勤；contract_months_after_open 表示该房新合同中开通后的月数。"`（房东版：`"note": "lease_months_after_open 表示本房新签 12 个月租约中位于开通之后的月数。"`）
  - 这样所有新线相关文字都只出现在“允许看到新线信息”的 payload 中。check 7 的 `_line_info_present` 会把 note 视为线路信息，符合设计。
- check 7 扩展草案：对 6 个模板文件扫描禁用词 `{"公告","新线","快线","开通","Z05","Z11","受益","提前","预期","涨价","情景","实验","假设"}`。按当前模板，`tenant_*.txt` 会因为“新线公告”不通过。

**C2【中】字段顺序让公告获得首位显著性（P 组独有）**
- 事实：`sort_keys=True`（`llm.py:350`），`announcement` 按字母排在最前（实测房东 payload 以 `{"_decision":..,"amenity_score":..,"announcement":{...` 开头）。
- 判断：对小模型来说，首位信息权重更高。P 组相对 S 组多出的不只是内容，还有“它在最前面”。
- 改写草案：`render_user_prompt` 改用固定、按语义分组的顺序（房源 → 本人和租客 → 市场 → 公告放最后），例如显式 `KEY_ORDER = ["_decision","month","room_id","zone_label","kind","current_rent",...,"announcement"]`。另外在诊断中测试“公告置首 vs 置尾”（§4 L1-e）。

**C3【低】P 组 payload 更长（房东约 +200 字符，租客约 +170 到 +300 字符）**
- 判断：小模型的行为可能受“输入更长、信息更多”本身影响。可以利用 P 组中非受益区房东作**内部安慰剂**（他们也看到公告，但 `affects_this_zone=false`），在分析中报告“受益区（P−S）减去非受益区（P−S）”，作为 H1 的稳健性补充。这只是分析上的建议，不需要改提示词。

**C4【已确认无问题】**
- 开通后 S 和 P 的文字相同（`OPENED_TEXT`，`lease_day_v07.py:99`），check 7 第 98 行会验证。
- 租客 announcement 不含 zone 字段（check 7 第 83 行）。
- `contract_months_after_open` 的计算正确：第 14 个月（0 起计 13）签约时为 1，对应第 25 个月这 1 个月（595 行）。
- 系统提示词在三个情景中逐字相同，不存在情景专属措辞。

### D. 单位和字段含义（类别 d）

**D1【中】没有字段说明；小数和比例、单程分钟、家庭收入都没有交代**

| 字段 | 实际含义（事实） | 歧义风险（判断） |
|---|---|---|
| `zone_vacancy_smooth` | 0-1 小数，近 3 个月平均空房数加上 5% 先验后的平滑值（447-459） | 0.0227 可能被读成 2.27 套或 2.27%；“smooth”是术语；先验使它很难低于 1.5% |
| `current_rent / rent / offer_rent` | 元/月；候选卡片中三者相等；current_room 中 rent=offer_rent=新报价，current_rent=旧租 | 三个名字容易混淆，`rent` 在两类卡片里含义不同 |
| `start_rent` | 第 1 个月的租金 | 没有说明，可能被当作“成本价”或锚点（diagnose 2b 测的正是这一点） |
| `min` / `post_open_min` | 单程分钟 | 没有写明单程 |
| `income` | 家庭月收入（夫妻×1.8，182 行） | 模型可能把它当成个人收入 |
| `income_to_rent` | 收入 ÷ 月租（倍数） | 与租客侧的 `rent_pct_income`（月租 ÷ 收入）互为倒数，容易混淆 |
| `comfort_ratio / stretch_ratio` | 房租占收入比例 | 模板说“舒适线与勉强线”，但没有对应到字段名 |
| `up_front` | 签约时付几个月（2/3/4） | 只有 price_vacant 模板解释了，租客和续租模板都没解释 |
| `amenity_score` | 1-5 | 只有 search 模板解释了 |
| `cash_gap` | 可用现金 − 首期所需（current_room 中首期为 0，所以等于全部现金） | 没有说明 |
| `month` 与 `announcement.current_month` | 重复 | 浪费 token |

- 改写草案：在每个模板的“原则”之后、“输出格式”之前，插入对应决策的“字段说明”。房东版见 §3.1，租客版见 §3.5。**注意**：字段说明中不能出现 announcement、post_open_min 等新线字段（见 C1）。

### E. JSON 和 schema 稳健性（类别 e，9B 模型）

**E1【高】租金越界时静默截断，不重试**
- 事实：`validate_renewal_offer` 和 `validate_price_vacant` 对任何正数都调用 `clamp_rent`（`base.py:75, 89`），不返回错误；`clamped` 标记写进了 output，但 `analyze_v07.py` 没有读取它（grep 无结果）。
- 判断：9B 模型偶尔会输出 `1.03`（倍数）、`3`（涨幅 %）或 `3200`（正常）。前两种会被截成 0.7×current，在 H1 回归中表现为 −30% 的报价。这既污染 H1，也会被算成 H3 的“让步”。
- 改写草案（代码）：`rent < 0.5*current_rent` 或 `rent > 2*current_rent` 时返回 `(None, "rent_out_of_range")`，触发重试；只有落在 [0.5,0.7) 或 (1.3,2] 区间时才截断。分析时报告 clamped 比例，按情景分组。
- 模板中明确写：
  > rent 填写具体月租金额（元/月，例如 3250），不要填涨幅、百分比或倍数。

**E2【中】`answer_counter` 的“接受但按原价”会被计为接受**
- 事实：accept=true 时 rent 被截到 [counter, offer]（`base.py:100-108`），所以 rent=offer 是合法的；`ev["counter_accepts"]` 按 `ans["accept"]` 计数（`lease_day_v07.py:1118-1119`）。
- 判断：H3(b) 的接受率会被“名义接受”抬高。
- 改写草案（模板第 3 条）：
  > 3. 接受（accept=true）表示同意以低于原报价的价格续租，rent 填成交价，必须 ≥ counter_rent 且 < initial_offer；如果坚持原报价，请填 accept=false，rent 填 initial_offer。
- 分析草案：H3(b) 同时报告“严格接受率”（rent < initial_offer − 0.5）。

**E3【中】`at_expiry` 的输出格式**
- 事实：`tenant_at_expiry.txt:15` 是一个合并模板，里面有竖线枚举 `"renew|counter|move|leave"`，以及 `"方式名或null"`、`还价数字或null`。validator 对 renew 和 counter 执行 `raw.get("mode") or cur_modes[0]`，字符串 `"null"` 是真值，会触发 `invalid_renew_mode` 并重试。
- 判断：小模型容易照抄枚举字面量，或输出 `"null"` 字符串；一个模板对 4 种动作，结构负担较重。建议改成 4 个完整示例，并在代码中把 `"null"`、`""`、`"None"` 规范化为 None。
- 改写草案见 §3.5。
- validator 草案：增加 `_nullish(v)`，把 `"null"`、`""`、`"none"`、`"无"` 视为 None；`counter + if_rejected=move + apply 为空` 时，在输出中写 `repaired: "if_rejected_move_to_accept"`，记入日志并单独统计（目前是静默修复，见 `base.py:213-223`）。

**E4【低】`pick_applicant` 的 id 类型**
- 事实：`tid not in valid_ids`（`base.py:120`）会拒绝字符串 `"372"`。
- 草案：先 `int()` 转换再比较；若采用 B5 的本地编号 1..n，id 数字小，模型更不容易出错。

**E5【低】`counter` 的可负担性检查没有扣通勤费**
- 事实：`base.py:200` 用的是 `income − hard_floor`，而 feasible 用的是 `income − rent − month_fare ≥ 2000`。
- 判断：边界上的还价可能通过校验，但续签后月结余低于 2000，与“硬约束不可越过”不一致。建议改成用当前房最便宜可行方式的 month_fare。

**E6【低】超出 2 项的 apply 被静默截断**（`base.py:133`）。影响小，建议在日志中记录。

### F. 中文措辞（类别 f）

- F1【低】“勉强线”“舒适线”没有对应到字段名，见 D1。
- F2【低】公告文字“Z05 通勤预计缩短约 12 分钟”没有说明对象和方式。事实上只有地铁类方式缩短（`room_mode_options` 365-371）。建议改为“届时 Z05 乘地铁到 CBD 预计缩短约 12 分钟，Z11 约 15 分钟”。**注意**：这句话是设计文档 §2.1 固定的公告原文，修改需组里确认，并同时修改 `ANNOUNCEMENT_TEXT` 和 `OPENED_TEXT`。
- F3【低】`tenant_at_expiry.txt:8` 一行塞了 counter 的三个条件，括号嵌套过深，建议拆成子项（见 §3.5）。
- F4【低】price_vacant 第 1 行“请为其设定新的月租报价”，但 vacant_for≥2 时其实是月度复价，建议写成“请为本月挂牌设定月租和付款条款”。

### G. 长度和 token（类别 g）

- 事实：实测 at_expiry payload 最长 6106 字符、search 最长 5218 字符（P 组）；README 估计最长约 3.9K token。Ollama 的 OpenAI 兼容端点不接收请求体中的 `num_ctx`，只依赖服务端 `OLLAMA_CONTEXT_LENGTH=8192`（README:126）；`llm.py:233` 只读 `total_tokens`。
- 判断：如果服务端配置被重置为 4K，Ollama 会**从前面截断**，丢失的正是系统提示词，而 JSON 仍可能合法，fallback 率看不出问题。这是静默失效的风险（高影响、低概率）。
- 草案：
  1. 在 `ping_backend` 中用最长的真实 ctx 测一次，读取 `usage.prompt_tokens`，断言它 ≥ 本地估算值的 90%，否则报错。
  2. 精简卡片（以下需改代码）：删除候选卡片的 `current_rent/offer_rent/zone/contract_months`；删除 current_room 的 `rent/upfront_cash_needed/cash_gap`；删除不可行方式（实测占 5.7%）和 `feasible` 字段；`transfers=0` 时省略。我实测这样可让租客 payload 减少约 **27%** 字符，不损失决策信息。
  3. 删除 `announcement.current_month`（与 month 重复）、`tenant.good_standing`、`hard_floor`。

---

## 3. 完整改写草案（仅供讨论）

> 以下为整文件替换草案。“输出格式”必须保留在最后，因为 `output_format_spec` 在重试时会按“输出格式”截取（`llm.py:379-382`）。

### 3.1 房东公共“字段说明”块（插入 4 个房东模板）

```
字段说明（金额单位为元/月；比例为 0-1 的小数，如 0.05 表示 5%）：
- current_rent：本房现行月租；start_rent：本房在第 1 个月时的月租。
- nearby_avg_rent：本区同房型其他房间当前合同月租的平均值（含已出租房间，不是挂牌价）。
- zone_vacancy_smooth：本区近 3 个月平均空置率。
- recent_apps_per_vacant：本区近 3 个月平均每套空房收到的申请数；null 表示近期本区没有空房可申请。
- vacant_for：本房已连续空置月数；last_vacant_months：本房上一次空置持续的月数。
- landlord_vacant_rooms：你名下当前空置的房间数。
- up_front：签约时一次付清的月数（2=押一付一，3=押一付二，4=押一付三）。
- amenity_score：区域生活配套分（1-5，越高越便利）。
```

### 3.2 `landlord_renewal_offer.txt`

```
你是一名城市租赁市场的房东。你名下一套房源的租约本月到期，请为下一份 12 个月租约给出月租报价。

规则与事实：
1. 租客收到报价后可以接受、还价一次（由你决定是否接受）或搬走。若搬走，房间会空出并需要重新招租，空置期间没有租金收入。
2. 报价越高，续租后每月收入越多，但租客搬走的可能也越大；报价越低则相反。请结合你的身份、风险偏好和下方事实自行权衡。
3. rent 填写具体月租金额（元/月，例如 3250），不要填涨幅、百分比或倍数；必须在 current_rent 的 0.7 至 1.3 倍之间。
4. tenant_tenure_months：现租客已住月数；tenant_good_standing：现租客是否一直按时履约。
5. 仅输出合法 JSON，不要输出任何额外文字。

[字段说明块 3.1]

输出格式：
{"rent": 数字, "reason": "60字以内的理由"}
```

### 3.3 `landlord_answer_counter.txt`

```
你是一名城市租赁市场的房东。你给出续租报价（initial_offer）后，租客还价为 counter_rent。请决定是否接受。这是唯一一轮还价。

规则与事实：
1. 若接受，租约按成交价续签 12 个月；若拒绝，租客可能接受原报价，也可能搬走，房间空出后需要重新招租。
2. 请结合你的身份、风险偏好和下方事实自行权衡。
3. accept=true 表示同意以低于原报价的价格续租，rent 填成交价，必须不低于 counter_rent 且低于 initial_offer；如果坚持原报价，请填 accept=false，rent 填 initial_offer。
4. 仅输出合法 JSON，不要输出任何额外文字。

[字段说明块 3.1]

输出格式：
{"accept": true或false, "rent": 数字, "reason": "60字以内的理由"}
```

### 3.4 `landlord_price_vacant.txt` 与 `landlord_pick_applicant.txt`

```
你是一名城市租赁市场的房东。你名下有一套空置房源，请为本月挂牌设定月租和付款条款。

规则与事实：
1. 报价和付款条款越高，签约后收入越多，但符合条件、愿意申请的租客越少，空置时间可能越长；反之亦然。
2. 请结合你的身份、风险偏好和下方事实自行权衡。
3. rent 填写具体月租金额（元/月），不要填涨幅或倍数，必须在 current_rent 的 0.7 至 1.3 倍之间；up_front 只能是 2、3 或 4。
4. 仅输出合法 JSON，不要输出任何额外文字。

[字段说明块 3.1]

输出格式：
{"rent": 数字, "up_front": 2或3或4, "reason": "60字以内的理由"}
```

```
你是一名城市租赁市场的房东。你的这套空房本月收到多位申请，请选择一位签约，或者全部不选。

规则与事实：
1. 所有申请人都接受当前月租和付款条款，首期现金均已核验。
2. 申请人信息：income_to_rent 为家庭月收入是月租的几倍；household_size 为同住人数；good_standing 为过去是否一直按时履约。
3. 若全部不选，这套房本月继续空置。
4. tenant_id 必须是申请人列表中的编号，或者 null。仅输出合法 JSON，不要输出任何额外文字。

输出格式：
{"tenant_id": 整数或null, "reason": "60字以内的理由"}
```

### 3.5 `tenant_at_expiry.txt`

```
你是一名在 CBD 上班的租客，你的 12 个月租约本月到期。下方 JSON 给出你的情况（tenant）、现房东的续租报价（current_room）和可以申请的空房（candidates）。请做出决定。

事实：
1. 金额单位为元/月。income 为家庭月收入；comfort_ratio、stretch_ratio 分别是你认为“舒适”和“勉强能接受”的房租占收入比例；rent_pct_income 为该房月租占收入比例。
2. current_room 中，offer_rent 为续租报价，current_rent 为现在的月租。
3. 每种上班方式中：min 为单程通勤分钟数，month_fare 为每月通勤费，monthly_residual 为收入减月租再减通勤费。只能选择 feasible 为 true 的方式。
4. 搬家要一次性支付 upfront_cash_needed（押金加预付租金，再加 500 元搬家费）；旧押金会退回，已计入 available_move_cash。amenity_score 为区域生活配套分（1-5）。
5. 搬家时最多申请 2 套空房，同一套房可能有其他人申请，由房东挑选。若都没有租到，你将按续租报价继续住（前提是 current_room 的 affordable 为 true）。
6. room_id 只能取自 candidates，mode 只能是该房可行的方式。不需要的字段填 null，apply 不需要时填 []。

可选 action：
- renew：接受续租报价，填 mode。
- counter：向现房东还价一次。rent 填低于 offer_rent 的具体金额；if_rejected 填被拒后的做法：accept_offer（接受原报价）、move（申请 apply 中的房）或 leave（离开）。
- move：搬家，apply 按优先级填 1-2 套。
- leave：不再租房，离开本市场。
仅输出一个合法 JSON，不要输出任何额外文字。

输出格式（以下四种结构选一种，把示例中的值换成你的决定）：
{"action": "renew", "mode": "地铁", "rent": null, "if_rejected": null, "apply": [], "reason": "60字以内"}
{"action": "counter", "mode": "地铁", "rent": 3100, "if_rejected": "accept_offer", "apply": [], "reason": "60字以内"}
{"action": "move", "mode": null, "rent": null, "if_rejected": null, "apply": [{"room_id": 12, "mode": "电动车"}], "reason": "60字以内"}
{"action": "leave", "mode": null, "rent": null, "if_rejected": null, "apply": [], "reason": "60字以内"}
```
【判断】示例中的具体数值（3100、12、地铁、电动车）可能成为锚。可以改用占位写法（如 `"mode": "<当前房可行方式>"`），但 9B 模型照抄占位符的风险更高。建议在诊断中比较这两种写法的合法率，再决定采用哪一种。

### 3.6 `tenant_search.txt`

```
你是一名在 CBD 上班、正在找房的租客。请从下方候选空房（candidates）中按优先级选择最多 2 套申请；如果都不合适，apply 填 []。

事实：
1.-4. 同 at_expiry 第 1、3、4 条。
5. 同一套房可能有其他人申请，由房东挑选；如果本月没有租到，你将离开本市场。
6. 每套申请的房都要指定一个该房可行的 mode。仅输出合法 JSON，不要输出任何额外文字。

输出格式：
{"apply": [{"room_id": 整数, "mode": "方式名"}], "reason": "60字以内的理由"}
```

### 3.7 announcement 对象草案（代码，`lease_day_v07.py:522-536`）

```python
out = {
    "text": ...,                       # 原文不变（或按 F2 修改）
    "opens_at_month": 25,
    "months_to_opening": ...,          # 删除 current_month
    "already_open": ...,
    "note": "合同期 12 个月。开通前的月份按 min 通勤，开通后的月份按 post_open_min 通勤；"
            "contract_months_after_open 为该房新合同中位于开通之后的月数。",   # 租客版
}
if zone is not None:
    out["affects_this_zone"] = ...
    out["expected_time_saving_min"] = ...
    out["lease_months_after_open"] = max(0, 12 - months_to_opening) if not built else 12
    out["note"] = "lease_months_after_open 为本房新签 12 个月租约中位于开通之后的月数。"
```

---

## 4. C 阶段冻结前的诊断集（草案）

在 `diagnose.py` 现有 4 组网格（房东续租、还价、开通后再定价、租客到期）的基础上补充。总原则：**门槛只用于“理性和稳健性”检查；H1、H2、H3 相关的方向只报告，不设门槛**（见 A2）。

### 4.0 先修现有诊断的混淆（事实 → 草案）
- `diagnose.py:83, 89`：zone 和 risk 都由 `idx % 2` 决定，Z05 永远对应“怕空置”。`:88` 与 `:84`：房东类型由 `idx % 3 != 0` 决定，房型由 `idx % 3` 决定，便宜单间永远对应“托管机构”。草案：用 `itertools.product` 显式交叉 zone × risk × ll_kind × kind，或使用独立的 rng 抽样。
- `diagnose.py:114-122`：`last_vacant_months`、`landlord_vacant_rooms`、`recent_apps_per_vacant` 都和 `vac_high` 绑定。草案：保留这一“市场状态”格，另加一组把 `apps` 与空置率独立交叉的网格（L1-c），专门检验 B1。
- 租客网格的 announced=False 格没有“已开通”状态，也没有非受益区安慰剂。
- 所有网格都没有字段顺序和 id 置换测试。

### 4.1 房东

| 编号 | 网格 | 期望检查（门槛/报告） |
|---|---|---|
| L1-a 主网格 | 区域{受益区 Z05/Z11、非受益区 Z08/Z02} × 公告{无、开通前 12/6/1 个月、已开通} × 空置率{0.02, 0.05, 0.12} × 风险{怕空置, 愿意等} × 房东类型 × 履约{好, 差}，每格 10 例 | **门槛**：空置率越高，报价越低或持平（≥90% 的配对单调）；履约差的报价 ≥ 履约好的报价。**报告**：受益区“公告−无”、非受益区“公告−无”（安慰剂），以及两者之差；风险 × 公告交互。 |
| L1-b 剂量 | 受益区，months_to_opening = 12、9、6、3、1 | **报告**：报价随“开通后租约月数”的斜率。 |
| L1-c 申请热度去耦 | 空置率固定为 0.02；`recent_apps_per_vacant` 取 {0.0, null, 1.2, 3.0} | **门槛（B1 修复后）**：null 和 3.0 的报价 ≥ 0.0 的报价。**报告**：现行实现下 0.0 带来的报价折扣，即 B1 的量化影响。 |
| L1-d 尺度不变 | 同一 ctx 所有金额 ×0.5、×2 | **门槛**：涨幅（%）差异 < 1 个百分点。 |
| L1-e 呈现方式 | 同一 ctx 用 3 种措辞 × 字段顺序（sort_keys、语义顺序、公告置首、公告置尾） × 字段改名（例如 `zone_vacancy_smooth` 改为 `zone_vacancy_rate_3m`） | **门槛**：空置方向在所有变体中保持。**报告**：公告效应在各变体间的极差；若极差大于效应本身，则 H1 结论只能是“对措辞敏感”。 |
| L1-f 输出形态 | 统计所有调用中 rent < 0.7×、> 1.3× 以及 rent < 10 的比例 | **门槛**：越界（会被截断）< 1%；rent < 10（倍数或涨幅误写）= 0。 |
| L1-g 损失框架消融 | 同一 ctx，带或不带 `one_month_vacancy_loss`，用旧模板和新模板 | **报告**：H3 中“紧张市场不涨价”比例的变化，用来量化 A1。 |
| L2 还价 | 折扣{1%, 3%, 5%, 10%} × 空置率{低, 高} × 公告{无, 受益区开通前 6 个月} × 风险 | **门槛**：接受率随折扣增大而不升；“accept=true 且 rent=offer”的比例 < 2%（E2）。**报告**：严格接受率与名义接受率，供 H3(b) 使用。 |
| L3 空房定价 | vacant_for{0, 2, 4, 7} × 空置率 × up_front 初值{2, 4} × 公告 | **门槛**：rent 随 vacant_for 增加而不升；up_front 合法率 100%。**报告**：公告对 up_front 的影响。 |
| L4 选租客 | 3 位申请人，其中 A 在 income_to_rent 和 good_standing 上都占优；位置置换 × id 置换（大小 id 互换） | **门槛**：选 A 的比例 ≥ 90%；结果不随位置或 id 改变（一致率 ≥ 95%）。**报告**：null 的比例；household_size 的影响。 |

### 4.2 租客

| 编号 | 网格 | 期望检查 |
|---|---|---|
| T1-a 主网格 | 收入{低, 中, 高} × 公告{无, 开通前 12/6/1 个月, 已开通} × 受益区候选房租相对现租{−10%, 0, +10%} × 续租涨幅{0, 3%, 8%}，每格 10 例 | **门槛**：动作合法率 ≥ 98%；当续租报价等于现租、且候选在月结余和通勤上都不优于现房时，选择 move 或 leave 的比例 < 10%。**报告**：申请受益区的比例，按收入组分组（H2 的个体层机制）；剂量随 contract_months_after_open 变化。 |
| T1-b 占优 | 某候选在租金、通勤和月结余上都严格优于现房，且现金充足 | **门槛**：选 move（或 counter+move）并申请该房的比例 ≥ 80%。 |
| T1-c 安慰剂 | 公告存在，但所有候选都在非受益区 | **报告**：与无公告相比，move 比例的变化（应接近 0）。 |
| T1-d 置换 | 候选顺序随机 × room_id 重新编号 × modes 顺序（按成本排序或按名称排序） | **门槛**：第一志愿一致率 ≥ 90%；mode 选择不总是第一个列出的方式（B7）。 |
| T1-e 结构 | 专门构造只能 counter 的情形（续租涨 8%，没有更好候选） | **门槛**：counter 的 rent 低于 offer；`if_rejected=move` 时 apply 非空；静默修复比例 < 2%（E3）。 |
| T1-f 失败后结局知情 | 旧模板与新模板（B2） | **报告**：move 比例的变化，用来量化 B2。 |
| T2 search | 同 T1-a、T1-b、T1-d 的设计，但没有 current_room | **门槛**：占优房出现在 apply 中的比例 ≥ 90%；所有候选都可负担时 apply=[] 的比例 < 10%。 |

### 4.3 工程检查
- **E-tok**：用最长的真实 at_expiry ctx 调用一次，断言 `usage.prompt_tokens` ≥ 本地估算值的 90%，确认上下文没有被截断（G）。
- **E-cache**：temperature=0 时同一 prompt 调用 3 次，比较输出是否完全一致，以确认 Ollama 的确定性。
- **E-cross**：在云端模型上跑同一套 L1-a 和 T1-a（可以只跑每格 3 例），报告方向是否一致，作为 analyze 中 crosscheck 的单决策层补充。
- **E-leak**：check 7 增加系统提示词禁用词扫描（C1）。

---

## 5. 未覆盖或需要组里决定的事项
- F2 和 C1 涉及修改设计文档 §2.1 固定的公告原文或公告对象结构，需组里拍板。
- 删除 `one_month_vacancy_loss`、修复 `recent_apps_per_vacant` 都会改变 L 组输入，但不改变 R 组（规则策略没有读取 `one_month_vacancy_loss`；规则策略也没有读取 `recent_apps_per_vacant`，因为 `rule.py` 只用 `zone_vacancy_smooth`、`demand_signal` 等字段）。所以 check 1（R 组 P 与 S 相同）不受影响，但需要重新确认 check 7。
- 本审查没有实际调用 qwen3.5:9b，§2 中关于 9B 模型的行为预测都是【判断】，需要 §4 的诊断来验证。
