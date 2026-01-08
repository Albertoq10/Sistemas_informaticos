# Flask Project - Solar Tracker

> Nota: Este repositorio forma parte de una tarea del curso "Máster Universitario en Internet de las Cosas: Tecnologías Aplicadas" (2025-2026), asignatura "Sistemas informáticos en IoT". Proyecto: "Seguimiento Solar Inteligente de Dos Ejes con ESP32 y Predicción de Voltaje mediante Aprendizaje Automático".

## Descripción
Sistema de seguimiento solar con ESP32 que utiliza 4 sensores LDR para orientar dos servomotores (horizontal y vertical) hacia la fuente de luz más intensa. Además, integra un sensor ambiental BME280 (I2C) para medir temperatura, humedad, presión y calcular altitud aproximada. También mide el voltaje del panel/celda solar mediante ADC. Los datos se envían a un servidor Flask que los almacena en InfluxDB.

## Pines Utilizados

| GPIO | Componente | Función |
|------|------------|---------|
| 33 | LDR Top Left | Sensor de luz superior izquierdo (ADC1) |
| 35 | LDR Top Right | Sensor de luz superior derecho (ADC1) |
| 32 | LDR Bottom Left | Sensor de luz inferior izquierdo (ADC1) |
| 34 | LDR Bottom Right | Sensor de luz inferior derecho (ADC1) |
| 26 | Servo Horizontal | Control de azimut (0-180°) |
| 25 | Servo Vertical | Control de elevación (0-180°) |
| 21 | I2C SDA (BME280) | Línea de datos I2C para BME280 |
| 22 | I2C SCL (BME280) | Línea de reloj I2C para BME280 |
| 39 | Panel Solar ADC | Medición de voltaje del panel (ADC1_CH3) |

## Componentes

- **ESP32**: Microcontrolador con WiFi
- **4x LDR**: Fotoresistencias para detección de luz
- **2x Servomotores**: Control de posición horizontal y vertical
- **Flask**: Framework web para servidor HTTP
- **InfluxDB**: Base de datos de series temporales
- **River**: Librería de machine learning
- **BME280**: Sensor ambiental (temperatura, humedad y presión; altitud estimada)

Notas BME280:
- Conexión I2C a ESP32: SDA → GPIO21, SCL → GPIO22, alimentación a 3.3V.
- Librería Arduino recomendada: SparkFun BME280.
- El código detecta si el BME está presente; si no, continúa sin medidas ambientales.

## Endpoint API

### POST /sensor_values
Recibe datos del ESP32 y los almacena en InfluxDB.

**URL:** `http://<server_ip>:6000/sensor_values`

**Content-Type:** `application/json`

**Datos enviados por el Solar Tracker (LDR, servos, panel):**
```json
{
  "ldr_tl": 1234,
  "ldr_tr": 1230,
  "ldr_bl": 1220,
  "ldr_br": 1225,
  "servo_h": 120,
  "servo_v": 150,
  "panel_voltage": 1.62,
  "device_id": "tracker_01",
  "at_limit_h": false,
  "at_limit_v": false
}
```

**Campos:**
- `ldr_tl`: Lectura ADC del sensor superior izquierdo (0-4095)
- `ldr_tr`: Lectura ADC del sensor superior derecho (0-4095)
- `ldr_bl`: Lectura ADC del sensor inferior izquierdo (0-4095)
- `ldr_br`: Lectura ADC del sensor inferior derecho (0-4095)
- `servo_h`: Posición del servo horizontal en grados (40-180°)
- `servo_v`: Posición del servo vertical en grados (130-175°)
- `panel_voltage`: Voltaje calculado del panel/celda solar en voltios
- `device_id`: Identificador del dispositivo ESP32
- `at_limit_h` / `at_limit_v`: Indicadores de si algún servo está en su límite físico

**Datos ambientales opcionales (BME280):**
```json
{
  "bme_temp_c": 24.7,
  "bme_press_hpa": 1009.3,
  "bme_hum_pct": 45.2,
  "bme_alt_m": 650.1
}
```

**Campos ambientales:**
- `bme_temp_c`: Temperatura ambiente en °C
- `bme_press_hpa`: Presión atmosférica en hPa
- `bme_hum_pct`: Humedad relativa en %
- `bme_alt_m`: Altitud estimada en metros (derivada de la presión)

**Respuesta exitosa (200):**
```json
{
  "status": "ok",
  "influx_status_code": 204,
  "received": { ... }
}
```

**Datos alternativos (Potenciómetro):**
```json
{
  "pot_value": 2048,
  "voltage": 1.65
}
```

## Ejemplo de código (ESP32 + BME280)

Fragmento relevante del envío JSON desde `Flask/Flask.ino` cuando el BME280 está presente:

```cpp
// I2C: SDA=21, SCL=22
Wire.begin(21, 22);
bool bme_ok = bme.beginI2C();

// Lecturas BME280 (si está disponible)
float bme_tempC = NAN;
float bme_hPa   = NAN;
float bme_hum   = NAN;
float bme_altm  = NAN;

if (bme_ok) {
  bme_tempC = bme.readTempC();
  bme_hPa   = bme.readFloatPressure() / 100.0f; // Pa -> hPa
  bme_hum   = bme.readFloatHumidity();
  bme_altm  = bme.readFloatAltitudeMeters();
}

StaticJsonDocument<384> doc;
doc["device_id"] = "tracker_01";
// ... LDR y servos ...
doc["panel_voltage"] = panelVoltage; // GPIO39 con divisor

if (bme_ok) {
  doc["bme_temp_c"]   = bme_tempC;
  doc["bme_press_hpa"] = bme_hPa;
  doc["bme_hum_pct"]  = bme_hum;
  doc["bme_alt_m"]    = bme_altm;
}
```

## Instalación

```bash
pip install -r requirements.txt
```

Para el firmware ESP32 (Arduino IDE):
- Instale la librería "SparkFun BME280" desde el gestor de librerías.
- Conecte el módulo BME280 a 3.3V, GND, SDA (GPIO21) y SCL (GPIO22).

## Configuración

1. Copiar `env.example.h` a `env.h` y configurar WiFi y servidor
2. Crear archivo `.env` con las credenciales de InfluxDB:
   ```
   INFLUX_URL_BASE=127.0.0.1
   INFLUX_TOKEN=tu_token_aqui
   INFLUX_ORG=UC3M
   INFLUX_BUCKET=Pot_pruebas
   ```

## Uso

### Servidor Flask
```bash
python servidor_flask.py
```
El servidor estará disponible en `http://0.0.0.0:6000`

### ESP32
1. Subir el código `Flask.ino` al ESP32
2. El sistema se conectará a WiFi y comenzará a enviar datos cada 5 segundos
3. Los servos se ajustarán automáticamente siguiendo la luz
4. Si el BME280 está conectado por I2C (GPIO21/22), se incluirán medidas de temperatura, humedad, presión y altitud en el JSON.

