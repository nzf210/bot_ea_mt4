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

string lastSignalId = "";
datetime lastProcessedAt = 0;

double DayStartEquity = 0;
int ConsecutiveLosses = 0;
datetime CooldownUntil = 0;

int OnInit()
{
   DayStartEquity = AccountEquity();
   return(INIT_SUCCEEDED);
}

void OnTick()
{
   if(!EnableTrading) return;
   if(Symbol() != "XAUUSD") return;
   if(TimeCurrent() < CooldownUntil) return;
   if(IsDailyLossLimitHit()) return;
   if(OrdersTotal() > 0) return;

   string json = HttpGetLatestSignal();
   if(StringLen(json) < 20) return;

   string signalId = JsonGetString(json, "signal_id");
   string symbol = JsonGetString(json, "symbol");
   string side = JsonGetString(json, "side");
   double stopLoss = JsonGetDouble(json, "stop_loss");
   double entryMin = JsonGetDouble(json, "entry_zone_min");
   double entryMax = JsonGetDouble(json, "entry_zone_max");
   double tp1 = JsonGetDouble(json, "tp1_price");
   int maxAge = (int)JsonGetDouble(json, "max_signal_age_sec");
   if(maxAge <= 0) maxAge = MaxSignalAgeSec;

   if(signalId == "" || signalId == lastSignalId) return;
   if(symbol != "XAUUSD") return;

   int spread = (int)MarketInfo(Symbol(), MODE_SPREAD);
   if(spread > MaxSpreadPoints) return;

   double price = (side == "BUY") ? Ask : Bid;
   if(price < entryMin || price > entryMax) return;

   double slPoints = MathAbs(price - stopLoss) / Point;
   if(slPoints <= 0) return;

   double lot = CalcLot(slPoints);
   if(lot < MarketInfo(Symbol(), MODE_MINLOT)) return;

   int cmd = (side == "BUY") ? OP_BUY : OP_SELL;
   RefreshRates();
   int ticket = OrderSend(Symbol(), cmd, lot, price, Slippage, stopLoss, tp1, signalId, MagicNumber, 0, clrGold);
   if(ticket > 0)
   {
      lastSignalId = signalId;
      lastProcessedAt = TimeCurrent();
      Print("Trade opened for signal: ", signalId);
   }
   else
   {
      Print("OrderSend failed: ", GetLastError());
   }
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
      return "";
   }

   string response = CharArrayToString(result);
   return FlattenSignalResponse(response);
}

string FlattenSignalResponse(string response)
{
   if(StringFind(response, '"signal":null') >= 0) return "";

   string signalId = JsonGetNestedString(response, "signal", "signal_id");
   string symbol = JsonGetNestedString(response, "signal", "symbol");
   string side = JsonGetNestedString(response, "signal", "side");
   double stopLoss = JsonGetNestedDouble(response, "signal", "stop_loss");
   double maxAge = JsonGetNestedDouble(response, "signal", "max_signal_age_sec");
   double entryMin = JsonGetDoubleFromSection(response, '"entry_zone"', "min");
   double entryMax = JsonGetDoubleFromSection(response, '"entry_zone"', "max");
   double tp1 = JsonGetDoubleFromSection(response, '"take_profit"', "price");

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
