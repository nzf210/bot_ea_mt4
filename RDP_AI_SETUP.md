# RDP AI-Driven Setup (Gemini Flash + MT4 local sender)

## Components
- `market_snapshot_receiver.py` → local HTTP receiver on port 8010
- `auto_signal_loop.py` → reads snapshots, prefilters, decides, publishes
- `gemini_decider.py` → current decision module (mock prefilter now, Gemini hook point)
- `mt4_snapshot_sender.mq4` → MT4 sender EA/script draft

## 1. Start receiver
```powershell
uvicorn market_snapshot_receiver:app --host 127.0.0.1 --port 8010
```

## 2. Start AI loop
```powershell
python auto_signal_loop.py
```

## 3. MT4 setup
- Copy `mt4_snapshot_sender.mq4` to `MQL4/Experts/`
- Compile in MetaEditor
- Attach to chart
- Enable WebRequest URL:
  - `http://127.0.0.1:8010`

## 4. Test receiver manually
```powershell
$h = @{ Authorization = "Bearer YOUR_BRIDGE_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8010/market/snapshot" -Method POST -Headers $h -ContentType "application/json" -InFile "market_snapshot_example.json"
```

## 5. Observe output
- receiver stores latest snapshot in `latest_market_snapshot.json`
- loop stores generated signals in `generated_ai_signal.json`
- if publish enabled, signal will be sent to ai4trade

## Notes
- current `gemini_decider.py` still uses a mock decision layer + prefilter
- next step is replacing mock decision with real Gemini Flash API call
