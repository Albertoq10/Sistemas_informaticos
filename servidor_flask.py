#LANZA servidor y manda datos a influx

from flask import Flask, request, jsonify
import requests
import time
import math
import os
from river import linear_model, preprocessing, anomaly, drift, optim
import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Permitir activar debug vía variable de entorno
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")

app = Flask("servidor_flask")

def _load_env_file(path: str = ".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass

_load_env_file()

INFLUX_URL_BASE = os.environ.get('INFLUX_URL_BASE', '127.0.0.1')  # local
INFLUX_TOKEN    = os.environ.get('INFLUX_TOKEN', 'NtZ58sLCY9fxPHq5yzC5qOr8iXVGHq81XWZs5wqu4JrN8EFgPLpFb7h96IrxCoJSSrJH85SilSxO0rrgH9VAIA==')
INFLUX_ORG      = os.environ.get('INFLUX_ORG', 'UC3M')
INFLUX_BUCKET   = os.environ.get('INFLUX_BUCKET', 'Pot_pruebas')  # recuerda cambiar


WRITE_URL = 'http://{}:8086/api/v2/write?org={}&bucket={}&precision=ms'.format(INFLUX_URL_BASE,INFLUX_ORG,INFLUX_BUCKET)#lanzar influx db simepre
HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "text/plain; charset=utf-8"
}

# ==================== MODELOS RIVER ====================

# 1. PREDICCIÓN DE EFICIENCIA
# Modelo de regresión adaptativa que predice el voltaje esperado según la luz recibida
# Características: promedio de LDRs, hora del día, posiciones de servos
efficiency_model = preprocessing.StandardScaler() | linear_model.LinearRegression(
    optimizer=optim.SGD(0.01),
    l2=0.001
)

# 2. DETECCIÓN DE ANOMALÍAS
# Detecta lecturas fuera de lo normal (sensores dañados, sombras, bloqueos mecánicos)
# HalfSpaceTrees es eficiente para streaming y detecta outliers en tiempo real
anomaly_detector = anomaly.HalfSpaceTrees(
    n_trees=10,
    height=8,
    window_size=250,
    seed=42
)

# 3. DETECCIÓN DE CONCEPT DRIFT
# Monitorea cambios en la distribución de datos (cambios estacionales/climáticos)
# ADWIN detecta cuándo el modelo debe "reaprender" el entorno
drift_detector = drift.ADWIN(delta=0.002)

# Métricas y contadores
model_predictions_count = 0
anomalies_detected = 0
drift_detected_count = 0

# ==================== FUNCIONES DE ANÁLISIS ====================

def calcular_caracteristicas(ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v):
    """
    Calcula características derivadas de las lecturas de sensores.
    
    Returns:
        tuple: (features_dict, avg_light, light_variance)
    """
    avg_light = (ldr_tl + ldr_tr + ldr_bl + ldr_br) / 4.0
    max_light = max(ldr_tl, ldr_tr, ldr_bl, ldr_br)
    min_light = min(ldr_tl, ldr_tr, ldr_bl, ldr_br)
    light_variance = ((ldr_tl - avg_light)**2 + (ldr_tr - avg_light)**2 + 
                    (ldr_bl - avg_light)**2 + (ldr_br - avg_light)**2) / 4.0
    
    features = {
        'avg_light': avg_light,
        'max_light': max_light,
        'min_light': min_light,
        'light_variance': light_variance,
        'servo_h': servo_h,
        'servo_v': servo_v,
        'hour': time.localtime().tm_hour,
        'minute': time.localtime().tm_min
    }
    
    return features, avg_light, light_variance


