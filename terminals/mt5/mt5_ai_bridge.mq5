#property strict
#include <Trade/Trade.mqh>

input string BridgeBaseUrl = "http://127.0.0.1:8000";
input string BridgeToken = "change-me-token";
input double RiskPercent = 0.5;
input double MaxDailyLossPercent = 2.0;
input int MaxSpreadPoints = 120;
input int MaxSignalAgeSec = 180;
input int SlippagePoints = 20;
input long MagicNumber = 20260430;
input bool EnableTrading = true;
input bool DebugLogging = true;
input int PollIntervalSeconds = 3;
input bool LogOnlyOnResponseChange = true;
input double EntryZoneExecutionBufferRatio = 0.25;
input double ExtremeEntryBlockRatio = 0.20;
input double BreakEvenRMultInput = 1.00;
input double BreakEvenBufferRMultInput = 0.10;
input double TrailingStartRMultInput = 1.40;
input double TrailingStepRMultInput = 0.45;
input double TrailingSlRMultInput = 0.85;
input bool TimeBasedTrailingEnabledInput = true;
input int TimeBasedTrailingAfterSecInput = 600;
input double TimeBasedTrailingMinRMultInput = 0.25;
input double TimeBasedTrailingSlRMultInput = 0.18;

CTrade trade;
string lastSignalId = "";
datetime lastProcessedAt = 0;
datetime lastSignalTimestamp = 0;
ulong lastPositionTicket = 0;
string lastOpenSignalId = "";
string lastRawResponse = "";
datetime lastPollAt = 0;
double lastOpenInitialRiskPrice = 0;
double lastOpenInitialStopLoss = 0;
double lastOpenInitialTp1 = 0;
double lastLastAppliedStopLoss = 0;
double lastBreakEvenRMult = 0.85;
double lastBreakEvenBufferRMult = 0.12;
double lastTrailingStartRMult = 1.2;
double lastTrailingStepRMult = 0.4;
double lastTrailingSlRMult = 0.85;
bool lastTrailingEnabled = true;
bool lastTimeBasedTrailingEnabled = true;
int lastTimeBasedTrailingAfterSec = 600;
double lastTimeBasedTrailingMinRMult = 0.25;
double lastTimeBasedTrailingSlRMult = 0.18;
bool lastBreakEvenActivated = false;
bool lastTrailingActivated = false;
double dayStartEquity = 0;
datetime cooldownUntil = 0;

string NormalizeBridgeSymbol(string symbol)
{
   string normalized = symbol;
   StringToUpper(normalized);
   string compact = normalized;
   StringReplace(compact, ".", "");
   StringReplace(compact, "_", "");
   StringReplace(compact, "-", "");

   if(normalized == "GOLD" || compact == "GOLD") return "XAUUSD";
   if(StringFind(compact, "XAUUSD") == 0) return "XAUUSD";
   if(StringFind(compact, "GOLD") == 0) return "XAUUSD";
   return normalized;
}

void DebugPrint(string message)
{
   if(DebugLogging)
      Print("DEBUG: ", message);
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

   MqlDateTime dt;
   dt.year = (int)StringToInteger(StringSubstr(s, 0, 4));
   dt.mon = (int)StringToInteger(StringSubstr(s, 5, 2));
   dt.day = (int)StringToInteger(StringSubstr(s, 8, 2));
   dt.hour = (int)StringToInteger(StringSubstr(s, 11, 2));
   dt.min = (int)StringToInteger(StringSubstr(s, 14, 2));
   dt.sec = (int)StringToInteger(StringSubstr(s, 17, 2));
   return StructToTime(dt);
}

string PersistKey(string suffix)
{
   return "XAU_MT5_BRIDGE_" + IntegerToString((int)MagicNumber) + "_" + suffix;
}

void SaveState()
{
   GlobalVariableSet(PersistKey("last_signal_ts"), (double)lastSignalTimestamp);
   GlobalVariableSet(PersistKey("last_processed_at"), (double)lastProcessedAt);
   GlobalVariableSet(PersistKey("cooldown_until"), (double)cooldownUntil);
   GlobalVariableSet(PersistKey("position_ticket"), (double)lastPositionTicket);
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
   GlobalVariableSet(PersistKey("last_signal_id_len"), StringLen(lastSignalId));
   GlobalVariableSet(PersistKey("open_signal_id_len"), StringLen(lastOpenSignalId));
   for(int i=0; i<StringLen(lastSignalId) && i<64; i++) GlobalVariableSet(PersistKey("last_signal_id_" + IntegerToString(i)), StringGetCharacter(lastSignalId, i));
   for(int j=0; j<StringLen(lastOpenSignalId) && j<64; j++) GlobalVariableSet(PersistKey("open_signal_id_" + IntegerToString(j)), StringGetCharacter(lastOpenSignalId, j));
}

