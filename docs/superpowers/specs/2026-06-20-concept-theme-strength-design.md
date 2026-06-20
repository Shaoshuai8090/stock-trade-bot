# Concept Theme Strength Design

## Goal

接入 A 股概念板块/热门题材强度，让真实行情扫描生成的候选股不再默认 `has_hot_theme=False`。收盘策略已有 `theme`、`theme_rank`、`has_hot_theme` 评分入口，本次设计只补齐真实 provider 的题材数据来源和映射。

## Scope

- 使用 AkShare/东方财富概念板块作为题材强度口径。
- 默认影响 `--provider astock`、`--provider akshare` 和 `close-push` 的真实行情候选。
- 保持 CSV、demo 和现有策略评分接口兼容。
- 概念接口失败时不阻断行情扫描。

## Architecture

新增一个 provider 边界内的概念热度 enrichment helper，例如 `ConceptThemeProvider`。它依赖现有 AkShare module，不直接影响策略层。

`AkShareProvider.fetch_candidates()` 在完成候选 enrich 后调用该 helper：

1. 拉取东方财富概念板块列表。
2. 按板块涨跌幅或列表顺序得到热门概念排名。
3. 只处理前 `hot_concept_limit` 个概念，避免请求过多。
4. 拉取这些热门概念的成分股。
5. 为候选股代码选择 rank 最靠前的概念。
6. 用 `dataclasses.replace` 填充 `theme`、`theme_rank`、`has_hot_theme`。

`AStockDataProvider` 继续以 `AkShareProvider` 作为 base provider，所以它会自然继承概念题材数据。腾讯实时刷新只更新价格、涨跌幅、成交量、换手率和市值，不覆盖题材字段。

## Data Flow

Concept board list:

- Preferred API: `ak.stock_board_concept_name_em()`
- Expected useful fields: concept name, percentage change, and optionally code/rank.
- Ranking rule: sort by percentage change descending when the field is present; otherwise preserve returned order.

Concept constituents:

- Preferred API: `ak.stock_board_concept_cons_em(symbol=concept_name)`
- Expected useful fields: stock code and stock name.

Mapping:

- Normalize all stock codes to six digits.
- Build `code -> theme assignment`.
- If a stock belongs to several hot concepts, keep the assignment with the lowest rank.
- Rank is 1-based. `theme_rank=1` means the strongest concept board among the selected hot concepts.

## Configuration

Add conservative defaults to `AkShareProvider` constructor:

- `enable_concept_theme: bool = True`
- `hot_concept_limit: int = 20`

No CLI flag is required for the initial integration. The feature should work by default for real providers and remain opt-out in tests through constructor injection.

## Failure Handling

Concept theme enrichment is best-effort:

- If board list fetching fails, return candidates unchanged.
- If one concept constituent request fails, skip that concept and continue.
- If fields are missing or malformed, ignore the affected row.
- Do not raise `RuntimeError` from concept enrichment.

This preserves the current scan behavior where market data failures matter, but optional scoring enrichment cannot take down `close-push`.

## Strategy Behavior

No scoring formula change is required.

Existing behavior:

- No hot theme: `_theme_score` returns neutral `8.0` and reason says theme strength is not connected.
- Hot theme without rank: `_theme_score` returns `16.0`.
- Hot theme rank 1-3: `25.0`.
- Hot theme rank 4-10: `20.0`.
- Hot theme rank above 10: `14.0`.

With provider enrichment, real candidates will carry actual `theme_rank` and the existing score path will apply.

## Tests

Provider tests should cover:

- A fake AkShare object with concept board list and constituents fills `theme`, `theme_rank`, and `has_hot_theme`.
- A stock in multiple hot concepts keeps the strongest rank.
- Concept board list failure returns candidates unchanged.
- A single constituent request failure does not fail the whole scan.

Strategy tests can stay focused. Add only a small assertion if needed to ensure a hot concept reason is emitted for provider-enriched candidates.

## Non-Goals

- No industry board fallback in this iteration.
- No manual concept CSV maintenance.
- No Telegram message format change beyond existing `题材` display.
- No new hard filter based on topic strength.
