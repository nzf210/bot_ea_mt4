#property strict

extern string BridgeBaseUrl = "http://127.0.0.1:8000";
extern string BridgeToken = "change-me-token";
extern double RiskPercent = 0.5;
extern double MaxDailyLossPercent = 2.0;
extern int MaxSpreadPoints = 35;
extern int MaxSignalAgeSec = 180;
extern int Slippage = 20;
extern int MagicNumber = 20260421;
extern bool EnableTrading = true;
extern bool DebugLogging = true;
extern double EntryZoneExecutionBufferRatio = 0.20;
extern double ExtremeEntryBlockRatio = 0.15;
extern double BreakEvenRMultInput = 0.85;
extern double BreakEvenBufferRMultInput = 0.12;
extern double TrailingStartRMultInput = 1.2;
extern double TrailingStepRMultInput = 0.4;
extern double TrailingSlRMultInput = 0.85;
extern bool TimeBasedTrailingEnabledInput = true;
extern int TimeBasedTrailingAfterSecInput = 600;
extern double TimeBasedTrailingMinRMultInput = 0.25;
extern double TimeBasedTrailingSlRMultInput = 0.18;

string lastSignalId = "";
datetime lastProcessedAt = 0;
int lastOpenTicket = -1;
string lastOpenSignalId = "";
double lastOpenInitialRiskPrice = 0;
double lastOpenInitialStopLoss = 0;
double lastOpenInitialTp1 = 0;
double lastLastAppliedStopLoss = 0;
double lastBreakEvenRMult = 1.0;
double lastBreakEvenBufferRMult = 0.08;
double lastTrailingStartRMult = 1.5;
double lastTrailingStepRMult = 0.5;
double lastTrailingSlRMult = 1.0;
bool lastTrailingEnabled = true;
bool lastTimeBasedTrailingEnabled = true;
int lastTimeBasedTrailingAfterSec = 600;
double lastTimeBasedTrailingMinRMult = 0.25;
double lastTimeBasedTrailingSlRMult = 0.18;
bool lastBreakEvenActivated = false;
bool lastTrailingActivated = false;
datetime lastSignalTimestamp = 0;

string NormalizeBridgeSymbol(string symbol)
{
   string normalized = symbol;
   StringToUpper(normalized);
   if(normalized == "GOLD") return "XAUUSD";
   return normalized;
}

bool IsSupportedChartSymbol()
{
   string chartSymbol = NormalizeBridgeSymbol(Symbol());
   return chartSymbol == "XAUUSD";
}

void DebugPrint(string message)
{
   if(DebugLogging)
      Print("DEBUG: ", message);
}

double DayStartEquity = 0;
int ConsecutiveLosses = 0;
datetime CooldownUntil = 0;

datetime ParseIsoTimestamp(string ts)
{
   string s = ts;
   int dotPos = StringFind(s, ".");
   int zPos = StringFind(s, "Z");
   if(dotPos >= 0)
   {
      if(zPos > dotPos)
         s = StringSubstr(s, 0, dotPos) + "Z";
      else
         s = StringSubstr(s, 0, dotPos);
   }
   StringReplace(s, "T", " ");
   StringReplace(s, "Z", "");
   if(StringLen(s) < 19)
      return 0;

   int year = StrToInteger(StringSubstr(s, 0, 4));
   int month = StrToInteger(StringSubstr(s, 5, 2));
   int day = StrToInteger(StringSubstr(s, 8, 2));
   int hour = StrToInteger(StringSubstr(s, 11, 2));
   int minute = StrToInteger(StringSubstr(s, 14, 2));
   int second = StrToInteger(StringSubstr(s, 17, 2));
   if(year <= 0 || month <= 0 || day <= 0)
      return 0;

   MqlDateTime dt;
   dt.year = year;
   dt.mon = month;
   dt.day = day;
   dt.hour = hour;
   dt.min = minute;
   dt.sec = second;
   return StructToTime(dt);
}

string PersistKey(string suffix)
{
   return "XAU_BRIDGE_" + IntegerToString(MagicNumber) + "_" + suffix;
}

void SaveTradeState()
{
   GlobalVariableSet(PersistKey("ticket"), lastOpenTicket);
   GlobalVariableSet(PersistKey("last_signal_id_len"), StringLen(lastSignalId));
   GlobalVariableSet(PersistKey("last_signal_ts"), lastSignalTimestamp);
   GlobalVariableSet(PersistKey("last_processed_at"), lastProcessedAt);
   GlobalVariableSet(PersistKey("cooldown_until"), CooldownUntil);
   GlobalVariableSet(PersistKey("risk"), lastOpenInitialRiskPrice);
   GlobalVariableSet(PersistKey("sl"), lastOpenInitialStopLoss);
   GlobalVariableSet(PersistKey("tp1"), lastOpenInitialTp1);
   GlobalVariableSet(PersistKey("last_sl"), lastLastAppliedStopLoss);
   GlobalVariableSet(PersistKey("be_r"), lastBreakEvenRMult);
   GlobalVariableSet(PersistKey("be_buf"), lastBreakEvenBufferRMult);
   GlobalVariableSet(PersistKey("trail_start"), lastTrailingStartRMult);
   GlobalVariableSet(PersistKey("trail_step"), lastTrailingStepRMult);
   GlobalVariableSet(PersistKey("trail_sl"), lastTrailingSlRMult);
   GlobalVariableSet(PersistKey("trail_enabled"), lastTrailingEnabled ? 1 : 0);
   GlobalVariableSet(PersistKey("time_trail_enabled"), lastTimeBasedTrailingEnabled ? 1 : 0);
   GlobalVariableSet(PersistKey("time_trail_after"), lastTimeBasedTrailingAfterSec);
   GlobalVariableSet(PersistKey("time_trail_min_r"), lastTimeBasedTrailingMinRMult);
   GlobalVariableSet(PersistKey("time_trail_sl_r"), lastTimeBasedTrailingSlRMult);
   GlobalVariableSet(PersistKey("be_active"), lastBreakEvenActivated ? 1 : 0);
   GlobalVariableSet(PersistKey("trail_active"), lastTrailingActivated ? 1 : 0);
}

