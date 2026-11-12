# Graph Report - collar  (2026-11-12)

## Corpus Check
- 31 files · ~29,177 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 3, .csv 1)

## Summary
- 798 nodes · 1854 edges · 33 communities (14 shown, 19 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 70 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c00e3952`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- main.py
- SymbolBook
- screener.py
- MainFrame
- IBApi
- PutScan
- logbook.py
- open_prognosis.py
- WatchlistDialog
- Controller
- test_book.py
- Displayer
- util/__init__.py
- test_put_scan.py
- .commit
- log_chart.py
- FirestoreDB
- records_ui.py
- App
- run.sh

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
- `import_collar_log()` --calls--> `parse_log_sheet()`  [EXTRACTED]
  botscripts/import_collar_log.py → trade/logbook.py
- `main()` --calls--> `MainFrame`  [EXTRACTED]
  run.py → trade/main.py
- `main()` --calls--> `IBApi`  [EXTRACTED]
  run.py → trade/api.py
- `make_scan()` --calls--> `PutScan`  [EXTRACTED]
  tests/test_put_scan.py → trade/put_scan.py

## Import Cycles
- None detected.

## Communities (33 total, 19 thin omitted)

### Community 0 - "main.py"
Cohesion: 0.05
Nodes (22): _commit_batches(), import_collar_log(), _load_sheet(), create_c(), find_project_root(), general(), gui(), make_c() (+14 more)

### Community 1 - "SymbolBook"
Cohesion: 0.11
Nodes (11): as_count(), describe(), fill_cash(), fill_delta(), multiplier(), Outcome, review_fill(), sgn() (+3 more)

### Community 2 - "screener.py"
Cohesion: 0.06
Nodes (51): d(), quote(), row(), test_earnings_date_and_soon_window(), test_fetch_day_retries_three_times(), test_filters(), test_good_friday_moves_expiry_to_thursday(), test_held_text_and_row_format() (+43 more)

### Community 3 - "MainFrame"
Cohesion: 0.05
Nodes (6): EditPositionDialog, EditStockDialog, MainFrame, parse_premium(), resolve_startdate(), startdate_is_undefined()

### Community 5 - "PutScan"
Cohesion: 0.14
Nodes (3): PutScan, quote_ready(), usable()

### Community 6 - "logbook.py"
Cohesion: 0.08
Nodes (29): test_day_and_year_buckets(), test_month_groups_sum_profit_and_keep_a_running_total(), trade(), test_collateral_limit_is_seventy_percent_and_left_is_the_remainder(), test_collateral_limit_stays_blank_without_an_account_value(), test_per_year_stays_blank_without_a_start_value(), test_total_profit_is_account_growth_and_sets_per_year(), as_float() (+21 more)

### Community 7 - "open_prognosis.py"
Cohesion: 0.09
Nodes (20): test_deepseek_reply_is_the_message_content(), test_option_open_field_takes_the_price_from_the_reply(), test_prompt_carries_the_contract_and_prices(), test_stock_open_field_is_empty_when_unknown(), work(), ask_deepseek(), _close_text(), deepseek_content() (+12 more)

### Community 8 - "WatchlistDialog"
Cohesion: 0.10
Nodes (3): bind_column_help(), SellPutsFrame, WatchlistDialog

### Community 10 - "test_book.py"
Cohesion: 0.26
Nodes (28): fill(), held(), only(), opt(), test_call_assignment_logs_cycle(), test_close_log_keeps_sell_price_and_opening_commission(), test_count_change_is_close_and_open_not_a_roll(), test_disappearing_before_expiry_goes_to_review() (+20 more)

### Community 11 - "Displayer"
Cohesion: 0.10
Nodes (4): breakeven(), Displayer, format_yymmdd(), short_put_collateral()

### Community 12 - "util/__init__.py"
Cohesion: 0.05
Nodes (12): colorize(), ibdebug(), is_float(), is_float_and_not_is_int(), is_int(), print_banner(), print_title_banner(), rgetattr() (+4 more)

### Community 13 - "test_put_scan.py"
Cohesion: 0.15
Nodes (19): plot_powerx_analysis(), advance_done(), FakeController, feed_chain(), feed_details(), feed_quotes(), make_scan(), test_complete_quotes_are_not_retried() (+11 more)

### Community 15 - "log_chart.py"
Cohesion: 0.19
Nodes (5): _axis_money(), LogChartDialog, ProfitChart, _scale(), _y()

### Community 18 - "records_ui.py"
Cohesion: 0.17
Nodes (6): format_yyyymmdd(), parse_value(), RecordFormDialog, RecordPage, RecordsDialog, show_value()

## Knowledge Gaps
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Controller` connect `Controller` to `main.py`, `screener.py`, `MainFrame`, `PutScan`, `.commit`, `FirestoreDB`, `.update_option_stub`, `.handle_position`, `.schedule_book`, `.sendIbCommand`, `.get_instrument_id_from_request`?**
  _High betweenness centrality (0.250) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Controller` (e.g. with `FirestoreDB` and `PutScan`) actually correct?**
  _`Controller` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05263157894736842 - nodes in this community are weakly interconnected._
- **Why does `IBApi` connect `IBApi` to `main.py`, `.start_api`, `App`, `.execDetails`, `._execute_command`, `.cancelOrder`, `.auto_queue`, `.commissionReport`, `.contractDetails`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `MainFrame` (e.g. with `Displayer` and `LogChartDialog`) actually correct?**
  _`MainFrame` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `SymbolBook` be split into smaller, more focused modules?**
  _Cohesion score 0.11450980392156863 - nodes in this community are weakly interconnected._
- **Why does `PutScan` connect `PutScan` to `main.py`, `Controller`, `screener.py`, `test_put_scan.py`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._