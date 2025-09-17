# Pro DOGE Bot (Render-Ready)

## What’s inside
- `main.py` – your bot with **pro strategy integration** (no changes to order/TP-SL functions).
- `strategy_upgrade.py` – decision layer (EMA200 + Supertrend + SMA(3/5/7) + RSI + ADX + protections).
- `requirements.txt` – dependencies.
- `render.yaml` – production config for Render.
- `.env.example` – example env file for local runs.

## Deploy on Render
1. Push these files to GitHub (main branch).
2. On Render → **New** → **Blueprint** → link your repo.
3. Render will detect `render.yaml` automatically.
4. In the service → **Environment** add:
   - `BINGX_API_KEY`
   - `BINGX_API_SECRET`
5. Deploy. The dashboard is served on `PORT` (set by Render) at path `/`.

## Local run
```bash
pip install -r requirements.txt
export BINGX_API_KEY=...
export BINGX_API_SECRET=...
python main.py
```

## Strategy summary
- **Trend**: price above/below EMA200 + Supertrend direction.
- **Structure**: SMA3>5>7 (buys) / SMA3<SMA5<SMA7 (sells).
- **Momentum**: RSI ≥ 55 / ≤ 45.
- **Strength**: ADX ≥ 23 (raise TP when ADX ≥ 28).
- **Protections**: spike candle & 3-bars move filter, block same direction for 45m, skip low range.
- **TP/SL**: your existing ATR-based engine kept intact.