void SaveLastSignalId()
{
   GlobalVariableSet(PersistKey("last_signal_id_len"), StringLen(lastSignalId));
   for(int i = 0; i < StringLen(lastSignalId) && i < 64; i++)
      GlobalVariableSet(PersistKey("last_signal_id_" + IntegerToString(i)), StringGetCharacter(lastSignalId, i));
}

string LoadLastSignalId()
{
   int len = 0;
   if(GlobalVariableCheck(PersistKey("last_signal_id_len")))
      len = (int)GlobalVariableGet(PersistKey("last_signal_id_len"));
   string result = "";
   for(int i = 0; i < len && i < 64; i++)
   {
      if(!GlobalVariableCheck(PersistKey("last_signal_id_" + IntegerToString(i))))
         break;
      result += CharToStr((int)GlobalVariableGet(PersistKey("last_signal_id_" + IntegerToString(i))));
   }
   return result;
}

void ClearTradeState()
{
   string keys[21] = {"ticket","risk","sl","tp1","last_sl","be_r","be_buf","trail_start","trail_step","trail_sl","trail_enabled","time_trail_enabled","time_trail_after","time_trail_min_r","time_trail_sl_r","be_active","trail_active","last_signal_ts","last_processed_at","cooldown_until","last_signal_id_len"};
   for(int i = 0; i < ArraySize(keys); i++)
      GlobalVariableDel(PersistKey(keys[i]));
   for(int j = 0; j < 64; j++)
      GlobalVariableDel(PersistKey("last_signal_id_" + IntegerToString(j)));
}

void RestoreOpenTradeState()
{
   lastOpenTicket = -1;
   lastOpenSignalId = "";
   lastOpenInitialRiskPrice = 0;
   lastOpenInitialStopLoss = 0;
   lastOpenInitialTp1 = 0;
   lastLastAppliedStopLoss = 0;
   lastBreakEvenActivated = false;
   lastTrailingActivated = false;

   for(int i = OrdersTotal()-1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderMagicNumber() != MagicNumber || OrderSymbol() != Symbol())
         continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
         continue;

      lastOpenTicket = OrderTicket();
      lastOpenSignalId = OrderComment();
      lastOpenInitialStopLoss = GlobalVariableCheck(PersistKey("sl")) ? GlobalVariableGet(PersistKey("sl")) : OrderStopLoss();
      lastLastAppliedStopLoss = GlobalVariableCheck(PersistKey("last_sl")) ? GlobalVariableGet(PersistKey("last_sl")) : OrderStopLoss();
      lastOpenInitialTp1 = GlobalVariableCheck(PersistKey("tp1")) ? GlobalVariableGet(PersistKey("tp1")) : OrderTakeProfit();
      lastOpenInitialRiskPrice = GlobalVariableCheck(PersistKey("risk")) ? GlobalVariableGet(PersistKey("risk")) : MathAbs(OrderOpenPrice() - OrderStopLoss());
      if(lastOpenInitialRiskPrice <= 0 && lastOpenInitialTp1 > 0)
         lastOpenInitialRiskPrice = MathAbs(OrderTakeProfit() - OrderOpenPrice()) / 1.35;
      lastBreakEvenRMult = GlobalVariableCheck(PersistKey("be_r")) ? GlobalVariableGet(PersistKey("be_r")) : 1.0;
      lastBreakEvenBufferRMult = GlobalVariableCheck(PersistKey("be_buf")) ? GlobalVariableGet(PersistKey("be_buf")) : 0.08;
      lastTrailingStartRMult = GlobalVariableCheck(PersistKey("trail_start")) ? GlobalVariableGet(PersistKey("trail_start")) : 1.5;
      lastTrailingStepRMult = GlobalVariableCheck(PersistKey("trail_step")) ? GlobalVariableGet(PersistKey("trail_step")) : 0.5;
      lastTrailingSlRMult = GlobalVariableCheck(PersistKey("trail_sl")) ? GlobalVariableGet(PersistKey("trail_sl")) : 1.0;
      lastTrailingEnabled = GlobalVariableCheck(PersistKey("trail_enabled")) ? (GlobalVariableGet(PersistKey("trail_enabled")) > 0) : true;
      lastTimeBasedTrailingEnabled = GlobalVariableCheck(PersistKey("time_trail_enabled")) ? (GlobalVariableGet(PersistKey("time_trail_enabled")) > 0) : TimeBasedTrailingEnabledInput;
      lastTimeBasedTrailingAfterSec = GlobalVariableCheck(PersistKey("time_trail_after")) ? (int)GlobalVariableGet(PersistKey("time_trail_after")) : TimeBasedTrailingAfterSecInput;
      lastTimeBasedTrailingMinRMult = GlobalVariableCheck(PersistKey("time_trail_min_r")) ? GlobalVariableGet(PersistKey("time_trail_min_r")) : TimeBasedTrailingMinRMultInput;
      lastTimeBasedTrailingSlRMult = GlobalVariableCheck(PersistKey("time_trail_sl_r")) ? GlobalVariableGet(PersistKey("time_trail_sl_r")) : TimeBasedTrailingSlRMultInput;
      lastBreakEvenActivated = GlobalVariableCheck(PersistKey("be_active")) ? (GlobalVariableGet(PersistKey("be_active")) > 0) : false;
      lastTrailingActivated = GlobalVariableCheck(PersistKey("trail_active")) ? (GlobalVariableGet(PersistKey("trail_active")) > 0) : false;
      break;
   }
}

