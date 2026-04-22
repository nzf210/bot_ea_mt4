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

string CharArrayToStringSafe(char &arr[])
{
   if(ArraySize(arr) <= 0)
      return "";
   return CharArrayToString(arr, 0, -1);
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

   string body = StringFormat(
      "{\"timestamp_utc\":\"%s\",\"snapshots\":[{\"symbol\":\"%s\",\"timeframe\":\"M1\",\"bid\":%G,\"ask\":%G,\"spread_points\":%d,\"ohlc\":{\"open\":%G,\"high\":%G,\"low\":%G,\"close\":%G},\"volume\":%G}]}",
      IsoTimeUTC(), symbol, bid, ask, spread, open, high, low, close, volume
   );

   string headers = "Authorization: Bearer " + ReceiverToken + "\r\nContent-Type: application/json\r\n";
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data);
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
