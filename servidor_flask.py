#LANZA servidor y manda datos a influx

from flask import Flask, request, jsonify
import requests
import time
import math
import os
from river import linear_model, preprocessing
import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

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

            ts_ms = int(time.time() * 1000)
            fields = [
                f"servo_h={servo_h}", f"servo_v={servo_v}",
                f"ldr_tl={ldr_tl}", f"ldr_tr={ldr_tr}",
                f"ldr_bl={ldr_bl}", f"ldr_br={ldr_br}"
            ]
            fieldset = ",".join(fields)
            line = f"tracker,device=esp32 {fieldset} {ts_ms}"

            r = requests.post(WRITE_URL, data=line, headers=HEADERS, timeout=5)
            ok = (204 == r.status_code)
            return jsonify({
                "status": "ok" if ok else "error",
                "influx_status_code": r.status_code,
                "received": data
            }), (200 if ok else 500)
        except Exception as e:
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
    app.run(host="0.0.0.0", port=6000, debug=False, use_reloader=False) #permite que se pueda abrir port, de esta manera se quita el erorr de python