int OnInit()
{
   DayStartEquity = AccountEquity();
   if(GlobalVariableCheck(PersistKey("cooldown_until")))
      CooldownUntil = (datetime)GlobalVariableGet(PersistKey("cooldown_until"));
   if(GlobalVariableCheck(PersistKey("last_signal_ts")))
      lastSignalTimestamp = (datetime)GlobalVariableGet(PersistKey("last_signal_ts"));
   if(GlobalVariableCheck(PersistKey("last_processed_at")))
      lastProcessedAt = (datetime)GlobalVariableGet(PersistKey("last_processed_at"));
   lastSignalId = LoadLastSignalId();
   RestoreOpenTradeState();
   return(INIT_SUCCEEDED);
}

void ManageOpenTrade()
{
   if(lastOpenTicket <= 0)
      return;
   if(!OrderSelect(lastOpenTicket, SELECT_BY_TICKET, MODE_TRADES))
      return;

   int type = OrderType();
   if(type != OP_BUY && type != OP_SELL)
      return;

   double openPrice = OrderOpenPrice();
   double currentSl = OrderStopLoss();
   double tp = OrderTakeProfit();
   double riskPrice = lastOpenInitialRiskPrice;
   if(riskPrice <= 0)
      riskPrice = MathAbs(openPrice - currentSl);
   if(riskPrice <= 0 && tp > 0)
      riskPrice = MathAbs(tp - openPrice) / 1.35;
   if(riskPrice <= 0)
      return;

   RefreshRates();
   double currentPrice = (type == OP_BUY) ? Bid : Ask;
   double profitPrice = (type == OP_BUY) ? (currentPrice - openPrice) : (openPrice - currentPrice);
   double rMultiple = profitPrice / riskPrice;
   double newSl = currentSl;
   bool shouldModify = false;

   if(lastTrailingEnabled && rMultiple >= lastBreakEvenRMult)
   {
      double beBuffer = riskPrice * lastBreakEvenBufferRMult;
      double beSl = (type == OP_BUY) ? (openPrice + beBuffer) : (openPrice - beBuffer);
      if((type == OP_BUY && beSl > newSl) || (type == OP_SELL && (newSl == 0 || beSl < newSl)))
      {
         newSl = beSl;
         shouldModify = true;
         lastBreakEvenActivated = true;
      }
   }

   if(lastTrailingEnabled && rMultiple >= lastTrailingStartRMult)
   {
      double lockedR = MathFloor((rMultiple - lastTrailingStartRMult) / lastTrailingStepRMult) * lastTrailingStepRMult;
      if(lockedR < 0) lockedR = 0;
      double trailR = lastTrailingSlRMult + lockedR;
      double trailSl = (type == OP_BUY) ? (openPrice + (riskPrice * trailR)) : (openPrice - (riskPrice * trailR));
      if((type == OP_BUY && trailSl > newSl) || (type == OP_SELL && (newSl == 0 || trailSl < newSl)))
      {
         newSl = trailSl;
         shouldModify = true;
         lastTrailingActivated = true;
      }
   }

   int holdSec = (int)(TimeCurrent() - OrderOpenTime());
   if(lastTrailingEnabled && lastTimeBasedTrailingEnabled && lastTimeBasedTrailingAfterSec > 0 && holdSec >= lastTimeBasedTrailingAfterSec && rMultiple >= lastTimeBasedTrailingMinRMult)
   {
      double timeTrailR = lastTimeBasedTrailingSlRMult;
      if(timeTrailR < 0) timeTrailR = 0;
      double timeTrailSl = (type == OP_BUY) ? (openPrice + (riskPrice * timeTrailR)) : (openPrice - (riskPrice * timeTrailR));
      if((type == OP_BUY && timeTrailSl > newSl) || (type == OP_SELL && (newSl == 0 || timeTrailSl < newSl)))
      {
         newSl = timeTrailSl;
         shouldModify = true;
         lastTrailingActivated = true;
      }
   }

   if(!shouldModify)
      return;

   newSl = NormalizeDouble(newSl, Digits);
   if(MathAbs(newSl - currentSl) < (Point * 2))
      return;

   if(OrderModify(lastOpenTicket, openPrice, newSl, tp, 0, clrGold))
   {
      lastLastAppliedStopLoss = newSl;
      SaveTradeState();
      DebugPrint("managed trade ticket=" + IntegerToString(lastOpenTicket) + " new_sl=" + DoubleToString(newSl, Digits) + " r=" + DoubleToString(rMultiple, 2));
   }
   else
   {
      DebugPrint("OrderModify failed ticket=" + IntegerToString(lastOpenTicket) + " err=" + IntegerToString(GetLastError()));
   }
}

