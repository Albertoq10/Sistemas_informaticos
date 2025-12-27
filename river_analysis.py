"""
Módulo de análisis con River ML para el tracker solar.

Funciones:
- Predicción de eficiencia del panel solar
- Detección de anomalías en sensores
- Detección de concept drift
"""

import time
import math
from river import linear_model, preprocessing, anomaly, drift, optim


class RiverAnalyzer:
    """Analizador de Machine Learning para tracker solar usando River"""
    
    def __init__(self):
        # 1. PREDICCIÓN DE EFICIENCIA
        # Modelo de regresión adaptativa que predice el voltaje esperado según la luz recibida
        # Características: promedio de LDRs, hora del día, posiciones de servos
        self.efficiency_model = preprocessing.StandardScaler() | linear_model.LinearRegression(
            optimizer=optim.SGD(0.01),
            l2=0.001
        )
        
        # 2. DETECCIÓN DE ANOMALÍAS
        # Detecta lecturas fuera de lo normal (sensores dañados, sombras, bloqueos mecánicos)
        # HalfSpaceTrees es eficiente para streaming y detecta outliers en tiempo real
        self.anomaly_detector = anomaly.HalfSpaceTrees(
            n_trees=10,
            height=8,
            window_size=250,
            seed=42
        )
        
        # 3. DETECCIÓN DE CONCEPT DRIFT
        # Monitorea cambios en la distribución de datos (cambios estacionales/climáticos)
        # ADWIN detecta cuándo el modelo debe "reaprender" el entorno
        self.drift_detector = drift.ADWIN(delta=0.002)
        
        # Métricas y contadores
        self.model_predictions_count = 0
        self.anomalies_detected = 0
        self.drift_detected_count = 0
    
    def calcular_caracteristicas(self, ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v):
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
    
    def analizar_eficiencia(self, features, panel_voltage):
        """
        Predice el voltaje esperado y detecta baja eficiencia del panel solar.
        
        Args:
            features: Diccionario con características del sistema
            panel_voltage: Voltaje real medido del panel
        
        Returns:
            dict: Información sobre el análisis de eficiencia
        """
        voltage_real = panel_voltage
        
        resultado = {
            'voltage_real': voltage_real,
            'voltage_predicted': None,
            'error': None,
            'status': 'TRAINING'
        }
        
        if self.model_predictions_count > 10:
            voltage_predicted = self.efficiency_model.predict_one(features)
            voltage_error = abs(voltage_real - voltage_predicted)
            
            efficiency_threshold = 0.5
            efficiency_status = "OK" if voltage_error < efficiency_threshold else "LOW_EFFICIENCY"
            
            resultado.update({
                'voltage_predicted': voltage_predicted,
                'error': voltage_error,
                'status': efficiency_status
            })
        
        # Entrenar el modelo con los datos actuales
        self.efficiency_model.learn_one(features, voltage_real)
        self.model_predictions_count += 1
        
        return resultado
    
    def detectar_anomalias(self, avg_light, light_variance, servo_h, servo_v):
        """
        Detecta comportamientos anómalos en el sistema (sensores dañados, sombras, bloqueos).
        
        Returns:
            dict: Información sobre la detección de anomalías
        """
        anomaly_features = {
            'avg_light': avg_light,
            'light_variance': light_variance,
            'servo_h': float(servo_h),
            'servo_v': float(servo_v)
        }
        
        anomaly_score = self.anomaly_detector.score_one(anomaly_features)
        self.anomaly_detector.learn_one(anomaly_features)
        
        anomaly_threshold = 0.7
        is_anomaly = anomaly_score > anomaly_threshold
        
        if is_anomaly:
            self.anomalies_detected += 1
        
        return {
            'score': anomaly_score,
            'is_anomaly': is_anomaly,
            'threshold': anomaly_threshold
        }
    
    def detectar_concept_drift(self, light_variance):
        """
        Detecta cambios drásticos en los patrones del sistema (cambios estacionales/climáticos).
        
        Returns:
            dict: Información sobre la detección de concept drift
        """
        self.drift_detector.update(light_variance)
        
        resultado = {
            'drift_detected': self.drift_detector.drift_detected,
            'drift_count': self.drift_detected_count
        }
        
        if self.drift_detector.drift_detected:
            self.drift_detected_count += 1
            resultado['drift_count'] = self.drift_detected_count
        
        return resultado
    
    def ejecutar_analisis_completo(self, ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v, panel_voltage):
        """
        Ejecuta todos los análisis de Machine Learning con River.
        
        Args:
            ldr_tl, ldr_tr, ldr_bl, ldr_br: Lecturas de los 4 sensores LDR
            servo_h, servo_v: Posiciones actuales de los servos
            panel_voltage: Voltaje real medido del panel
        
        Returns:
            dict: Resultados de todos los análisis
        """
        features, avg_light, light_variance = self.calcular_caracteristicas(
            ldr_tl, ldr_tr, ldr_bl, ldr_br, servo_h, servo_v
        )
        
        eficiencia = self.analizar_eficiencia(features, panel_voltage)
        
        anomalias = self.detectar_anomalias(avg_light, light_variance, servo_h, servo_v)
        
        drift = self.detectar_concept_drift(light_variance)
        
        return {
            'eficiencia': eficiencia,
            'anomalias': anomalias,
            'drift': drift
        }
    
    def get_stats(self):
        """Retorna estadísticas actuales del analizador"""
        return {
            'predictions_count': self.model_predictions_count,
            'anomalies_detected': self.anomalies_detected,
            'drift_detected_count': self.drift_detected_count
        }