def analizar_eficiencia(features, avg_light):
    """
    Predice el voltaje esperado y detecta baja eficiencia del panel solar.
    
    Args:
        features: Diccionario con características del sistema
        avg_light: Promedio de luz de los 4 LDRs
    
    Returns:
        dict: Información sobre el análisis de eficiencia
    """
    global model_predictions_count, efficiency_model
    
    # Simular voltaje (en producción, usar voltaje real del panel)
    simulated_voltage = avg_light / 4095.0 * 5.0  # Normalizar a 0-5V
    
    resultado = {
        'voltage_real': simulated_voltage,
        'voltage_predicted': None,
        'error': None,
        'status': 'TRAINING'
    }
    
    # Predecir solo después de entrenar con suficientes muestras
    if model_predictions_count > 10:
        voltage_predicted = efficiency_model.predict_one(features)
        voltage_error = abs(simulated_voltage - voltage_predicted)
        
        # Umbral de error aceptable
        efficiency_threshold = 0.5
        efficiency_status = "OK" if voltage_error < efficiency_threshold else "LOW_EFFICIENCY"
        
        resultado.update({
            'voltage_predicted': voltage_predicted,
            'error': voltage_error,
            'status': efficiency_status
        })
        
        print(f"  [EFICIENCIA] Voltaje esperado: {voltage_predicted:.3f}V, Real: {simulated_voltage:.3f}V, Error: {voltage_error:.3f}V - {efficiency_status}")
    
    # Entrenar el modelo con los datos actuales
    efficiency_model.learn_one(features, simulated_voltage)
    model_predictions_count += 1
    
    return resultado


def detectar_anomalias(avg_light, light_variance, servo_h, servo_v):
    """
    Detecta comportamientos anómalos en el sistema (sensores dañados, sombras, bloqueos).
    
    Returns:
        dict: Información sobre la detección de anomalías
    """
    global anomalies_detected, anomaly_detector
    
    anomaly_features = {
        'avg_light': avg_light,
        'light_variance': light_variance,
        'servo_h': float(servo_h),
        'servo_v': float(servo_v)
    }
    
    # Calcular score de anomalía (mayor = más anómalo)
    anomaly_score = anomaly_detector.score_one(anomaly_features)
    anomaly_detector.learn_one(anomaly_features)
    
    # Umbral para considerar una anomalía
    anomaly_threshold = 0.7
    is_anomaly = anomaly_score > anomaly_threshold
    
    if is_anomaly:
        anomalies_detected += 1
        print(f"  [ANOMALÍA] Score: {anomaly_score:.3f} - Posible sensor dañado, sombra o bloqueo mecánico")
    else:
        print(f"  [NORMAL] Score de anomalía: {anomaly_score:.3f}")
    
    return {
        'score': anomaly_score,
        'is_anomaly': is_anomaly,
        'threshold': anomaly_threshold
    }


def detectar_concept_drift(light_variance):
    """
    Detecta cambios drásticos en los patrones del sistema (cambios estacionales/climáticos).
    
    Returns:
        dict: Información sobre la detección de concept drift
    """
    global drift_detected_count, drift_detector
    
    drift_detector.update(light_variance)
    
    resultado = {
        'drift_detected': drift_detector.drift_detected,
        'drift_count': drift_detected_count
    }
    
    if drift_detector.drift_detected:
        drift_detected_count += 1
        resultado['drift_count'] = drift_detected_count
        print(f"  [DRIFT DETECTADO] Cambio #{drift_detected_count} - El patrón de luz ha cambiado drásticamente")
        print(f"  [DRIFT] Considerar reentrenar modelos o ajustar umbrales")
        
        # Aquí podrías reiniciar modelos o ajustar parámetros
        # Por ejemplo: efficiency_model = preprocessing.StandardScaler() | linear_model.LinearRegression()
    
    return resultado


def ejecutar_analisis_river(ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v):
    """
    Ejecuta todos los análisis de Machine Learning con River.
    
    Returns:
        dict: Resultados de todos los análisis
    """
    # 1. Calcular características
    features, avg_light, light_variance = calcular_caracteristicas(
        ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v
    )
    
    # 2. Análisis de eficiencia
    eficiencia = analizar_eficiencia(features, avg_light)
    
    # 3. Detección de anomalías
    anomalias = detectar_anomalias(avg_light, light_variance, servo_h, servo_v)
    
    # 4. Detección de concept drift
    drift = detectar_concept_drift(light_variance)
    
    # Mostrar estadísticas generales
    print(f"  [STATS] Predicciones: {model_predictions_count}, Anomalías: {anomalies_detected}, Drifts: {drift_detected_count}")
    
    return {
        'eficiencia': eficiencia,
        'anomalias': anomalias,
        'drift': drift
    }

# ==================== RUTAS ====================

