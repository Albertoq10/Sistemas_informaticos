
// ID único del dispositivo (cambiar para cada ESP32)
#define DEVICE_ID "tracker_01"

#include <WiFi.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include "env.h" // Configurar con tus datos en env.h

// Pines de sensores LDR
const int ldrTL = 33;
const int ldrTR = 35;
const int ldrBL = 32;
const int ldrBR = 34;

// Pines de los servos
const int pinServoH = 26;  // Horizontal (Azimut)
const int pinServoV = 25;  // Vertical (Elevación)

// Medición de voltaje de celda solar
const int solarPin = 39; // GPIO39 (VN), ADC1_CH3

// Divisor de tensión: celdas solares (máx ~5V) -> ADC (máx ~3.6V)
// Esquema: R1=100kΩ (superior) / R2=47kΩ (inferior) + capacitor 104µF
// Voltaje máximo en ADC: 5V × (47/(100+47)) ≈ 1.6V
const float SOLAR_DIV_R1 = 100000.0;  // ohmios, entre +solar y nodo de medición
const float SOLAR_DIV_R2 = 47000.0;   // ohmios, entre nodo de medición y GND
const float ADC_REF_V = 3.6;          // voltios, rango con atenuación 11dB

int posH = 120, posV = 150;  // Posiciones iniciales

int limiteMinH = 40, limiteMaxH = 180;
int limiteMinV = 130, limiteMaxV = 175;

Servo servoH, servoV;
int lastPosH = 0, lastPosV = 0;

// Control de envío HTTP
unsigned long lastHttpSend = 0;
const unsigned long HTTP_SEND_INTERVAL = 5000;  // Enviar cada 5 segundos
unsigned long httpInterval = HTTP_SEND_INTERVAL; // Intervalo actual
unsigned long fastModeUntil = 0; // Timestamp hasta el que usamos intervalo rápido
int MIN_CHANGE_TO_SEND = 5; // Mínimo cambio en posición para forzar envío

// Control de impresión serial
const unsigned long SERIAL_PRINT_INTERVAL = 1000;  // ms entre impresiones si no cambia
const int SERIAL_MIN_DELTA = 20;  // Cambio mínimo en lectura para forzar impresión
unsigned long lastSerialPrint = 0;
int lastPrintTl = 0, lastPrintTr = 0, lastPrintBl = 0, lastPrintBr = 0;
bool hasPrintedSensors = false;

WiFiClient wifi;

// Umbral de cambio mínimo para imprimir voltaje
const float SERIAL_MIN_DELTA_V = 0.05f; // 50 mV
float lastPanelVoltage = -1.0f;

void printStatusOnChange(int tl, int tr, int bl, int br, int posH, int posV, float panelVoltage) {
  bool sensorChanged = (abs(tl - lastPrintTl) > SERIAL_MIN_DELTA) ||
                       (abs(tr - lastPrintTr) > SERIAL_MIN_DELTA) ||
                       (abs(bl - lastPrintBl) > SERIAL_MIN_DELTA) ||
                       (abs(br - lastPrintBr) > SERIAL_MIN_DELTA);
  bool timeElapsed = (millis() - lastSerialPrint) >= SERIAL_PRINT_INTERVAL;
  bool pvChanged = (lastPanelVoltage < 0.0f) || (panelVoltage > lastPanelVoltage + SERIAL_MIN_DELTA_V) || (panelVoltage < lastPanelVoltage - SERIAL_MIN_DELTA_V);
  bool shouldPrint = !hasPrintedSensors || sensorChanged || pvChanged || timeElapsed;

  if (shouldPrint) {
    Serial.print("[" DEVICE_ID "] LDR -> TL:");
    Serial.print(tl);
    Serial.print(" TR:");
    Serial.print(tr);
    Serial.print(" BL:");
    Serial.print(bl);
    Serial.print(" BR:");
    Serial.print(br);
    Serial.print(" | SERVO -> H:");
    Serial.print(posH);
    Serial.print(" V:");
    Serial.print(posV);
    Serial.print(" | PV:");
    Serial.print(panelVoltage, 3);
    Serial.println("V");

    lastSerialPrint = millis();
    lastPrintTl = tl;
    lastPrintTr = tr;
    lastPrintBl = bl;
    lastPrintBr = br;
    lastPanelVoltage = panelVoltage;
    hasPrintedSensors = true;
  }
}


