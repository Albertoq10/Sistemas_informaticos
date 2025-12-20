/* 
  Avance proyecto, base para poder hacer lo demas
*/

// Habilitar/deshabilitar modo calibración
#define CALIBRATION_MODE false

#include <WiFi.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include "env.h" // Configurar con tus datos en env.h

// Sensores LDR (ADC1)
const int ldrTL = 33; // Top Left (Arriba Izquierda)
const int ldrTR = 35; // Top Right (Arriba Derecha)
const int ldrBL = 32; // Bottom Left (Abajo Izquierda)
const int ldrBR = 34; // Bottom Right (Abajo Derecha)

// Pines de los Servos
const int pinServoH = 26; // Servo Horizontal (Azimut)
const int pinServoV = 25; // Servo Vertical (Elevación)

// Configuración inicial de ángulos
int posH = 120;
int posV = 150;
int tolerancia = 20; // Compensa variación entre LDR
int limiteMinH = 40, limiteMaxH = 180;  // Límites horizontal
int limiteMinV = 130, limiteMaxV = 175;  // Límites vertical

// Controlador PID
float Kp = 0.01;  // Ganancia proporcional (reducida para movimiento más lento)
float Kd = 0.05;  // Ganancia derivativa (suaviza cambios bruscos)
int maxCambio = 2;  // Cambio máximo de grados por ciclo
float errorPrevH = 0;
float errorPrevV = 0;
Servo servoH;

// Control de envío HTTP
unsigned long lastHttpSend = 0;
const unsigned long HTTP_SEND_INTERVAL = 5000;  // Enviar cada 5 segundos
int MIN_CHANGE_TO_SEND = 5; // Mínimo cambio en posición para forzar envío
int lastPosH = 0;
int lastPosV = 0;
Servo servoV;

WiFiClient wifi;

#include "calibracion.h" // Lógica de calibración (solo si CALIBRATION_MODE es true)


void setup() {
  Serial.begin(230400);

  // Configuración de Servos
  servoH.attach(pinServoH, 500, 2500);
  servoV.attach(pinServoV, 500, 2500);

  servoH.write(posH);
  servoV.write(posV);
  delay(1000);

  // Conectar WiFi solo si no estamos en modo calibración
#if !CALIBRATION_MODE
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.println("Connecting to WiFi..");
  }
  Serial.println("Connected to the WiFi network");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
#endif

#if CALIBRATION_MODE
  enterCalibrationMode();
#endif
}