double ExitTolerancePrice()
{
   int spreadPoints = (int)MarketInfo(Symbol(), MODE_SPREAD);
   double tolerance = MathMax(Point * 10, spreadPoints * Point * 1.5);
   return tolerance;
}

string DetectExitReason()
{
   if(!OrderSelect(lastOpenTicket, SELECT_BY_TICKET, MODE_HISTORY))
      return "UNKNOWN_EXIT";

   int type = OrderType();
   double closePrice = OrderClosePrice();
   double openPrice = OrderOpenPrice();
   double finalSl = OrderStopLoss();
   double finalTp = OrderTakeProfit();
   double tolerance = ExitTolerancePrice();
   double pnl = OrderProfit() + OrderSwap() + OrderCommission();

   bool isBuy = (type == OP_BUY);
   bool nearInitialSl = (lastOpenInitialStopLoss > 0 && MathAbs(closePrice - lastOpenInitialStopLoss) <= tolerance);
   bool beyondInitialSl = false;
   if(lastOpenInitialStopLoss > 0)
      beyondInitialSl = isBuy ? (closePrice < lastOpenInitialStopLoss - tolerance) : (closePrice > lastOpenInitialStopLoss + tolerance);
   bool nearFinalSl = (finalSl > 0 && MathAbs(closePrice - finalSl) <= tolerance);
   bool beyondFinalSl = false;
   if(finalSl > 0)
      beyondFinalSl = isBuy ? (closePrice < finalSl - tolerance) : (closePrice > finalSl + tolerance);
   bool nearTp = (lastOpenInitialTp1 > 0 && MathAbs(closePrice - lastOpenInitialTp1) <= tolerance) || (finalTp > 0 && MathAbs(closePrice - finalTp) <= tolerance);
   bool beyondTp = false;
   double refTp = (lastOpenInitialTp1 > 0) ? lastOpenInitialTp1 : finalTp;
   if(refTp > 0)
      beyondTp = isBuy ? (closePrice > refTp + tolerance) : (closePrice < refTp - tolerance);

   double beBuffer = lastOpenInitialRiskPrice * lastBreakEvenBufferRMult;
   double beLevel = isBuy ? (openPrice + beBuffer) : (openPrice - beBuffer);
   bool nearBe = MathAbs(closePrice - beLevel) <= tolerance;

   if((nearTp || beyondTp) && pnl > 0)
      return beyondTp ? "GAP_SLIPPAGE_TP" : "TAKE_PROFIT";
   if((nearInitialSl || nearFinalSl || beyondInitialSl || beyondFinalSl) && pnl < 0)
   {
      if(beyondInitialSl || beyondFinalSl)
         return "GAP_SLIPPAGE_SL";
      if(lastTrailingActivated)
         return "TRAILING_STOP";
      return "STOP_LOSS";
   }
   if((nearBe || nearFinalSl) && MathAbs(pnl) <= (lastOpenInitialRiskPrice * 0.25))
   {
      if(lastBreakEvenActivated)
         return "BREAKEVEN_STOP";
   }
   if(lastTrailingActivated && nearFinalSl)
      return "TRAILING_STOP";
   if(MathAbs(pnl) <= (lastOpenInitialRiskPrice * 0.25) && lastBreakEvenActivated)
      return "BREAKEVEN_STOP";
   return "UNKNOWN_EXIT";
}

void CheckClosedTradeReport()
{
   if(lastOpenTicket <= 0 || lastOpenSignalId == "")
      return;

   if(IsTicketStillOpen(lastOpenTicket))
      return;

   if(OrderSelect(lastOpenTicket, SELECT_BY_TICKET, MODE_HISTORY))
   {
      double pnl = OrderProfit() + OrderSwap() + OrderCommission();
      string outcome = "BREAKEVEN";
      if(pnl > 0.0)
         outcome = "WIN";
      else if(pnl < 0.0)
         outcome = "LOSS";
      string exitReason = DetectExitReason();
      SendExecutionCloseReport(lastOpenSignalId, lastOpenTicket, OrderLots(), OrderClosePrice(), outcome, pnl, exitReason);
      if(outcome == "LOSS")
         CooldownUntil = TimeCurrent() + (MaxSignalAgeSec > 0 ? MaxSignalAgeSec : 180);
      SaveTradeState();
      DebugPrint("reported closed trade ticket=" + IntegerToString(lastOpenTicket) + " outcome=" + outcome + " exit_reason=" + exitReason + " pnl=" + DoubleToString(pnl, 2));
   }

   lastOpenTicket = -1;
   lastOpenSignalId = "";
   lastOpenInitialRiskPrice = 0;
   lastOpenInitialStopLoss = 0;
   lastOpenInitialTp1 = 0;
   lastLastAppliedStopLoss = 0;
   lastBreakEvenActivated = false;
   lastTrailingActivated = false;
   ClearTradeState();
}

