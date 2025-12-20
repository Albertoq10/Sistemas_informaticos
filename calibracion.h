#pragma once

// Lógica de calibración - incluida solo si CALIBRATION_MODE es true

#ifdef CALIBRATION_MODE

void printLdrDiagnostics() {
  int tl = analogRead(ldrTL);
  int tr = analogRead(ldrTR);
  int bl = analogRead(ldrBL);
  int br = analogRead(ldrBR);

  int promedioArriba = (tl + tr) / 2;
  int promedioAbajo  = (bl + br) / 2;
  int promedioIzq    = (tl + bl) / 2;
  int promedioDer    = (tr + br) / 2;

  int diffV = promedioArriba - promedioAbajo;   // positivo => arriba más luz
  int diffH = promedioIzq - promedioDer;        // positivo => izquierda más luz

  const char* sugV = (abs(diffV) > tolerancia) ? (diffV > 0 ? "^" : "v") : "-";
  const char* sugH = (abs(diffH) > tolerancia) ? (diffH > 0 ? "<" : ">") : "-";

  Serial.println("--- DIAGNÓSTICO LDR ---");
  Serial.print("TL:"); Serial.print(tl);
  Serial.print(" TR:"); Serial.print(tr);
  Serial.print(" BL:"); Serial.print(bl);
  Serial.print(" BR:"); Serial.println(br);

  Serial.print("Arriba:"); Serial.print(promedioArriba);
  Serial.print(" Abajo:"); Serial.print(promedioAbajo);
  Serial.print("  DiffV:"); Serial.print(diffV);
  Serial.print("  Sugerido V:"); Serial.println(sugV);

  Serial.print("Izq:"); Serial.print(promedioIzq);
  Serial.print(" Der:"); Serial.print(promedioDer);
  Serial.print("  DiffH:"); Serial.print(diffH);
  Serial.print("  Sugerido H:"); Serial.println(sugH);
  Serial.println("-----------------------");
}

bool processCommand(const String &command) {
  if (command == "h+") {
    posH += 5;
    Serial.print("H: ");
    Serial.println(posH);
  } else if (command == "h-") {
    posH -= 5;
    Serial.print("H: ");
    Serial.println(posH);
  } else if (command == "v+") {
    posV += 5;
    Serial.print("V: ");
    Serial.println(posV);
  } else if (command == "v-") {
    posV -= 5;
    Serial.print("V: ");
    Serial.println(posV);
  } else if (command.startsWith("h=")) {
    int v = command.substring(2).toInt();
    posH = constrain(v, 0, 180);
    Serial.print("H set: ");
    Serial.println(posH);
  } else if (command.startsWith("v=")) {
    int v = command.substring(2).toInt();
    posV = constrain(v, 0, 180);
    Serial.print("V set: ");
    Serial.println(posV);
  } else if (command == "status") {
    Serial.print("H:");
    Serial.print(posH);
    Serial.print(" V:");
    Serial.println(posV);
  } else if (command.startsWith("lmin:")) {
    limiteMinH = command.substring(5).toInt();
    Serial.print("Min H: ");
    Serial.println(limiteMinH);
  } else if (command.startsWith("lmax:")) {
    limiteMaxH = command.substring(5).toInt();
    Serial.print("Max H: ");
    Serial.println(limiteMaxH);
  } else if (command.startsWith("vmin:")) {
    limiteMinV = command.substring(5).toInt();
    Serial.print("Min V: ");
    Serial.println(limiteMinV);
  } else if (command.startsWith("vmax:")) {
    limiteMaxV = command.substring(5).toInt();
    Serial.print("Max V: ");
    Serial.println(limiteMaxV);
  } else if (command == "help") {
    Serial.println("=== CALIBRACIÓN ===");
    Serial.println("h+/h- : Mover horizontal ±5°");
    Serial.println("v+/v- : Mover vertical ±5°");
    Serial.println("h=X  : Fijar horizontal a X (0-180)");
    Serial.println("v=X  : Fijar vertical a X (0-180)");
    Serial.println("status: Ver posición actual");
    Serial.println("lmin:X : Set límite mín horizontal (ej: lmin:20)");
    Serial.println("lmax:X : Set límite máx horizontal (ej: lmax:160)");
    Serial.println("vmin:X : Set límite mín vertical (ej: vmin:20)");
    Serial.println("vmax:X : Set límite máx vertical (ej: vmax:160)");
    Serial.println("probe  : Leer LDR y mostrar diagnóstico (arriba/abajo/izq/der)");
    Serial.println("start : Salir de calibración");
  } else if (command == "probe") {
    printLdrDiagnostics();
  } else if (command == "start") {
    return true; // señal para salir
  }

  servoH.write(posH);
  servoV.write(posV);
  return false;
}

void handleSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    bool wantsStart = processCommand(command);
    if (wantsStart) {
      // no salir aquí; el loop de espera lo manejará
    }
  }
}

void enterCalibrationMode() {
  Serial.println("\n=== MODO CALIBRACIÓN ===");
  Serial.println("Escribe 'help' para ver comandos");
  Serial.println("Escribe 'start' para salir de calibración y comenzar loop");

  bool ready = false;
  while (!ready) {
    if (Serial.available() > 0) {
      String cmd = Serial.readStringUntil('\n');
      cmd.trim();
      bool wantsStart = processCommand(cmd);
      if (wantsStart) {
        ready = true;
      }
      if (cmd == "help") {
        Serial.println("Comando 'start' para iniciar loop normal");
      }
    }
    delay(20);
  }
}

#endif