void loop() {
#if CALIBRATION_MODE
  // Escuchar comandos de calibración por serial
  handleSerialCommands();
#endif
  
  // 1. Leer valores de luz de los 4 LDRs
  int tl = analogRead(ldrTL);
  int tr = analogRead(ldrTR);
  int bl = analogRead(ldrBL);
  int br = analogRead(ldrBR);

  // Mostrar lectura de LDRs en consola
  Serial.print("LDR -> TL:");
  Serial.print(tl);
  Serial.print(" TR:");
  Serial.print(tr);
  Serial.print(" BL:");
  Serial.print(bl);
  Serial.print(" BR:");
  Serial.println(br);

  // 2. Calcular promedios para cada eje
  int promedioArriba = (tl + tr) / 2;
  int promedioAbajo = (bl + br) / 2;
  int promedioIzquierda = (tl + bl) / 2;
  int promedioDerecha = (tr + br) / 2;

  // Calcular diferencias
  int diffV = promedioArriba - promedioAbajo;
  int diffH = promedioIzquierda - promedioDerecha;

  // Decidir qué eje mover (solo uno a la vez)
  bool moverV = false;
  bool moverH = false;
  
  if (abs(diffV) > tolerancia || abs(diffH) > tolerancia) {
    // Mover solo el eje con mayor error
    if (abs(diffV) > abs(diffH)) {
      moverV = true;
    } else {
      moverH = true;
    }
  }

  // 3. Lógica Eje Vertical (Elevación) con PID
  const char* movV = "-";
  if (moverV) {
    // PID: error = diferencia, derivada = cambio del error
    float errorV = diffV; 
    float derivV = errorV - errorPrevV;
    float correccionV = (Kp * errorV) + (Kd * derivV);
    
    // Limitar cambio máximo por ciclo
    correccionV = constrain(correccionV, -maxCambio, maxCambio);
    
    int posVAnterior = posV;
    posV -= (int)correccionV;  // Invertido
    posV = constrain(posV, limiteMinV, limiteMaxV);
    errorPrevV = errorV;
    
    // Verificar si hubo movimiento real (no en límite)
    if (posV != posVAnterior) {
      if (correccionV > 0) movV = "^";
      else if (correccionV < 0) movV = "v";
    } else {
      // En el límite
      if (posV == limiteMinV) Serial.println("[LÍMITE MIN] Eje V (" + String(limiteMinV) + "°)");
      if (posV == limiteMaxV) Serial.println("[LÍMITE MAX] Eje V (" + String(limiteMaxV) + "°)");
    }
  }

  // 4. Lógica Eje Horizontal (Azimut) con PID
  const char* movH = "-";
  if (moverH) {
    // PID: error = diferencia, derivada = cambio del error
    float errorH = diffH;
    float derivH = errorH - errorPrevH;
    float correccionH = (Kp * errorH) + (Kd * derivH);
    
    // Limitar cambio máximo por ciclo
    correccionH = constrain(correccionH, -maxCambio, maxCambio);
    
    int posHAnterior = posH;
    posH += (int)correccionH;
    posH = constrain(posH, limiteMinH, limiteMaxH);
    errorPrevH = errorH;
    
    // Verificar si hubo movimiento
    if (posH != posHAnterior) {
      if (correccionH > 0) movH = ">";
      else if (correccionH < 0) movH = "<";
    } else {
      // En el límite
      if (posH == limiteMinH) Serial.println("[LÍMITE MIN] Eje H (" + String(limiteMinH) + "°)");
      if (posH == limiteMaxH) Serial.println("[LÍMITE MAX] Eje H (" + String(limiteMaxH) + "°)");
    }
  }

  // 6. Aplicar movimiento
  servoV.write(posV);
  servoH.write(posH);

  // Mostrar posición de servos y decisión de movimiento en consola
  Serial.print("SERVO -> H:");
  Serial.print(posH);
  Serial.print(" V:");
  Serial.print(posV);
  Serial.print("  MOV -> H:");
  Serial.print(movH);
  Serial.print(" V:");
  Serial.println(movV);

  // Enviar posiciones de servos y LDR por HTTP
  if (WiFi.status() == WL_CONNECTED) {
    // Enviar solo cada 5 segundos O si la posición cambió significativamente
    unsigned long now = millis();
    bool tiempoTranscurrido = (now - lastHttpSend) >= HTTP_SEND_INTERVAL;
    bool posicionCambio = (abs(posH - lastPosH) > MIN_CHANGE_TO_SEND) || (abs(posV - lastPosV) > MIN_CHANGE_TO_SEND);

    if (tiempoTranscurrido || posicionCambio) {
      StaticJsonDocument<256> doc;
      doc["ldr_tl"] = tl;
      doc["ldr_tr"] = tr;
      doc["ldr_bl"] = bl;
      doc["ldr_br"] = br;
      doc["servo_h"] = posH;
      doc["servo_v"] = posV;

      String json_string;
      serializeJson(doc, json_string);
      Serial.print("JSON -> ");
      Serial.println(json_string);

      HTTPClient http;
      String url = String(SERVER_BASE_URL) + "/sensor_values";
      Serial.print("POST URL: ");
      Serial.println(url);
      http.begin(wifi, url);
      http.setConnectTimeout(5000);
      http.addHeader("Content-Type", "application/json");

      int httpResponseCode = http.POST(json_string);
      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.print("HTTP ");
        Serial.println(httpResponseCode);
        Serial.println(response);
      } else {
        Serial.print("Error on sending POST Request: ");
        Serial.print(httpResponseCode);
        Serial.print(" ");
        Serial.println(http.errorToString(httpResponseCode));
        Serial.print("WiFi IP: ");
        Serial.println(WiFi.localIP());
        Serial.print("WiFi RSSI: ");
        Serial.println(WiFi.RSSI());
      }
      http.end();

      // Actualizar timer y posición
      lastHttpSend = now;
      lastPosH = posH;
      lastPosV = posV;
    }
  } else {
    Serial.println("Error in WiFi connection");
  }

  // Pequeña pausa para suavizar el movimiento
  delay(50);
}