void setup() {
  Serial.begin(230400);

  // Configuración de Servos
  servoH.attach(pinServoH, 500, 2500);
  servoV.attach(pinServoV, 500, 2500);
  servoH.write(posH);
  servoV.write(posV);
  delay(1000);

  // Configuracion de atenuación de hasta ~3.6V en ADC para medición de panel solar
  // ADC_11db: rango ~0-3.6V
  analogSetPinAttenuation(solarPin, ADC_11db);

  // Conectar a WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.println("Connecting to WiFi..");
  }
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  
  // Volver a intervalo normal si terminó modo rápido
  if (fastModeUntil != 0 && millis() > fastModeUntil) {
    httpInterval = HTTP_SEND_INTERVAL;
    fastModeUntil = 0;
  }
  
  // 1. Leer valores de luz de los 4 LDRs
  int tl = analogRead(ldrTL);
  int tr = analogRead(ldrTR);
  int bl = analogRead(ldrBL);
  int br = analogRead(ldrBR);

  // Lectura de voltaje del panel con divisor
  int solarRaw = analogRead(solarPin);
  float v_adc = (float)solarRaw / 4095.0 * ADC_REF_V;
  float panelVoltage = v_adc * ((SOLAR_DIV_R1 + SOLAR_DIV_R2) / SOLAR_DIV_R2);

  printStatusOnChange(tl, tr, bl, br, posH, posV, panelVoltage);

  // 2. Enviar datos al servidor y recibir comandos
  if (WiFi.status() == WL_CONNECTED) {
    unsigned long now = millis();
    bool tiempoTranscurrido = (now - lastHttpSend) >= httpInterval;
    bool posicionCambio = (abs(posH - lastPosH) > MIN_CHANGE_TO_SEND) || (abs(posV - lastPosV) > MIN_CHANGE_TO_SEND);

    if (tiempoTranscurrido || posicionCambio) {
      StaticJsonDocument<256> doc;
      doc["device_id"] = DEVICE_ID;
      doc["ldr_tl"] = tl;
      doc["ldr_tr"] = tr;
      doc["ldr_bl"] = bl;
      doc["ldr_br"] = br;
      doc["servo_h"] = posH;
      doc["servo_v"] = posV;
      
      bool limitH = (posH == limiteMinH || posH == limiteMaxH);
      bool limitV = (posV == limiteMinV || posV == limiteMaxV);
      doc["at_limit_h"] = limitH;
      doc["at_limit_v"] = limitV;
      doc["panel_voltage"] = panelVoltage;

      String json_string;
      serializeJson(doc, json_string);
      Serial.print("[" DEVICE_ID "] Enviando: ");
      Serial.println(json_string);

      HTTPClient http;
      String url = String(SERVER_BASE_URL) + "/sensor_values";
      http.begin(wifi, url);
      http.setConnectTimeout(5000);
      http.addHeader("Content-Type", "application/json");

      int httpResponseCode = http.POST(json_string);
      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.print("[" DEVICE_ID "] HTTP ");
        Serial.print(httpResponseCode);
        Serial.print(": ");
        Serial.println(response);

        // 3. Procesar respuesta del servidor con nuevos ángulos
        if (httpResponseCode == 200) {
          StaticJsonDocument<256> responseDoc;
          DeserializationError error = deserializeJson(responseDoc, response);
          
          if (!error && responseDoc.containsKey("command")) {
            JsonObject cmd = responseDoc["command"];
            
            if (cmd.containsKey("servo_h") && cmd.containsKey("servo_v")) {
              int newH = cmd["servo_h"];
              int newV = cmd["servo_v"];
              
              // 4. Validar límites
              bool validH = (newH >= limiteMinH && newH <= limiteMaxH);
              bool validV = (newV >= limiteMinV && newV <= limiteMaxV);
              
              if (validH && validV) {
                posH = newH;
                posV = newV;
                servoH.write(posH);
                servoV.write(posV);
                Serial.print("[" DEVICE_ID "] Movido a H:");
                Serial.print(posH);
                Serial.print(" V:");
                Serial.println(posV);
              } else {
                Serial.println("[" DEVICE_ID "] Ángulos fuera de límites");
              }
            }
          }

          // Activar modo rápido temporal si el servidor lo indica
          if (!error && responseDoc.containsKey("fast")) {
            JsonObject fast = responseDoc["fast"];
            if (fast.containsKey("fast_interval_ms") && fast.containsKey("fast_duration_ms")) {
              unsigned long fi = fast["fast_interval_ms"];
              unsigned long fd = fast["fast_duration_ms"];
              if (fi >= 200 && fi <= 2000 && fd <= 10000) {
                httpInterval = fi;
                fastModeUntil = millis() + fd;
              }
            }
          }
        }
      } else {
        Serial.print("[" DEVICE_ID "] HTTP Error: ");
        Serial.println(http.errorToString(httpResponseCode));
      }
      http.end();

      lastHttpSend = now;
      lastPosH = posH;
      lastPosV = posV;
    }
  } else {
    Serial.println("[" DEVICE_ID "] Error: WiFi desconectado");
  }

  delay(50);
}