@app.route("/sensor_values", methods=["POST"])
def sensor_values():
    data = request.get_json(force=True, silent=True) or {}
    
    if any(k in data for k in ("servo_h", "servo_v", "ldr_tl", "ldr_tr", "ldr_bl", "ldr_br")):
        try:
            servo_h = int(data.get("servo_h", 0))
            servo_v = int(data.get("servo_v", 0))
            ldr_tl  = int(data.get("ldr_tl", 0))
            ldr_tr  = int(data.get("ldr_tr", 0))
            ldr_bl  = int(data.get("ldr_bl", 0))
            ldr_br  = int(data.get("ldr_br", 0))

            print(f"SolarTracker -> servo_h={servo_h}, servo_v={servo_v}, TL={ldr_tl}, TR={ldr_tr}, BL={ldr_bl}, BR={ldr_br}")

            # Ejecutar análisis con River
            analisis_resultados = ejecutar_analisis_river(ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v)

            ts_ms = int(time.time() * 1000)
            
            # Preparar datos para InfluxDB (incluyendo análisis ML)
            fields = [
                f"servo_h={servo_h}", f"servo_v={servo_v}",
                f"ldr_tl={ldr_tl}", f"ldr_tr={ldr_tr}",
                f"ldr_bl={ldr_bl}", f"ldr_br={ldr_br}"
            ]
            
            # Agregar resultados del análisis con River
            efic = analisis_resultados['eficiencia']
            anom = analisis_resultados['anomalias']
            drift = analisis_resultados['drift']
            
            if efic['voltage_predicted'] is not None:
                fields.append(f"voltage_predicted={efic['voltage_predicted']:.4f}")
                fields.append(f"voltage_error={efic['error']:.4f}")
                fields.append(f"efficiency_ok={'1' if efic['status'] == 'OK' else '0'}")
            
            fields.append(f"anomaly_score={anom['score']:.4f}")
            fields.append(f"is_anomaly={'1' if anom['is_anomaly'] else '0'}")
            fields.append(f"drift_detected={'1' if drift['drift_detected'] else '0'}")
            
            fieldset = ",".join(fields)
            line = f"tracker,device=esp32 {fieldset} {ts_ms}"

            r = requests.post(WRITE_URL, data=line, headers=HEADERS, timeout=5)
            ok = (204 == r.status_code)

            if not ok:
                # Log detallado para diagnosticar fallos de InfluxDB
                print(f"[INFLUX ERROR] status={r.status_code} body={r.text}")
                print(f"[INFLUX ERROR] url={WRITE_URL}")
            
            # Incluir resultados del análisis en la respuesta
            return jsonify({
                "status": "ok" if ok else "error",
                "influx_status_code": r.status_code,
                "received": data,
                "analysis": {
                    "efficiency": {
                        "status": efic['status'],
                        "voltage_real": efic['voltage_real'],
                        "voltage_predicted": efic['voltage_predicted'],
                        "error": efic['error']
                    },
                    "anomaly": {
                        "detected": anom['is_anomaly'],
                        "score": anom['score']
                    },
                    "drift": {
                        "detected": drift['drift_detected'],
                        "count": drift['drift_count']
                    }
                }
            }), (200 if ok else 500)
        except Exception as e:
            # Log completo de la excepción para depurar el 500
            print("[EXCEPTION] sensor_values:", repr(e))
            import traceback
            traceback.print_exc()
            return jsonify({"status": "error", "msg": str(e)}), 500

    
    # Caso: potenciómetro + voltaje
    pot_value = int(data.get("pot_value", 0))
    voltage   = float(data.get("voltage", float("nan")))

    print(f"Recibido -> pot_value={pot_value}, voltage={voltage:.3f} V")

    ts_ms = int(time.time() * 1000)
    fields = [f"value={pot_value}"]
    if not math.isnan(voltage):
        fields.append(f"voltage={voltage}")
    fieldset = ",".join(fields)
    line = f"potentiometer,device=esp32 {fieldset} {ts_ms}"

    try:
        r = requests.post(WRITE_URL, data=line, headers=HEADERS, timeout=5)
        ok = (204 == r.status_code)
        return jsonify({
            "status": "ok" if ok else "error",
            "influx_status_code": r.status_code,
            "received": data
        }), (200 if ok else 500)
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000, debug=DEBUG_MODE, use_reloader=False) #permite que se pueda abrir port, de esta manera se quita el erorr de python
