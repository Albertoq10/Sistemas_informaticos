from flask import Flask, request, jsonify
import requests
import time
import math
import os
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from river_analysis import RiverAnalyzer


DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")

app = Flask("servidor_flask")

device_states = {}

class DevicePIDController:
    """Controlador PID independiente para cada dispositivo ESP32"""
    def __init__(self, device_id):
        self.device_id = device_id

        self.Kp = 0.02
        self.Kd = 0.06
        self.Ki = 0.0005
        self.maxCambio = 5
        self.tolerancia = 1

        self.errorPrevH = 0
        self.errorPrevV = 0
        self.intErrH = 0.0
        self.intErrV = 0.0
        self.int_limit = 5000

        self.limiteMinH = 40
        self.limiteMaxH = 180
        self.limiteMinV = 40
        self.limiteMaxV = 175

        self.lastPosH = 120
        self.lastPosV = 150



    def calcular_angulos(self, ldr_tl, ldr_tr, ldr_bl, ldr_br, current_h, current_v, at_limit_h=False, at_limit_v=False):
        """
        Uso de PID para determinar posicion de servos
        """
        self.lastPosH = current_h
        self.lastPosV = current_v

        promedioArriba = (ldr_tl + ldr_tr) / 2
        promedioAbajo = (ldr_bl + ldr_br) / 2
        promedioIzquierda = (ldr_tl + ldr_bl) / 2
        promedioDerecha = (ldr_tr + ldr_br) / 2

        diffV = promedioArriba - promedioAbajo
        diffH = promedioIzquierda - promedioDerecha

      #  moverV = False
       # moverH = False

        #if abs(diffV) > self.tolerancia or abs(diffH) > self.tolerancia:
         #   if abs(diffV) > abs(diffH):
          #      moverV = True
           # else:
            #    moverH = True

        #cambio
        #para que ambos ejes se puedan estar moviendo sin darle prioridad a otro
        moverV = abs(diffV) > self.tolerancia
        moverH = abs(diffH) > self.tolerancia


        nuevo_h = current_h
        nuevo_v = current_v
        debug_info = {
            'diffH': diffH,
            'diffV': diffV,
            'moverH': moverH,
            'moverV': moverV,
            'correccionH': 0,
            'correccionV': 0
        }

        # Función auxiliar: tamaño de paso no lineal según magnitud de error
        def step_from_diff(d):
            ad = abs(d)
            if ad > 1200:
                return 10
            if ad > 600:
                return 8
            if ad > 250:
                return 6
            if ad > 80:
                return 4
            if ad > self.tolerancia:
                return 2
            return 0

        if moverV:
            if at_limit_v:
                if (diffV > 0 and current_v >= self.limiteMaxV) or (diffV < 0 and current_v <= self.limiteMinV):
                    moverV = False

            if moverV:
                errorV = diffV
                derivV = errorV - self.errorPrevV
                self.intErrV += errorV
                self.intErrV = max(min(self.intErrV, self.int_limit), -self.int_limit)
                correccionV = (self.Kp * errorV) + (self.Kd * derivV) + (self.Ki * self.intErrV)
                max_step_v = step_from_diff(errorV)
                correccionV = max(min(correccionV, max_step_v), -max_step_v)

                nuevo_v = current_v - int(correccionV)  # Invertido
                nuevo_v = max(min(nuevo_v, self.limiteMaxV), self.limiteMinV)

                self.errorPrevV = errorV
                debug_info['correccionV'] = correccionV

        if moverH:
            if at_limit_h:
                if (diffH > 0 and current_h >= self.limiteMaxH) or (diffH < 0 and current_h <= self.limiteMinH):
                    moverH = False

            if moverH:
                errorH = diffH
                derivH = errorH - self.errorPrevH
                self.intErrH += errorH
                self.intErrH = max(min(self.intErrH, self.int_limit), -self.int_limit)
                correccionH = (self.Kp * errorH) + (self.Kd * derivH) + (self.Ki * self.intErrH)
                max_step_h = step_from_diff(errorH)
                correccionH = max(min(correccionH, max_step_h), -max_step_h)

                nuevo_h = current_h + int(correccionH)
                nuevo_h = max(min(nuevo_h, self.limiteMaxH), self.limiteMinH)

                self.errorPrevH = errorH
                debug_info['correccionH'] = correccionH

        return nuevo_h, nuevo_v, debug_info