string LoadStringState(string prefix)
{
   int len = 0;
   if(GlobalVariableCheck(PersistKey(prefix + "_len")))
      len = (int)GlobalVariableGet(PersistKey(prefix + "_len"));
   string result = "";
   for(int i=0; i<len && i<64; i++)
   {
      if(!GlobalVariableCheck(PersistKey(prefix + "_" + IntegerToString(i)))) break;
      ushort ch = (ushort)GlobalVariableGet(PersistKey(prefix + "_" + IntegerToString(i)));
      result += ShortToString(ch);
   }
   return result;
}

void RestoreState()
{
   if(GlobalVariableCheck(PersistKey("last_signal_ts"))) lastSignalTimestamp = (datetime)GlobalVariableGet(PersistKey("last_signal_ts"));
   if(GlobalVariableCheck(PersistKey("last_processed_at"))) lastProcessedAt = (datetime)GlobalVariableGet(PersistKey("last_processed_at"));
   if(GlobalVariableCheck(PersistKey("cooldown_until"))) cooldownUntil = (datetime)GlobalVariableGet(PersistKey("cooldown_until"));
   if(GlobalVariableCheck(PersistKey("position_ticket"))) lastPositionTicket = (ulong)GlobalVariableGet(PersistKey("position_ticket"));
   if(GlobalVariableCheck(PersistKey("risk"))) lastOpenInitialRiskPrice = GlobalVariableGet(PersistKey("risk"));
   if(GlobalVariableCheck(PersistKey("sl"))) lastOpenInitialStopLoss = GlobalVariableGet(PersistKey("sl"));
   if(GlobalVariableCheck(PersistKey("tp1"))) lastOpenInitialTp1 = GlobalVariableGet(PersistKey("tp1"));
   if(GlobalVariableCheck(PersistKey("last_sl"))) lastLastAppliedStopLoss = GlobalVariableGet(PersistKey("last_sl"));
   if(GlobalVariableCheck(PersistKey("be_r"))) lastBreakEvenRMult = GlobalVariableGet(PersistKey("be_r"));
   if(GlobalVariableCheck(PersistKey("be_buf"))) lastBreakEvenBufferRMult = GlobalVariableGet(PersistKey("be_buf"));
   if(GlobalVariableCheck(PersistKey("trail_start"))) lastTrailingStartRMult = GlobalVariableGet(PersistKey("trail_start"));
   if(GlobalVariableCheck(PersistKey("trail_step"))) lastTrailingStepRMult = GlobalVariableGet(PersistKey("trail_step"));
   if(GlobalVariableCheck(PersistKey("trail_sl"))) lastTrailingSlRMult = GlobalVariableGet(PersistKey("trail_sl"));
   if(GlobalVariableCheck(PersistKey("trail_enabled"))) lastTrailingEnabled = GlobalVariableGet(PersistKey("trail_enabled")) > 0;
   if(GlobalVariableCheck(PersistKey("time_trail_enabled"))) lastTimeBasedTrailingEnabled = GlobalVariableGet(PersistKey("time_trail_enabled")) > 0;
   if(GlobalVariableCheck(PersistKey("time_trail_after"))) lastTimeBasedTrailingAfterSec = (int)GlobalVariableGet(PersistKey("time_trail_after"));
   if(GlobalVariableCheck(PersistKey("time_trail_min_r"))) lastTimeBasedTrailingMinRMult = GlobalVariableGet(PersistKey("time_trail_min_r"));
   if(GlobalVariableCheck(PersistKey("time_trail_sl_r"))) lastTimeBasedTrailingSlRMult = GlobalVariableGet(PersistKey("time_trail_sl_r"));
   if(GlobalVariableCheck(PersistKey("be_active"))) lastBreakEvenActivated = GlobalVariableGet(PersistKey("be_active")) > 0;
   if(GlobalVariableCheck(PersistKey("trail_active"))) lastTrailingActivated = GlobalVariableGet(PersistKey("trail_active")) > 0;
   lastSignalId = LoadStringState("last_signal_id");
   lastOpenSignalId = LoadStringState("open_signal_id");
}