void OnTick()
{
   ManageOpenTrade();
   CheckClosedTradeReport();

   if(!EnableTrading)
   {
      DebugPrint("skip: trading disabled");
      return;
   }
   if(!IsSupportedChartSymbol())
   {
      DebugPrint("skip: unsupported chart symbol " + Symbol());
      return;
   }
   if(TimeCurrent() < CooldownUntil)
   {
      DebugPrint("skip: cooldown active");
      return;
   }
   if(IsDailyLossLimitHit())
   {
      DebugPrint("skip: daily loss limit hit");
      return;
   }
   
   if(CountCurrentOrders() > 0)
   {
      DebugPrint("skip: existing order for symbol/magic");
      return;
   }

   string json = HttpGetLatestSignal();
   if(StringLen(json) < 20)
   {
      DebugPrint("skip: empty flattened signal payload");
      return;
   }

   string signalId = JsonGetString(json, "signal_id");
   string symbol = JsonGetString(json, "symbol");
   string timestampUtc = JsonGetString(json, "timestamp_utc");
   string side = JsonGetString(json, "side");
   double stopLoss = JsonGetDouble(json, "stop_loss");
   double entryMin = JsonGetDouble(json, "entry_zone_min");
   double entryMax = JsonGetDouble(json, "entry_zone_max");
   double tp1 = JsonGetDouble(json, "tp1_price");
   double breakEvenRMult = JsonGetDouble(json, "break_even_r_mult");
   double breakEvenBufferRMult = JsonGetDouble(json, "break_even_buffer_r_mult");
   double trailingStartRMult = JsonGetDouble(json, "trailing_start_r_mult");
   double trailingStepRMult = JsonGetDouble(json, "trailing_step_r_mult");
   double trailingSlRMult = JsonGetDouble(json, "trailing_sl_r_mult");
   double timeBasedTrailingAfterSec = JsonGetDouble(json, "time_based_trailing_after_sec");
   double timeBasedTrailingMinRMult = JsonGetDouble(json, "time_based_trailing_min_r_mult");
   double timeBasedTrailingSlRMult = JsonGetDouble(json, "time_based_trailing_sl_r_mult");
   double trailingEnabledRaw = JsonGetDouble(json, "trailing_enabled");
   int maxAge = (int)JsonGetDouble(json, "max_signal_age_sec");
   if(maxAge <= 0) maxAge = MaxSignalAgeSec;

   if(signalId == "")
   {
      DebugPrint("skip: missing signal_id");
      return;
   }
   datetime signalTs = ParseIsoTimestamp(timestampUtc);
   if(StringLen(timestampUtc) > 0 && signalTs <= 0)
   {
      DebugPrint("skip: invalid signal timestamp raw=" + timestampUtc);
      return;
   }
   if(signalTs > 0)
   {
      int signalAge = (int)(TimeGMT() - signalTs);
      if(signalAge < 0)
      {
         DebugPrint("skip: signal timestamp is in the future age=" + IntegerToString(signalAge) + " raw=" + timestampUtc + " gmt_now=" + TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS));
         SendExecutionReject(signalId, symbol, side, "future_signal_timestamp", 0, 0, 0);
         return;
      }
      if(signalAge > maxAge)
      {
         DebugPrint("skip: stale signal age=" + IntegerToString(signalAge) + " max=" + IntegerToString(maxAge) + " raw=" + timestampUtc + " gmt_now=" + TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS));
         SendExecutionReject(signalId, symbol, side, "stale_signal", 0, 0, 0);
         return;
      }
   }
   if(signalId == lastSignalId)
   {
      DebugPrint("skip: signal already processed " + signalId);
      SendExecutionReject(signalId, symbol, side, "signal_already_processed", 0, 0, 0);
      return;
   }
   if(lastSignalTimestamp > 0 && signalTs > 0 && signalTs <= lastSignalTimestamp)
   {
      DebugPrint("skip: signal timestamp not newer");
      return;
   }
   if(NormalizeBridgeSymbol(symbol) != NormalizeBridgeSymbol(Symbol()))
   {
      DebugPrint("skip: symbol mismatch signal=" + symbol + " chart=" + Symbol());
      SendExecutionReject(signalId, symbol, side, "symbol_mismatch", 0, 0, 0);
      return;
   }

   int spread = (int)MarketInfo(Symbol(), MODE_SPREAD);
   if(spread > MaxSpreadPoints)
   {
      DebugPrint("skip: spread too high current=" + IntegerToString(spread) + " max=" + IntegerToString(MaxSpreadPoints));
      SendExecutionReject(signalId, symbol, side, "spread_too_high", (side == "BUY") ? Ask : Bid, 0, 0);
      return;
   }

   double price = (side == "BUY") ? Ask : Bid;
   if(price < entryMin || price > entryMax)
   {
      DebugPrint("skip: price outside entry zone price=" + DoubleToString(price, Digits) + " min=" + DoubleToString(entryMin, Digits) + " max=" + DoubleToString(entryMax, Digits));
      SendExecutionReject(signalId, symbol, side, "price_outside_entry_zone", price, entryMin, entryMax);
      return;
   }

   double zoneWidth = entryMax - entryMin;
   if(zoneWidth <= 0)
   {
      DebugPrint("skip: invalid entry zone width");
      SendExecutionReject(signalId, symbol, side, "invalid_entry_zone_width", price, entryMin, entryMax);
      return;
   }
   double zoneBuffer = zoneWidth * EntryZoneExecutionBufferRatio;
   double effectiveMin = entryMin + zoneBuffer;
   double effectiveMax = entryMax - zoneBuffer;
   if(effectiveMin >= effectiveMax)
   {
      effectiveMin = entryMin;
      effectiveMax = entryMax;
   }
   if(price < effectiveMin || price > effectiveMax)
   {
      DebugPrint("skip: price too close to zone edge price=" + DoubleToString(price, Digits) + " eff_min=" + DoubleToString(effectiveMin, Digits) + " eff_max=" + DoubleToString(effectiveMax, Digits));
      SendExecutionReject(signalId, symbol, side, "price_too_close_to_zone_edge", price, effectiveMin, effectiveMax);
      return;
   }

   double edgeRatio = 0.5;
   if(side == "BUY")
      edgeRatio = (entryMax - price) / zoneWidth;
   else if(side == "SELL")
      edgeRatio = (price - entryMin) / zoneWidth;
   if(edgeRatio <= ExtremeEntryBlockRatio)
   {
      DebugPrint("skip: extreme edge entry blocked ratio=" + DoubleToString(edgeRatio, 2));
      SendExecutionReject(signalId, symbol, side, "extreme_edge_entry_blocked", price, entryMin, entryMax);
      return;
   }

   double slPoints = MathAbs(price - stopLoss) / Point;
   if(slPoints <= 0)
   {
      DebugPrint("skip: invalid stop loss distance");
      return;
   }

   double lot = CalcLot(slPoints);
   if(lot < MarketInfo(Symbol(), MODE_MINLOT))
   {
      DebugPrint("skip: calculated lot below broker minimum");
      return;
   }

   int cmd = (side == "BUY") ? OP_BUY : OP_SELL;
   RefreshRates();
   int ticket = OrderSend(Symbol(), cmd, lot, price, Slippage, stopLoss, tp1, signalId, MagicNumber, 0, clrGold);
   if(ticket > 0)
   {
      lastSignalId = signalId;
      lastProcessedAt = TimeCurrent();
      lastSignalTimestamp = signalTs;
      lastOpenTicket = ticket;
      lastOpenSignalId = signalId;
      lastOpenInitialRiskPrice = MathAbs(price - stopLoss);
      lastOpenInitialStopLoss = stopLoss;
      lastOpenInitialTp1 = tp1;
      lastLastAppliedStopLoss = stopLoss;
      lastBreakEvenActivated = false;
      lastTrailingActivated = false;
      lastBreakEvenRMult = (breakEvenRMult > 0) ? breakEvenRMult : BreakEvenRMultInput;
      lastBreakEvenBufferRMult = (breakEvenBufferRMult >= 0) ? breakEvenBufferRMult : BreakEvenBufferRMultInput;
      lastTrailingStartRMult = (trailingStartRMult > 0) ? trailingStartRMult : TrailingStartRMultInput;
      lastTrailingStepRMult = (trailingStepRMult > 0) ? trailingStepRMult : TrailingStepRMultInput;
      lastTrailingSlRMult = (trailingSlRMult > 0) ? trailingSlRMult : TrailingSlRMultInput;
      lastTrailingEnabled = (trailingEnabledRaw == 0) ? false : true;
      lastTimeBasedTrailingEnabled = TimeBasedTrailingEnabledInput;
      lastTimeBasedTrailingAfterSec = (timeBasedTrailingAfterSec > 0) ? (int)timeBasedTrailingAfterSec : TimeBasedTrailingAfterSecInput;
      lastTimeBasedTrailingMinRMult = (timeBasedTrailingMinRMult >= 0) ? timeBasedTrailingMinRMult : TimeBasedTrailingMinRMultInput;
      lastTimeBasedTrailingSlRMult = (timeBasedTrailingSlRMult >= 0) ? timeBasedTrailingSlRMult : TimeBasedTrailingSlRMultInput;
      SaveLastSignalId();
      SaveTradeState();
      Print("Trade opened for signal: ", signalId);
      SendExecutionReport(signalId, ticket, "OPEN", lot, price);
   }
   else
   {
      Print("OrderSend failed: ", GetLastError());
   }
}

