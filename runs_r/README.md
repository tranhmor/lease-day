# R 组正式基线（A4，2026-11-25）

- 代码：A1（开局抽到住满）+ A2（三组共用外部事件）+ A3（V1.2 新口径）之后的 `prototype_v07`。
- 规模：N / S / P × 种子 0–19，共 60 局；240 间房，36 个月，共享第 1–12 月热身快照。
- 生成命令（在 `rental_game/` 下）：

```bash
python3 -m prototype_v07.run_v07 --group R --seeds 20 --no-decision-log --out runs_r
python3 -m prototype_v07.analyze_v07 --runs runs_r --group R            > runs_r/analysis_R.json
python3 -m prototype_v07.analyze_v07 --runs runs_r --group R --validate > runs_r/validation_R.json
python3 -m prototype_v07.analyze_v07 --runs runs_r --group R --table    > runs_r/table_R.md
```

- 2026-11-25 用 A5 代码重生成（`summary.json` 新增 `tight_renewals`，其余内容逐字节不变）。
- 可复现性：带决策日志重跑的结果，其 `monthly.jsonl` 和 `summary.json` 与本目录逐字节相同（不比较 `decision_count`、`total_tokens`）。
- 用途：L 组的零基准（规则房东和规则租客都不看公告，所以 P − S 恒为 0），以及偏差检查 B 的对照（`--baseline-runs runs_r`）。
- 2026-11-25 写入 V2.2 判定后，只重新生成了派生文件 `validation_R.json`（只有 V2.2 和 `level_reached` 变化）；运行数据未改动。
- 此目录生成后不再改动；代码再改动时另建新目录，不覆盖本目录。