bool IsDailyLossLimitHit()
{
   double lossPct = 0.0;
   if(dayStartEquity > 0)
      lossPct = ((dayStartEquity - AccountInfoDouble(ACCOUNT_EQUITY)) / dayStartEquity) * 100.0;
   return lossPct >= MaxDailyLossPercent;
}

int CountCurrentPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      count++;
      lastPositionTicket = ticket;
   }
   return count;
}

double CalcLot(double slPoints)
{
   double riskAmount = AccountInfoDouble(ACCOUNT_EQUITY) * (RiskPercent / 100.0);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double pointSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double pointValuePerLot = 0.0;
   if(tickValue > 0 && tickSize > 0 && pointSize > 0)
      pointValuePerLot = tickValue * (pointSize / tickSize);
   if(pointValuePerLot <= 0) pointValuePerLot = tickValue;
   if(pointValuePerLot <= 0) pointValuePerLot = 1.0;
   double rawLot = riskAmount / (slPoints * pointValuePerLot);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0) step = 0.01;
   double lot = MathFloor(rawLot / step) * step;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;
   return NormalizeDouble(lot, 2);
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
   string val = StringSubstr(json, start, end - start);
   StringTrimLeft(val);
   StringTrimRight(val);
   return StringToDouble(val);
}

string HttpGetLatestSignal()
{
   string url = BridgeBaseUrl + "/signal/latest";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\n";
   char data[];
   char result[];
   string resultHeaders;
   int code = WebRequest("GET", url, headers, 5000, data, result, resultHeaders);
   if(code == -1)
   {
      Print("WebRequest failed: ", GetLastError());
      return "";
   }
   string response = CharArrayToString(result);
   if(DebugLogging)
   {
      bool shouldLog = true;
      if(LogOnlyOnResponseChange && response == lastRawResponse)
         shouldLog = false;
      if(shouldLog)
         DebugPrint("raw response=" + response);
   }
   lastRawResponse = response;
   return FlattenSignalResponse(response);
}

string FlattenSignalResponse(string response)
{
   if(StringFind(response, "\"signal\":null") >= 0) return "";
   if(StringFind(response, "\"news_blocked\":true") >= 0) return "";
   if(StringFind(response, "\"status\":\"BLOCKED_BY_NEWS\"") >= 0) return "";
   string signalId = JsonGetString(response, "signal_id");
   string symbol = JsonGetString(response, "symbol");
   string side = JsonGetString(response, "side");
   string timestampUtc = JsonGetString(response, "timestamp_utc");
   double stopLoss = JsonGetDouble(response, "stop_loss");
   double maxAge = JsonGetDouble(response, "max_signal_age_sec");
   double entryMin = JsonGetDouble(response, "entry_zone_min");
   double entryMax = JsonGetDouble(response, "entry_zone_max");
   double tp1 = JsonGetDouble(response, "tp1_price");
   double breakEvenRMult = JsonGetDouble(response, "break_even_r_mult");
   double breakEvenBufferRMult = JsonGetDouble(response, "break_even_buffer_r_mult");
   double trailingStartRMult = JsonGetDouble(response, "trailing_start_r_mult");
   double trailingStepRMult = JsonGetDouble(response, "trailing_step_r_mult");
   double trailingSlRMult = JsonGetDouble(response, "trailing_sl_r_mult");
   double timeBasedTrailingAfterSec = JsonGetDouble(response, "time_based_trailing_after_sec");
   double timeBasedTrailingMinRMult = JsonGetDouble(response, "time_based_trailing_min_r_mult");
   double timeBasedTrailingSlRMult = JsonGetDouble(response, "time_based_trailing_sl_r_mult");
   double trailingEnabled = JsonGetDouble(response, "trailing_enabled");
   return StringFormat("{\"signal_id\":\"%s\",\"symbol\":\"%s\",\"side\":\"%s\",\"timestamp_utc\":\"%s\",\"stop_loss\":%G,\"entry_zone_min\":%G,\"entry_zone_max\":%G,\"tp1_price\":%G,\"max_signal_age_sec\":%G,\"break_even_r_mult\":%G,\"break_even_buffer_r_mult\":%G,\"trailing_start_r_mult\":%G,\"trailing_step_r_mult\":%G,\"trailing_sl_r_mult\":%G,\"time_based_trailing_after_sec\":%G,\"time_based_trailing_min_r_mult\":%G,\"time_based_trailing_sl_r_mult\":%G,\"trailing_enabled\":%G}", signalId, symbol, side, timestampUtc, stopLoss, entryMin, entryMax, tp1, maxAge, breakEvenRMult, breakEvenBufferRMult, trailingStartRMult, trailingStepRMult, trailingSlRMult, timeBasedTrailingAfterSec, timeBasedTrailingMinRMult, timeBasedTrailingSlRMult, trailingEnabled);
}