int CountCurrentOrders()
{
   int count = 0;
   for(int i = OrdersTotal()-1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == MagicNumber && OrderSymbol() == Symbol())
            count++;
      }
   }
   return count;
}

string JsonEscape(string value)
{
   string escaped = value;
   StringReplace(escaped, "\\", "\\\\");
   StringReplace(escaped, "\"", "\\\"");
   StringReplace(escaped, "\r", " ");
   StringReplace(escaped, "\n", " ");
   StringReplace(escaped, "\t", " ");
   return escaped;
}

void SendExecutionReport(string signalId, int ticket, string type, double lot, double price)
{
   string safeSignalId = JsonEscape(signalId);
   string safeType = JsonEscape(type);
   string url = BridgeBaseUrl + "/execution/report";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat("{\"signal_id\":\"%s\",\"ticket\":%d,\"type\":\"%s\",\"lot\":%G,\"price\":%G}", safeSignalId, ticket, safeType, lot, price);
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   int code = WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
   string response = CharArrayToString(result);
   if(code == -1)
   {
      Print("Execution report failed: ", GetLastError(), " type=", type, " signal=", signalId, " url=", url, " body=", body);
      return;
   }
   if(code < 200 || code >= 300)
   {
      Print("Execution report rejected code=", code, " type=", type, " signal=", signalId, " body=", body, " response=", response);
      return;
   }
   DebugPrint("execution report ok type=" + type + " signal=" + signalId + " code=" + IntegerToString(code));
}

