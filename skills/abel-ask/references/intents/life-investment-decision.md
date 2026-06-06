# Life Investment Decision

Use for decisions that allocate money, time, career capital, health, attention,
or opportunity cost without asking for a market strategy.

Examples:

- spend $1M on an MBA
- learn to cook vs keep eating out
- switch careers, buy a home, move, start a company, or stay employed

This intent usually executes through `proxy_routed`: Abel maps the economic
environment, not the user's private constraints or values.

## Boundary

Stay in Abel Ask for decision rules, causal maps, and opportunity-cost analysis.
Switch to Abel Invest only when the user asks for a market trade, buy/sell call,
alpha search, backtest, or strategy.

## Workflow

1. Frame the choice, horizon, irreversible cost, and meaning of "worth it".
2. Split the cost side: cash, time, opportunity cost, downside, reversibility.
3. Split the upside side: income, savings, option value, skill compounding,
   health, autonomy, identity, relationships.
4. Map the external environment with graph/web proxies: labor demand, wage
   premium, rates, inflation, industry cycle, consumer demand, funding cycle,
   housing cycle.
5. Name personal variables Abel cannot see: current income, time, risk
   tolerance, family constraints, taste, persistence, target city/role/industry.
6. Give a rule: worth it if, not worth it if, breakeven threshold, minimum
   experiment, switch/stop trigger.

## Output

```text
Verdict: [conditional recommendation]

Decision rule:
- worth it if ...
- not worth it if ...

Breakeven:
- [cost + opportunity cost] must be covered by [expected upside x probability]

Minimum experiment:
- [small test before committing]

What Abel can and cannot see:
- graph/economic context: ...
- personal facts still needed: ...
```