void SendExecutionReport(string signalId, string type, double lot, double price, string outcome = "", double pnl = 0.0, string exitReason = "")
{
   string url = BridgeBaseUrl + "/execution/report";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat(
      "{\"signal_id\":\"%s\",\"ticket\":%I64u,\"type\":\"%s\",\"lot\":%G,\"price\":%G,\"outcome\":\"%s\",\"pnl\":%G,\"exit_reason\":\"%s\",\"initial_risk_price\":%G,\"initial_stop_loss\":%G,\"initial_tp1\":%G,\"last_applied_stop_loss\":%G,\"break_even_activated\":%s,\"trailing_activated\":%s,\"terminal\":{\"platform\":\"mt5\",\"symbol_raw\":\"%s\"}}",
      JsonEscape(signalId), lastPositionTicket, JsonEscape(type), lot, price, JsonEscape(outcome), pnl, JsonEscape(exitReason),
      lastOpenInitialRiskPrice, lastOpenInitialStopLoss, lastOpenInitialTp1, lastLastAppliedStopLoss,
      lastBreakEvenActivated ? "true" : "false", lastTrailingActivated ? "true" : "false", JsonEscape(_Symbol)
   );
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   int code = WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
   if(code < 200 || code >= 300)
      DebugPrint("execution report failed code=" + IntegerToString(code));
}

void SendExecutionReject(string signalId, string symbol, string side, string reason, double price, double entryMin, double entryMax)
{
   string url = BridgeBaseUrl + "/execution/reject";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat(
      "{\"signal_id\":\"%s\",\"symbol\":\"%s\",\"side\":\"%s\",\"reason\":\"%s\",\"price\":%G,\"entry_zone_min\":%G,\"entry_zone_max\":%G,\"terminal\":{\"platform\":\"mt5\",\"symbol_raw\":\"%s\"}}",
      JsonEscape(signalId), JsonEscape(symbol), JsonEscape(side), JsonEscape(reason), price, entryMin, entryMax, JsonEscape(_Symbol)
   );
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   int code = WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
   if(code < 200 || code >= 300)
      DebugPrint("execution reject failed code=" + IntegerToString(code));
}

bool SelectManagedPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      lastPositionTicket = ticket;
      return true;
   }
   return false;
}

