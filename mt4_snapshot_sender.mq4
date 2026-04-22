#property strict

extern string ReceiverUrl = "http://127.0.0.1:8010/market/snapshot";
extern string ReceiverToken = "change-me-token";
extern bool EnableSender = true;

string IsoTimeUTC()
{
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
      dt.year, dt.mon, dt.day,
      dt.hour, dt.min, dt.sec);
}

string CharArrayToStringSafe(uchar &arr[])
{
   if(ArraySize(arr) <= 0)
      return "";
   return CharArrayToString(arr, 0, -1, CP_UTF8);
}

string JsonNumber(double value, int digits)
{
   return DoubleToString(value, digits);
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
   SendSnapshot();
}

string BuildRecentCandlesJson(string symbol, int timeframe, int bars, int digits)
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
         iVolume(symbol, timeframe, i)
      );
   }
   candles += "]";
   return candles;
}

void SendSnapshot()
{
   string symbol = Symbol();
   double bid = Bid;
   double ask = Ask;
   int spread = (int)MarketInfo(symbol, MODE_SPREAD);
   double open = iOpen(symbol, PERIOD_M1, 0);
   double high = iHigh(symbol, PERIOD_M1, 0);
   double low = iLow(symbol, PERIOD_M1, 0);
   double close = iClose(symbol, PERIOD_M1, 0);
   long volume = iVolume(symbol, PERIOD_M1, 0);

   int digits = (int)MarketInfo(symbol, MODE_DIGITS);
   string recentCandles = BuildRecentCandlesJson(symbol, PERIOD_M1, 5, digits);
   string body = StringFormat(
      "{\"timestamp_utc\":\"%s\",\"snapshots\":[{\"symbol\":\"%s\",\"timeframe\":\"M1\",\"bid\":%s,\"ask\":%s,\"spread_points\":%d,\"ohlc\":{\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s},\"volume\":%d,\"recent_candles\":%s}]}",
      IsoTimeUTC(), symbol,
      JsonNumber(bid, digits), JsonNumber(ask, digits), spread,
      JsonNumber(open, digits), JsonNumber(high, digits), JsonNumber(low, digits), JsonNumber(close, digits),
      volume, recentCandles
   );

   Print("Snapshot request body: ", body);

   string headers = "Authorization: Bearer " + ReceiverToken + "\r\nContent-Type: application/json; charset=utf-8\r\n";
   uchar data[];
   uchar result[];
   string resultHeaders;
   int dataLen = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(dataLen > 0 && data[dataLen - 1] == 0)
      ArrayResize(data, dataLen - 1);
   int code = WebRequest("POST", ReceiverUrl, headers, 5000, data, result, resultHeaders);
   if(code == -1)
   {
      Print("Snapshot send failed: ", GetLastError());
      return;
   }

   string responseBody = CharArrayToStringSafe(result);
   Print("Snapshot sent, HTTP code: ", code);
   if(StringLen(responseBody) > 0)
      Print("Snapshot response body: ", responseBody);
   if(StringLen(resultHeaders) > 0)
      Print("Snapshot response headers: ", resultHeaders);
}