void SendExecutionReject(string signalId, string symbol, string side, string reason, double price, double entryMin, double entryMax)
{
   string safeSignalId = JsonEscape(signalId);
   string safeSymbol = JsonEscape(symbol);
   string safeSide = JsonEscape(side);
   string safeReason = JsonEscape(reason);
   string url = BridgeBaseUrl + "/execution/reject";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat("{\"signal_id\":\"%s\",\"symbol\":\"%s\",\"side\":\"%s\",\"reason\":\"%s\",\"price\":%G,\"entry_zone_min\":%G,\"entry_zone_max\":%G}", safeSignalId, safeSymbol, safeSide, safeReason, price, entryMin, entryMax);
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   int code = WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
   string response = CharArrayToString(result);
   if(code == -1)
   {
      Print("Execution reject report failed: ", GetLastError(), " signal=", signalId, " reason=", reason, " body=", body);
      return;
   }
   if(code < 200 || code >= 300)
   {
      Print("Execution reject report rejected code=", code, " signal=", signalId, " reason=", reason, " body=", body, " response=", response);
      return;
   }
   DebugPrint("execution reject report ok signal=" + signalId + " reason=" + reason + " code=" + IntegerToString(code));
}

void SendExecutionCloseReport(string signalId, int ticket, double lot, double price, string outcome, double pnl, string exitReason)
{
   string safeSignalId = JsonEscape(signalId);
   string safeOutcome = JsonEscape(outcome);
   string safeExitReason = JsonEscape(exitReason);
   string url = BridgeBaseUrl + "/execution/report";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat("{\"signal_id\":\"%s\",\"ticket\":%d,\"type\":\"CLOSE\",\"lot\":%G,\"price\":%G,\"outcome\":\"%s\",\"pnl\":%G,\"exit_reason\":\"%s\",\"initial_risk_price\":%G,\"initial_stop_loss\":%G,\"initial_tp1\":%G,\"last_applied_stop_loss\":%G,\"break_even_activated\":%s,\"trailing_activated\":%s}", safeSignalId, ticket, lot, price, safeOutcome, pnl, safeExitReason, lastOpenInitialRiskPrice, lastOpenInitialStopLoss, lastOpenInitialTp1, lastLastAppliedStopLoss, lastBreakEvenActivated ? "true" : "false", lastTrailingActivated ? "true" : "false");
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   int code = WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
   string response = CharArrayToString(result);
   if(code == -1)
   {
      Print("Execution close report failed: ", GetLastError(), " signal=", signalId, " url=", url, " body=", body);
      return;
   }
   if(code < 200 || code >= 300)
   {
      Print("Execution close report rejected code=", code, " signal=", signalId, " body=", body, " response=", response);
      return;
   }
   DebugPrint("execution close report ok signal=" + signalId + " code=" + IntegerToString(code));
}

bool IsTicketStillOpen(int ticket)
{
   for(int i = OrdersTotal()-1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderTicket() == ticket)
            return true;
      }
   }
   return false;
}

bool IsDailyLossLimitHit()
{
   double lossPct = 0;
   if(DayStartEquity > 0)
      lossPct = ((DayStartEquity - AccountEquity()) / DayStartEquity) * 100.0;
   return lossPct >= MaxDailyLossPercent;
}

double CalcLot(double slPoints)
{
   double riskAmount = AccountEquity() * (RiskPercent / 100.0);
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double pointValuePerLot = tickValue;
   if(pointValuePerLot <= 0) pointValuePerLot = 1.0;

   double rawLot = riskAmount / (slPoints * pointValuePerLot);
   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   double step = MarketInfo(Symbol(), MODE_LOTSTEP);

   double lot = MathFloor(rawLot / step) * step;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;
   return NormalizeDouble(lot, 2);
}

string HttpGetLatestSignal()
{
   string url = BridgeBaseUrl + "/signal/latest";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\n";
   char data[];
   char result[];
   string resultHeaders;
   int timeout = 5000;

   int code = WebRequest("GET", url, headers, timeout, data, result, resultHeaders);
   if(code == -1)
   {
      Print("WebRequest failed: ", GetLastError());
      DebugPrint("request url=" + url);
      return "";
   }

   string response = CharArrayToString(result);
   DebugPrint("http code=" + IntegerToString(code));
   if(DebugLogging)
      DebugPrint("raw response=" + response);
   return FlattenSignalResponse(response);
}