void ManageOpenPosition()
{
   if(!SelectManagedPosition()) return;

   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSl = PositionGetDouble(POSITION_SL);
   double currentTp = PositionGetDouble(POSITION_TP);
   long type = PositionGetInteger(POSITION_TYPE);
   datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
   double currentPrice = (type == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   double riskPrice = lastOpenInitialRiskPrice;
   if(riskPrice <= 0) riskPrice = MathAbs(openPrice - currentSl);
   if(riskPrice <= 0 && lastOpenInitialTp1 > 0) riskPrice = MathAbs(lastOpenInitialTp1 - openPrice) / 1.35;
   if(riskPrice <= 0) return;

   double profitPrice = (type == POSITION_TYPE_BUY) ? (currentPrice - openPrice) : (openPrice - currentPrice);
   double rMultiple = profitPrice / riskPrice;
   double newSl = currentSl;
   bool shouldModify = false;

   if(lastTrailingEnabled && rMultiple >= lastBreakEvenRMult)
   {
      double beBuffer = riskPrice * lastBreakEvenBufferRMult;
      double beSl = (type == POSITION_TYPE_BUY) ? (openPrice + beBuffer) : (openPrice - beBuffer);
      if((type == POSITION_TYPE_BUY && beSl > newSl) || (type == POSITION_TYPE_SELL && (newSl == 0 || beSl < newSl)))
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
      double trailSl = (type == POSITION_TYPE_BUY) ? (openPrice + (riskPrice * trailR)) : (openPrice - (riskPrice * trailR));
      if((type == POSITION_TYPE_BUY && trailSl > newSl) || (type == POSITION_TYPE_SELL && (newSl == 0 || trailSl < newSl)))
      {
         newSl = trailSl;
         shouldModify = true;
         lastTrailingActivated = true;
      }
   }

   int holdSec = (int)(TimeCurrent() - openTime);
   if(lastTrailingEnabled && lastTimeBasedTrailingEnabled && lastTimeBasedTrailingAfterSec > 0 && holdSec >= lastTimeBasedTrailingAfterSec && rMultiple >= lastTimeBasedTrailingMinRMult)
   {
      double timeTrailSl = (type == POSITION_TYPE_BUY) ? (openPrice + (riskPrice * lastTimeBasedTrailingSlRMult)) : (openPrice - (riskPrice * lastTimeBasedTrailingSlRMult));
      if((type == POSITION_TYPE_BUY && timeTrailSl > newSl) || (type == POSITION_TYPE_SELL && (newSl == 0 || timeTrailSl < newSl)))
      {
         newSl = timeTrailSl;
         shouldModify = true;
         lastTrailingActivated = true;
      }
   }

   if(!shouldModify) return;
   newSl = NormalizeDouble(newSl, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
   if(MathAbs(newSl - currentSl) < (SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 2)) return;

   if(trade.PositionModify(_Symbol, newSl, currentTp))
   {
      lastLastAppliedStopLoss = newSl;
      SaveState();
      DebugPrint("position modified new_sl=" + DoubleToString(newSl, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)));
   }
}

void CheckClosedPositionReport()
{
   if(lastPositionTicket == 0 || lastOpenSignalId == "") return;
   if(SelectManagedPosition()) return;

   HistorySelect(TimeCurrent() - 86400 * 7, TimeCurrent());
   double pnl = 0.0;
   double closePrice = 0.0;
   string outcome = "BREAKEVEN";
   string exitReason = "UNKNOWN_EXIT";
   int deals = HistoryDealsTotal();
   for(int i = deals - 1; i >= 0; i--)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0) continue;
      if((long)HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != MagicNumber) continue;
      if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) continue;
      pnl = HistoryDealGetDouble(dealTicket, DEAL_PROFIT) + HistoryDealGetDouble(dealTicket, DEAL_SWAP) + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
      closePrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
      break;
   }

   if(pnl > 0.0) outcome = "WIN";
   else if(pnl < 0.0) outcome = "LOSS";
   if(pnl < 0.0) exitReason = lastTrailingActivated ? "TRAILING_STOP" : "STOP_LOSS";
   if(pnl > 0.0) exitReason = "TAKE_PROFIT";

   SendExecutionReport(lastOpenSignalId, "CLOSE", 0.0, closePrice, outcome, pnl, exitReason);
   if(outcome == "LOSS") cooldownUntil = TimeCurrent() + (MaxSignalAgeSec > 0 ? MaxSignalAgeSec : 180);

   lastPositionTicket = 0;
   lastOpenSignalId = "";
   lastOpenInitialRiskPrice = 0;
   lastOpenInitialStopLoss = 0;
   lastOpenInitialTp1 = 0;
   lastLastAppliedStopLoss = 0;
   lastBreakEvenActivated = false;
   lastTrailingActivated = false;
   SaveState();
}