def get_device_controller(device_id):
    """Obtiene o crea el controlador PID para un dispositivo"""
    if device_id not in device_states:
        device_states[device_id] = DevicePIDController(device_id)
    return device_states[device_id]

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


#estos datos cambian dependiendo de los datos de influx
INFLUX_URL_BASE = os.environ.get('INFLUX_URL_BASE', '127.0.0.1')
INFLUX_TOKEN    = os.environ.get('INFLUX_TOKEN', 'NtZ58sLCY9fxPHq5yzC5qOr8iXVGHq81XWZs5wqu4JrN8EFgPLpFb7h96IrxCoJSSrJH85SilSxO0rrgH9VAIA==')
INFLUX_ORG      = os.environ.get('INFLUX_ORG', 'UC3M')
INFLUX_BUCKET   = os.environ.get('INFLUX_BUCKET', 'Pot_pruebas')

WRITE_URL = 'http://{}:8086/api/v2/write?org={}&bucket={}&precision=ms'.format(INFLUX_URL_BASE,INFLUX_ORG,INFLUX_BUCKET)
HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "text/plain; charset=utf-8"
}

river_analyzer = RiverAnalyzer()

@app.route("/sensor_values", methods=["POST"])
def sensor_values():
    data = request.get_json(force=True, silent=True) or {}

    # Caso: datos del tracker solar
    if any(k in data for k in ("servo_h", "servo_v", "ldr_tl", "ldr_tr", "ldr_bl", "ldr_br")):
        try:
            device_id = data.get("device_id", "unknown")
            servo_h = int(data.get("servo_h", 0))
            servo_v = int(data.get("servo_v", 0))
            ldr_tl  = int(data.get("ldr_tl", 0))
            ldr_tr  = int(data.get("ldr_tr", 0))
            ldr_bl  = int(data.get("ldr_bl", 0))
            ldr_br  = int(data.get("ldr_br", 0))
            panel_voltage = float(data.get("panel_voltage", float("nan")))

            bme_temp_c    = data.get("bme_temp_c", None)
            bme_press_hpa = data.get("bme_press_hpa", None)
            bme_hum_pct   = data.get("bme_hum_pct", None)
            bme_alt_m     = data.get("bme_alt_m", None)
            # Reportes de límites desde el ESP32
            at_limit_h = data.get("at_limit_h", False)
            at_limit_v = data.get("at_limit_v", False)

            promedioArriba = (ldr_tl + ldr_tr) / 2.0
            promedioAbajo = (ldr_bl + ldr_br) / 2.0
            promedioIzquierda = (ldr_tl + ldr_bl) / 2.0
            promedioDerecha = (ldr_tr + ldr_br) / 2.0

            # Normalizar lecturas LDR a escala 0-100
            # 50 = promedio, <50 = más oscuro, >50 = más brillante
            # Útiles para visualizar desbalances en dashboard y analizar errores de posicionamiento
            avg_all = (ldr_tl + ldr_tr + ldr_bl + ldr_br) / 4.0

            if avg_all > 0:
                norm_tl = 50 + (ldr_tl - avg_all) / avg_all * 50
                norm_tr = 50 + (ldr_tr - avg_all) / avg_all * 50
                norm_bl = 50 + (ldr_bl - avg_all) / avg_all * 50
                norm_br = 50 + (ldr_br - avg_all) / avg_all * 50
            else:
                norm_tl = norm_tr = norm_bl = norm_br = 50.0

            norm_tl = max(0, min(100, norm_tl))
            norm_tr = max(0, min(100, norm_tr))
            norm_bl = max(0, min(100, norm_bl))
            norm_br = max(0, min(100, norm_br))

            controller = get_device_controller(device_id)
            nuevo_h, nuevo_v, debug_info = controller.calcular_angulos(
                ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v, at_limit_h, at_limit_v
            )

            analisis_resultados = river_analyzer.ejecutar_analisis_completo(ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v, panel_voltage, bme_temp_c=bme_temp_c, bme_press_hpa=bme_press_hpa, bme_hum_pct=bme_hum_pct)
            ts_ms = int(time.time() * 1000)

            fields = [
                f"servo_h={servo_h}", f"servo_v={servo_v}",
                f"ldr_tl={ldr_tl}", f"ldr_tr={ldr_tr}",
                f"ldr_bl={ldr_bl}", f"ldr_br={ldr_br}",
                f"ldr_arriba={promedioArriba:.1f}", f"ldr_abajo={promedioAbajo:.1f}",
                f"ldr_izquierda={promedioIzquierda:.1f}", f"ldr_derecha={promedioDerecha:.1f}",
                f"ldr_norm_tl={norm_tl:.1f}", f"ldr_norm_tr={norm_tr:.1f}",
                f"ldr_norm_bl={norm_bl:.1f}", f"ldr_norm_br={norm_br:.1f}",
                f"limit_hit_h={'1' if at_limit_h else '0'}", f"limit_hit_v={'1' if at_limit_v else '0'}",
                f"cmd_h={nuevo_h}", f"cmd_v={nuevo_v}"
            ]

            #bme
            if bme_temp_c is not None:
                fields.append(f"bme_temp_c={float(bme_temp_c):.2f}")

            if bme_press_hpa is not None:
               fields.append(f"bme_press_hpa={float(bme_press_hpa):.2f}")

            if bme_hum_pct is not None:
              fields.append(f"bme_hum_pct={float(bme_hum_pct):.2f}")

            if bme_alt_m is not None:
                   fields.append(f"bme_alt_m={float(bme_alt_m):.2f}")
            if not math.isnan(panel_voltage):
                fields.append(f"panel_voltage={panel_voltage:.4f}")

            # Agregar resultados del análisis con River
            efic = analisis_resultados['eficiencia']
            anom = analisis_resultados['anomalias']
            drift_res = analisis_resultados['drift']

            amb = analisis_resultados.get('ambiente', {})
            if amb:
                # para influx
                fields.append(f"env_state=\"{amb.get('state','NA')}\"")
                fields.append(f"env_confidence={float(amb.get('confidence',0.0)):.2f}")
                fields.append(f"env_rel_light_change={float(amb.get('rel_light_change',0.0)):.4f}")

                fields.append(f"env_state_id={int(amb.get('state_id', -1))}")


            if efic['voltage_predicted'] is not None:
                fields.append(f"voltage_predicted={efic['voltage_predicted']:.4f}")
                fields.append(f"voltage_error={efic['error']:.4f}")
                fields.append(f"efficiency_ok={'1' if efic['status'] == 'OK' else '0'}")

            fields.append(f"anomaly_score={anom['score']:.4f}")
            fields.append(f"is_anomaly={'1' if anom['is_anomaly'] else '0'}")
            fields.append(f"drift_detected={'1' if drift_res['drift_detected'] else '0'}")

            fieldset = ",".join(fields)
            line = f"tracker,device={device_id} {fieldset} {ts_ms}"

            r = requests.post(WRITE_URL, data=line, headers=HEADERS, timeout=5)
            ok = (204 == r.status_code)

            delta_h = abs(nuevo_h - servo_h)
            delta_v = abs(nuevo_v - servo_v)
            fast_hint = {"fast_interval_ms": 400, "fast_duration_ms": 3000} if max(delta_h, delta_v) >= 2 else None

            return jsonify({
                "status": "ok" if ok else "error",
                "device_id": device_id,
                "command": {
                    "servo_h": nuevo_h,
                    "servo_v": nuevo_v
                },
                **({"fast": fast_hint} if fast_hint else {}),
                "limit_aware": {
                    "at_limit_h": at_limit_h,
                    "at_limit_v": at_limit_v,
                    "respected": True
                },
                "debug": {
                    "diffH": debug_info['diffH'],
                    "diffV": debug_info['diffV'],
                    "correccionH": debug_info['correccionH'],
                    "correccionV": debug_info['correccionV']
                },
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
                        "detected": drift_res['drift_detected'],
                        "count": drift_res['drift_count']
                    }
                }
            }), 200
        except Exception as e:
            print("[EXCEPTION] sensor_values:", repr(e))
            import traceback
            traceback.print_exc()
            return jsonify({"status": "error", "msg": str(e)}), 500




    # pruebas iniciales con el pot
    pot_value = int(data.get("pot_value", 0))
    voltage   = float(data.get("voltage", float("nan")))

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
    app.run(host="0.0.0.0", port=6000, debug=DEBUG_MODE, use_reloader=False)