string FlattenSignalResponse(string response)
{
   if(StringFind(response, "\"signal\":null") >= 0)
   {
      DebugPrint("skip: no signal available");
      return "";
   }
   if(StringFind(response, "\"news_blocked\":true") >= 0)
   {
      Print("Trading blocked by news filter");
      return "";
   }
   if(StringFind(response, "\"status\":\"BLOCKED_BY_NEWS\"") >= 0)
   {
      Print("Signal blocked by news filter");
      return "";
   }

   string signalId = JsonGetNestedString(response, "bridge_contract", "signal_id");
   string symbol = JsonGetNestedString(response, "bridge_contract", "symbol");
   string side = JsonGetNestedString(response, "bridge_contract", "side");
   double stopLoss = JsonGetNestedDouble(response, "bridge_contract", "stop_loss");
   double maxAge = JsonGetNestedDouble(response, "bridge_contract", "max_signal_age_sec");
   double entryMin = JsonGetNestedDouble(response, "bridge_contract", "entry_zone_min");
   double entryMax = JsonGetNestedDouble(response, "bridge_contract", "entry_zone_max");
   double tp1 = JsonGetNestedDouble(response, "bridge_contract", "tp1_price");
   double breakEvenRMult = JsonGetNestedDouble(response, "bridge_contract", "break_even_r_mult");
   double breakEvenBufferRMult = JsonGetNestedDouble(response, "bridge_contract", "break_even_buffer_r_mult");
   double trailingStartRMult = JsonGetNestedDouble(response, "bridge_contract", "trailing_start_r_mult");
   double trailingStepRMult = JsonGetNestedDouble(response, "bridge_contract", "trailing_step_r_mult");
   double trailingSlRMult = JsonGetNestedDouble(response, "bridge_contract", "trailing_sl_r_mult");
   double timeBasedTrailingAfterSec = JsonGetNestedDouble(response, "bridge_contract", "time_based_trailing_after_sec");
   double timeBasedTrailingMinRMult = JsonGetNestedDouble(response, "bridge_contract", "time_based_trailing_min_r_mult");
   double timeBasedTrailingSlRMult = JsonGetNestedDouble(response, "bridge_contract", "time_based_trailing_sl_r_mult");
   double trailingEnabled = JsonGetNestedDouble(response, "bridge_contract", "trailing_enabled");

   string timestampUtc = JsonGetNestedString(response, "bridge_contract", "timestamp_utc");
   return StringFormat("{\"signal_id\":\"%s\",\"symbol\":\"%s\",\"side\":\"%s\",\"timestamp_utc\":\"%s\",\"stop_loss\":%G,\"entry_zone_min\":%G,\"entry_zone_max\":%G,\"tp1_price\":%G,\"max_signal_age_sec\":%G,\"break_even_r_mult\":%G,\"break_even_buffer_r_mult\":%G,\"trailing_start_r_mult\":%G,\"trailing_step_r_mult\":%G,\"trailing_sl_r_mult\":%G,\"time_based_trailing_after_sec\":%G,\"time_based_trailing_min_r_mult\":%G,\"time_based_trailing_sl_r_mult\":%G,\"trailing_enabled\":%G}", signalId, symbol, side, timestampUtc, stopLoss, entryMin, entryMax, tp1, maxAge, breakEvenRMult, breakEvenBufferRMult, trailingStartRMult, trailingStepRMult, trailingSlRMult, timeBasedTrailingAfterSec, timeBasedTrailingMinRMult, timeBasedTrailingSlRMult, trailingEnabled);
}

string JsonGetString(string json, string key)
{
   string pattern = "\"" + key + "\":\"";
   int start = StringFind(json, pattern);
   if(start < 0) return "";
   start += StringLen(pattern);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double JsonGetDouble(string json, string key)
{
   string pattern = "\"" + key + "\":";
   int start = StringFind(json, pattern);
   if(start < 0) return 0;
   start += StringLen(pattern);
   int end1 = StringFind(json, ",", start);
   int end2 = StringFind(json, "}", start);
   int end = end1;
   if(end < 0 || (end2 >= 0 && end2 < end)) end = end2;
   if(end < 0) end = StringLen(json);
   string val = StringTrimLeft(StringTrimRight(StringSubstr(json, start, end - start)));
   return StrToDouble(val);
}

string JsonGetNestedString(string json, string parent, string key)
{
   return JsonGetString(json, key);
}

double JsonGetNestedDouble(string json, string parent, string key)
{
   return JsonGetDouble(json, key);
}

double JsonGetDoubleFromSection(string json, string sectionKey, string key)
{
   int secStart = StringFind(json, sectionKey);
   if(secStart < 0) return 0;
   int braceStart = StringFind(json, "{", secStart);
   int braceEnd = StringFind(json, "}", braceStart);
   if(braceStart < 0 || braceEnd < 0) return 0;
   string section = StringSubstr(json, braceStart, braceEnd - braceStart + 1);
   return JsonGetDouble(section, key);
}

double JsonGetDoubleFromArrayObject(string json, string sectionKey, string key)
{
   int secStart = StringFind(json, sectionKey);
   if(secStart < 0) return 0;
   int bracketStart = StringFind(json, "[", secStart);
   int braceStart = StringFind(json, "{", bracketStart);
   int braceEnd = StringFind(json, "}", braceStart);
   if(bracketStart < 0 || braceStart < 0 || braceEnd < 0) return 0;
   string section = StringSubstr(json, braceStart, braceEnd - braceStart + 1);
   return JsonGetDouble(section, key);
}