int OnInit()
{
   dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(SlippagePoints);
   RestoreState();
   EventSetTimer(PollIntervalSeconds > 0 ? PollIntervalSeconds : 3);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTick()
{
   ManageOpenPosition();
   CheckClosedPositionReport();
}

bool ProcessLatestSignal(string json)
{
   if(StringLen(json) < 20) return false;

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

   if(signalId == "") return false;
   datetime signalTs = ParseIsoTimestamp(timestampUtc);
   if(signalTs > 0)
   {
      int signalAge = (int)(TimeGMT() - signalTs);
      if(signalAge < 0)
      {
         SendExecutionReject(signalId, symbol, side, "future_signal_timestamp", 0, 0, 0);
         return false;
      }
      if(signalAge > maxAge)
      {
         SendExecutionReject(signalId, symbol, side, "stale_signal", 0, 0, 0);
         return false;
      }
   }
   if(signalId == lastSignalId)
   {
      SendExecutionReject(signalId, symbol, side, "signal_already_processed", 0, 0, 0);
      return false;
   }
   if(lastSignalTimestamp > 0 && signalTs > 0 && signalTs <= lastSignalTimestamp) return false;
   if(NormalizeBridgeSymbol(symbol) != NormalizeBridgeSymbol(_Symbol))
   {
      SendExecutionReject(signalId, symbol, side, "symbol_mismatch", 0, 0, 0);
      return false;
   }

   int spread = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > MaxSpreadPoints)
   {
      SendExecutionReject(signalId, symbol, side, "spread_too_high", (side == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID), 0, 0);
      return false;
   }

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = (side == "BUY") ? ask : bid;
   if(price < entryMin || price > entryMax)
   {
      SendExecutionReject(signalId, symbol, side, "price_outside_entry_zone", price, entryMin, entryMax);
      return false;
   }

   double zoneWidth = entryMax - entryMin;
   if(zoneWidth <= 0)
   {
      SendExecutionReject(signalId, symbol, side, "invalid_entry_zone_width", price, entryMin, entryMax);
      return false;
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
      SendExecutionReject(signalId, symbol, side, "price_too_close_to_zone_edge", price, effectiveMin, effectiveMax);
      return false;
   }

   double edgeRatio = 0.5;
   if(side == "BUY") edgeRatio = (entryMax - price) / zoneWidth;
   else if(side == "SELL") edgeRatio = (price - entryMin) / zoneWidth;
   if(edgeRatio <= ExtremeEntryBlockRatio)
   {
      SendExecutionReject(signalId, symbol, side, "extreme_edge_entry_blocked", price, entryMin, entryMax);
      return false;
   }

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double slPoints = MathAbs(price - stopLoss) / point;
   if(slPoints <= 0)
   {
      SendExecutionReject(signalId, symbol, side, "invalid_stop_loss_distance", price, entryMin, entryMax);
      return false;
   }

   int stopsLevelPoints = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevelPoints = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   int minStopDistancePoints = MathMax(stopsLevelPoints, freezeLevelPoints);
   double minStopDistancePrice = minStopDistancePoints * point;
   double slDistancePrice = MathAbs(price - stopLoss);
   double tpDistancePrice = (tp1 > 0) ? MathAbs(tp1 - price) : 0.0;

   if(minStopDistancePoints > 0)
   {
      if(slDistancePrice < minStopDistancePrice)
      {
         DebugPrint(StringFormat("broker stop guard blocked: sl_distance=%G min_required=%G stops_level=%d freeze_level=%d", slDistancePrice, minStopDistancePrice, stopsLevelPoints, freezeLevelPoints));
         SendExecutionReject(signalId, symbol, side, "stop_loss_too_close_for_broker", price, entryMin, entryMax);
         return false;
      }
      if(tp1 > 0 && tpDistancePrice < minStopDistancePrice)
      {
         DebugPrint(StringFormat("broker stop guard blocked: tp_distance=%G min_required=%G stops_level=%d freeze_level=%d", tpDistancePrice, minStopDistancePrice, stopsLevelPoints, freezeLevelPoints));
         SendExecutionReject(signalId, symbol, side, "take_profit_too_close_for_broker", price, entryMin, entryMax);
         return false;
      }
   }

   double lot = CalcLot(slPoints);
   if(lot < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN))
   {
      SendExecutionReject(signalId, symbol, side, "calculated_lot_below_minimum", price, entryMin, entryMax);
      return false;
   }

   bool ok = false;
   if(side == "BUY") ok = trade.Buy(lot, _Symbol, ask, stopLoss, tp1, signalId);
   else if(side == "SELL") ok = trade.Sell(lot, _Symbol, bid, stopLoss, tp1, signalId);

   if(ok)
   {
      lastSignalId = signalId;
      lastProcessedAt = TimeCurrent();
      lastSignalTimestamp = signalTs;
      lastOpenSignalId = signalId;
      lastPositionTicket = trade.ResultOrder();
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
      SaveState();
      SendExecutionReport(signalId, "OPEN", lot, price);
      return true;
   }

   int retcode = (int)trade.ResultRetcode();
   string retcodeDesc = trade.ResultRetcodeDescription();
   string orderComment = trade.ResultComment();
   DebugPrint(StringFormat(
      "trade open failed retcode=%d desc=%s comment=%s side=%s lot=%G price=%G sl=%G tp=%G spread=%d stops_level=%d freeze_level=%d symbol=%s",
      retcode,
      retcodeDesc,
      orderComment,
      side,
      lot,
      price,
      stopLoss,
      tp1,
      spread,
      stopsLevelPoints,
      freezeLevelPoints,
      _Symbol
   ));
   return false;
}

void OnTimer()
{
   lastPollAt = TimeCurrent();
   ManageOpenPosition();
   CheckClosedPositionReport();

   if(!EnableTrading) return;
   if(TimeCurrent() < cooldownUntil) return;
   if(IsDailyLossLimitHit()) return;
   if(CountCurrentPositions() > 0) return;

   string json = HttpGetLatestSignal();
   ProcessLatestSignal(json);
}
