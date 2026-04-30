#property strict

input string ReceiverUrl = "http://127.0.0.1:8000/market/snapshot";
input string ReceiverToken = "change-me-token";
input bool EnableSender = true;

string IsoTimeUTC()
{
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string JsonNumber(double value, int digits)
{
   return DoubleToString(value, digits);
}

string BuildRecentCandlesJson(string symbol, ENUM_TIMEFRAMES timeframe, int bars, int digits)
{
   string candles = "[";
   for(int i = 0; i < bars; i++)
   {
      if(i > 0) candles += ",";
      candles += StringFormat(
         "{\"shift\":%d,\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s,\"volume\":%d}",
         i,
         JsonNumber(iOpen(symbol, timeframe, i), digits),
         JsonNumber(iHigh(symbol, timeframe, i), digits),
         JsonNumber(iLow(symbol, timeframe, i), digits),
         JsonNumber(iClose(symbol, timeframe, i), digits),
         (int)iVolume(symbol, timeframe, i)
      );
   }
   candles += "]";
   return candles;
}

int OnInit()
{
   EventSetTimer(30);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   if(!EnableSender) return;

   string symbol = _Symbol;
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   int spread = (int)SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   double open = iOpen(symbol, PERIOD_M1, 0);
   double high = iHigh(symbol, PERIOD_M1, 0);
   double low = iLow(symbol, PERIOD_M1, 0);
   double close = iClose(symbol, PERIOD_M1, 0);
   long volume = iVolume(symbol, PERIOD_M1, 0);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   string recentCandles = BuildRecentCandlesJson(symbol, PERIOD_M1, 5, digits);

   string body = StringFormat(
      "{\"timestamp_utc\":\"%s\",\"snapshots\":[{\"symbol\":\"%s\",\"timeframe\":\"M1\",\"bid\":%s,\"ask\":%s,\"spread_points\":%d,\"ohlc\":{\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s},\"volume\":%d,\"recent_candles\":%s,\"terminal\":{\"platform\":\"mt5\",\"symbol_raw\":\"%s\"}}]}",
      IsoTimeUTC(), symbol,
      JsonNumber(bid, digits), JsonNumber(ask, digits), spread,
      JsonNumber(open, digits), JsonNumber(high, digits), JsonNumber(low, digits), JsonNumber(close, digits),
      (int)volume, recentCandles, symbol
   );

   string headers = "Authorization: Bearer " + ReceiverToken + "\r\nContent-Type: application/json; charset=utf-8\r\n";
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   int code = WebRequest("POST", ReceiverUrl, headers, 5000, data, result, resultHeaders);
   if(code == -1)
      Print("Snapshot send failed: ", GetLastError());
}
