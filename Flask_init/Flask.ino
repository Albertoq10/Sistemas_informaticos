/* 
  Avance proyecto, base para poder hacer lo demas
*/

#include <WiFi.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>

const char* ssid     = "iPhoneBETO"; //recuerda cambiar wifi, MN2 es de casa. Revisa en serial monitor que se conecte
const char* password = "12345678";

// Usa un pin de ADC1 para poder leer con WiFi activo
const int POT_PIN = 32;  

WiFiClient wifi;

void setup() {
  Serial.begin(230400);

  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.println("Connecting to WiFi..");
  }
  Serial.println("Connected to the WiFi network");
  Serial.println("WiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    int raw = analogRead(POT_PIN);//potenciometro
    float voltage = (raw / 4095.0f) * 3.3f;

    //para mandar formato JSON
    StaticJsonDocument<128> doc;
    doc["pot_value"] = raw;
    doc["voltage"]   = voltage;

    String json_string;
    serializeJson(doc, json_string);
    Serial.print("JSON -> ");
    Serial.println(json_string);


    HTTPClient http;
    http.begin("http://172.20.10.3:6000/sensor_values");  // cambia a la IP/puerto de tu PC IP DE PC!!!, a la esp32 se le asigna otra ip
    http.addHeader("Content-Type", "application/json");

    int httpResponseCode = http.POST(json_string);
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("HTTP ");
      Serial.println(httpResponseCode);
      Serial.println(response);
    } else {
      Serial.print("Error on sending POST Request: ");
      Serial.println(httpResponseCode);
    }
    http.end();

  } else {
    Serial.println("Error in WiFi connection");
  }

  delay(1000);
}
