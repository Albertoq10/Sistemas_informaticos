# Flask Project - Solar Tracker

## Descripción
Sistema de seguimiento solar con ESP32 que utiliza 4 sensores LDR para orientar dos servomotores (horizontal y vertical) hacia la fuente de luz más intensa. Los datos se envían a un servidor Flask que los almacena en InfluxDB.

## Pines Utilizados

| GPIO | Componente | Función |
|------|------------|---------|
| 33 | LDR Top Left | Sensor de luz superior izquierdo (ADC1) |
| 35 | LDR Top Right | Sensor de luz superior derecho (ADC1) |
| 32 | LDR Bottom Left | Sensor de luz inferior izquierdo (ADC1) |
| 34 | LDR Bottom Right | Sensor de luz inferior derecho (ADC1) |
| 26 | Servo Horizontal | Control de azimut (0-180°) |
| 25 | Servo Vertical | Control de elevación (0-180°) |

## Componentes

- **ESP32**: Microcontrolador con WiFi
- **4x LDR**: Fotoresistencias para detección de luz
- **2x Servomotores**: Control de posición horizontal y vertical
- **Flask**: Framework web para servidor HTTP
- **InfluxDB**: Base de datos de series temporales
- **River**: Librería de machine learning

## Endpoint API

### POST /sensor_values
Recibe datos del ESP32 y los almacena en InfluxDB.

**URL:** `http://<server_ip>:6000/sensor_values`

**Content-Type:** `application/json`

**Datos enviados por el Solar Tracker:**
```json
{
  "ldr_tl": 1234,
  "ldr_tr": 1230,
  "ldr_bl": 1220,
  "ldr_br": 1225,
  "servo_h": 120,
  "servo_v": 150
}
```

**Campos:**
- `ldr_tl`: Lectura ADC del sensor superior izquierdo (0-4095)
- `ldr_tr`: Lectura ADC del sensor superior derecho (0-4095)
- `ldr_bl`: Lectura ADC del sensor inferior izquierdo (0-4095)
- `ldr_br`: Lectura ADC del sensor inferior derecho (0-4095)
- `servo_h`: Posición del servo horizontal en grados (40-180°)
- `servo_v`: Posición del servo vertical en grados (130-175°)

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

## Instalación

```bash
pip install -r requirements.txt
```

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

