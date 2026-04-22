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

string lastSignalId = "";
datetime lastProcessedAt = 0;
int lastOpenTicket = -1;
string lastOpenSignalId = "";

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

int OnInit()
{
   DayStartEquity = AccountEquity();
   return(INIT_SUCCEEDED);
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
      SendExecutionCloseReport(lastOpenSignalId, lastOpenTicket, OrderLots(), OrderClosePrice(), outcome, pnl);
      DebugPrint("reported closed trade ticket=" + IntegerToString(lastOpenTicket) + " outcome=" + outcome + " pnl=" + DoubleToString(pnl, 2));
   }

   lastOpenTicket = -1;
   lastOpenSignalId = "";
}

void OnTick()
{
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
      DebugPrint("skip: empty or invalid signal response");
      return;
   }

   string signalId = JsonGetString(json, "signal_id");
   string symbol = JsonGetString(json, "symbol");
   string side = JsonGetString(json, "side");
   double stopLoss = JsonGetDouble(json, "stop_loss");
   double entryMin = JsonGetDouble(json, "entry_zone_min");
   double entryMax = JsonGetDouble(json, "entry_zone_max");
   double tp1 = JsonGetDouble(json, "tp1_price");
   int maxAge = (int)JsonGetDouble(json, "max_signal_age_sec");
   if(maxAge <= 0) maxAge = MaxSignalAgeSec;

   if(signalId == "")
   {
      DebugPrint("skip: missing signal_id");
      return;
   }
   if(signalId == lastSignalId)
   {
      DebugPrint("skip: signal already processed " + signalId);
      return;
   }
   if(NormalizeBridgeSymbol(symbol) != NormalizeBridgeSymbol(Symbol()))
   {
      DebugPrint("skip: symbol mismatch signal=" + symbol + " chart=" + Symbol());
      return;
   }

   int spread = (int)MarketInfo(Symbol(), MODE_SPREAD);
   if(spread > MaxSpreadPoints)
   {
      DebugPrint("skip: spread too high current=" + IntegerToString(spread) + " max=" + IntegerToString(MaxSpreadPoints));
      return;
   }

   double price = (side == "BUY") ? Ask : Bid;
   if(price < entryMin || price > entryMax)
   {
      DebugPrint("skip: price outside entry zone price=" + DoubleToString(price, Digits) + " min=" + DoubleToString(entryMin, Digits) + " max=" + DoubleToString(entryMax, Digits));
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
      lastOpenTicket = ticket;
      lastOpenSignalId = signalId;
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

void SendExecutionReport(string signalId, int ticket, string type, double lot, double price)
{
   string url = BridgeBaseUrl + "/execution/report";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat("{\"signal_id\":\"%s\",\"ticket\":%d,\"type\":\"%s\",\"lot\":%G,\"price\":%G}", signalId, ticket, type, lot, price);
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data);
   WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
}

void SendExecutionCloseReport(string signalId, int ticket, double lot, double price, string outcome, double pnl)
{
   string url = BridgeBaseUrl + "/execution/report";
   string headers = "Authorization: Bearer " + BridgeToken + "\r\nContent-Type: application/json\r\n";
   string body = StringFormat("{\"signal_id\":\"%s\",\"ticket\":%d,\"type\":\"CLOSE\",\"lot\":%G,\"price\":%G,\"outcome\":\"%s\",\"pnl\":%G}", signalId, ticket, lot, price, outcome, pnl);
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data);
   WebRequest("POST", url, headers, 5000, data, result, resultHeaders);
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

   string signalId = JsonGetNestedString(response, "signal", "signal_id");
   string symbol = JsonGetNestedString(response, "signal", "symbol");
   string side = JsonGetNestedString(response, "signal", "side");
   double stopLoss = JsonGetNestedDouble(response, "signal", "stop_loss");
   double maxAge = JsonGetNestedDouble(response, "signal", "max_signal_age_sec");
   double entryMin = JsonGetDoubleFromSection(response, "\"entry_zone\"", "min");
   double entryMax = JsonGetDoubleFromSection(response, "\"entry_zone\"", "max");
   double tp1 = JsonGetDoubleFromArrayObject(response, "\"take_profit\"", "price");

   return StringFormat("{\"signal_id\":\"%s\",\"symbol\":\"%s\",\"side\":\"%s\",\"stop_loss\":%G,\"entry_zone_min\":%G,\"entry_zone_max\":%G,\"tp1_price\":%G,\"max_signal_age_sec\":%G}", signalId, symbol, side, stopLoss, entryMin, entryMax, tp1, maxAge);
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
