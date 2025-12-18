#LANZA servidor y manda datos a influx

from flask import Flask, request, jsonify
import requests
import time
import math

app = Flask("servidor_flask")

INFLUX_URL_BASE = '127.0.0.1'  #local
INFLUX_TOKEN = 'NtZ58sLCY9fxPHq5yzC5qOr8iXVGHq81XWZs5wqu4JrN8EFgPLpFb7h96IrxCoJSSrJH85SilSxO0rrgH9VAIA=='#token, guardada en carpeta de clase de lunes
INFLUX_ORG   = 'UC3M'
INFLUX_BUCKET= 'Pot_pruebas'#recuerda cambiar


WRITE_URL = 'http://{}:8086/api/v2/write?org={}&bucket={}&precision=ms'.format(INFLUX_URL_BASE,INFLUX_ORG,INFLUX_BUCKET)#lanzar influx db simepre
HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "text/plain; charset=utf-8"
}

@app.route("/sensor_values", methods=["POST"])
def sensor_values():
    data = request.get_json(force=True, silent=True) or {}
    pot_value = int(data.get("pot_value", 0))
    voltage   = float(data.get("voltage", float("nan")))

    print(f"Recibido -> pot_value={pot_value}, voltage={voltage:.3f} V")#datos en consola

    #valor de voltaje, 0 a 3.3
    ts_ms = int(time.time() * 1000)
    fields = [f"value={pot_value}"]
    if not math.isnan(voltage):
        fields.append(f"voltage={voltage}")
    fieldset = ",".join(fields)

   #este es para mostrar el valor en crudo, considera usar el otro query
    #ts_ms = int(time.time() * 1000)
    #fields = [f"value={pot_value}"]
    #if not math.isnan(pot_value):
    #    fields.append(f"pot_value={pot_value}")
    #fieldset = ",".join(fields)

    line = f"potentiometer,device=esp32 field_count=2,{fieldset} {ts_ms}"


    try:
        r = requests.post(WRITE_URL, data=line, headers=HEADERS, timeout=5)
        ok = (204 == r.status_code)  #204 se ve en monitor arduino
        return jsonify({
            "status": "ok" if ok else "error",
            "influx_status_code": r.status_code,
            "received": data
        }), (200 if ok else 500)
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000, debug=False, use_reloader=False) #permite que se pueda abrir port, de esta manera se quita el erorr de python
