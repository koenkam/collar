# Graph Report - collar  (2026-11-08)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 784 nodes · 1834 edges · 29 communities (14 shown, 15 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 70 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `67203f25`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 15
- Community 16
- Community 18
- Community 21
- Community 23
- Community 24
- Community 25
- Community 26

## God Nodes (most connected - your core abstractions)
1. `Controller` - 98 edges
2. `IBApi` - 47 edges
3. `PutScan` - 46 edges
4. `MainFrame` - 38 edges
5. `SymbolBook` - 31 edges
6. `reconcile()` - 29 edges
7. `as_count()` - 28 edges
8. `held()` - 24 edges
9. `WatchlistDialog` - 21 edges
10. `only()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `sort_log()` --indirect_call--> `trade()`  [INFERRED]
  trade/firestore.py → tests/test_log_chart.py
- `make_c()` --calls--> `Stub`  [EXTRACTED]
  config/__init__.py → util/__init__.py
- `main()` --calls--> `MainFrame`  [EXTRACTED]
  run.py → trade/main.py
- `main()` --calls--> `IBApi`  [EXTRACTED]
  run.py → trade/api.py
- `make_scan()` --calls--> `PutScan`  [EXTRACTED]
  tests/test_put_scan.py → trade/put_scan.py

## Import Cycles
- None detected.

## Communities (29 total, 15 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (31): create_c(), find_project_root(), general(), gui(), make_c(), path(), screener(), wheel() (+23 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (17): as_count(), describe(), fill_cash(), fill_delta(), multiplier(), Outcome, review_fill(), sgn() (+9 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (45): d(), quote(), row(), test_earnings_date_and_soon_window(), test_fetch_day_retries_three_times(), test_filters(), test_good_friday_moves_expiry_to_thursday(), test_held_text_and_row_format() (+37 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (7): EditPositionDialog, work(), EditStockDialog, MainFrame, parse_premium(), resolve_startdate(), startdate_is_undefined()

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (3): PutScan, quote_ready(), usable()

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (29): test_day_and_year_buckets(), test_month_groups_sum_profit_and_keep_a_running_total(), trade(), test_collateral_limit_is_seventy_percent_and_left_is_the_remainder(), test_collateral_limit_stays_blank_without_an_account_value(), test_per_year_stays_blank_without_a_start_value(), test_total_profit_is_account_growth_and_sets_per_year(), as_float() (+21 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (19): test_deepseek_reply_is_the_message_content(), test_option_open_field_takes_the_price_from_the_reply(), test_prompt_carries_the_contract_and_prices(), test_stock_open_field_is_empty_when_unknown(), ask_deepseek(), _close_text(), deepseek_content(), _delta_text() (+11 more)

### Community 8 - "Community 8"
Cohesion: 0.10
Nodes (3): bind_column_help(), SellPutsFrame, WatchlistDialog

### Community 10 - "Community 10"
Cohesion: 0.26
Nodes (28): fill(), held(), only(), opt(), test_call_assignment_logs_cycle(), test_close_log_keeps_sell_price_and_opening_commission(), test_count_change_is_close_and_open_not_a_roll(), test_disappearing_before_expiry_goes_to_review() (+20 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (3): colorize(), print_banner(), print_title_banner()

### Community 13 - "Community 13"
Cohesion: 0.22
Nodes (18): advance_done(), FakeController, feed_chain(), feed_details(), feed_quotes(), make_scan(), test_complete_quotes_are_not_retried(), test_details_gives_up_after_retries() (+10 more)

### Community 15 - "Community 15"
Cohesion: 0.19
Nodes (5): _axis_money(), LogChartDialog, ProfitChart, _scale(), _y()

### Community 23 - "Community 23"
Cohesion: 0.50
Nodes (3): ibdebug(), wxdebug(), inner()

### Community 25 - "Community 25"
Cohesion: 0.67
Nodes (3): is_float(), is_float_and_not_is_int(), is_int()

## Knowledge Gaps
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Community 9` to `Community 0`, `Community 2`, `Community 3`, `Community 5`, `Community 14`, `Community 16`, `Community 17`, `Community 19`, `Community 20`, `Community 22`, `Community 27`?**
  _High betweenness centrality (0.254) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Controller` (e.g. with `FirestoreDB` and `PutScan`) actually correct?**
  _`Controller` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05063291139240506 - nodes in this community are weakly interconnected._
- **Why does `IBApi` connect `Community 4` to `Community 0`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `MainFrame` (e.g. with `Displayer` and `LogChartDialog`) actually correct?**
  _`MainFrame` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07207207207207207 - nodes in this community are weakly interconnected._
- **Why does `PutScan` connect `Community 5` to `Community 0`, `Community 9`, `Community 13`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._