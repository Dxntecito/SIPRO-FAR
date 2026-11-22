import json
import math
import os
import joblib
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "modelo_siprofar.joblib")
METRICS_PATH = os.path.join(BASE_DIR, "model_metrics.json")
CSV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "dataset_medicamentos_mensual.csv"))


class SiproFarEngine:
    """Motor predictivo ML + Control Estadístico 3-Sigma + Simulador de Crisis."""

    def __init__(self, model_path: str = MODEL_PATH, csv_path: str = CSV_PATH):
        self.model = joblib.load(model_path)
        self.df = pd.read_csv(csv_path)
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            self.metrics = json.load(f)

        # Precompute baseline lookup per (medicamento_id, departamento, mes)
        self.baselines = (
            self.df.groupby(["medicamento_id", "departamento", "mes"], as_index=False)
            .agg(
                medicamento=("medicamento", "first"),
                categoria=("categoria", "first"),
                unidad=("unidad", "first"),
                costo_unitario=("costo_unitario", "first"),
                base_mensual=("base_mensual", "first"),
                sensibilidad_dengue=("sensibilidad_dengue", "first"),
                sensibilidad_clima=("sensibilidad_clima", "first"),
                pedido_departamento=("pedido_departamento", "mean"),
                consumo_mes_actual=("consumo_mes_actual", "mean"),
                lag_1=("lag_1", "mean"),
                lag_2=("lag_2", "mean"),
                lag_3=("lag_3", "mean"),
                lag_12=("lag_12", "mean"),
                media_movil_3=("media_movil_3", "mean"),
                media_movil_12=("media_movil_12", "mean"),
                desviacion_movil_12=("desviacion_movil_12", "mean"),
                nivel_dengue=("nivel_dengue", "mean"),
                evento_nino=("evento_nino", "mean"),
                lluvia_mm=("lluvia_mm", "mean"),
                desembalse_almanzor=("desembalse_almanzor", "mean"),
                pronostico_dengue_mes_objetivo=("pronostico_dengue_mes_objetivo", "mean"),
                pronostico_nino_mes_objetivo=("pronostico_nino_mes_objetivo", "mean"),
            )
        )

    @staticmethod
    def evaluar_3sigma(valor_observado: float, media_12: float, desv_12: float) -> dict:
        desv = max(float(desv_12), 1e-6)
        media = float(media_12)
        val = float(valor_observado)
        z = (val - media) / desv
        lcs_3 = media + 3.0 * desv
        lci_3 = max(0.0, media - 3.0 * desv)
        alerta_2 = media + 2.0 * desv

        if val > lcs_3:
            estado = "CRITICO_3SIGMA"
            nivel_alerta = "ROJO"
            mensaje = (
                f"Ruptura de límite superior 3σ (Z = {z:+.2f}). "
                "Activar requerimiento urgente de reposición en ≤48 h (MEA03)."
            )
        elif val > alerta_2:
            estado = "ALERTA_2SIGMA"
            nivel_alerta = "AMBAR"
            mensaje = (
                f"Tendencia anómala sobre +2σ (Z = {z:+.2f}). "
                "Monitorear stock diario y preparar orden preventiva."
            )
        elif val < lci_3:
            estado = "SUBCONSUMO_3SIGMA"
            nivel_alerta = "AMBAR"
            mensaje = (
                f"Consumo inusualmente bajo (Z = {z:+.2f}). "
                "Revisar riesgo de sobre-stock y lotes próximos a vencer."
            )
        else:
            estado = "NORMAL"
            nivel_alerta = "VERDE"
            mensaje = f"Operación dentro de control estadístico normal (Z = {z:+.2f})."

        return {
            "valor_observado": round(val, 1),
            "media_12": round(media, 1),
            "desviacion_12": round(desv, 1),
            "z_score": round(z, 2),
            "lci_3sigma": round(lci_3, 1),
            "alerta_2sigma": round(alerta_2, 1),
            "lcs_3sigma": round(lcs_3, 1),
            "estado": estado,
            "nivel_alerta": nivel_alerta,
            "mensaje": mensaje,
        }

    def _get_baseline_row(self, medicamento_id: str, departamento: str, mes: int) -> dict:
        m = self.baselines[
            (self.baselines["medicamento_id"] == medicamento_id)
            & (self.baselines["departamento"] == departamento)
            & (self.baselines["mes"] == int(mes))
        ]
        if m.empty:
            raise ValueError(f"Combinación no encontrada: {medicamento_id} / {departamento} / mes {mes}")
        return m.iloc[0].to_dict()

    def _predict_row(self, row: dict) -> float:
        mes = int(row["mes"])
        row["mes_sin"] = math.sin(2.0 * math.pi * mes / 12.0)
        row["mes_cos"] = math.cos(2.0 * math.pi * mes / 12.0)
        cols = self.metrics["features"]["categoricas"] + self.metrics["features"]["numericas"]
        X = pd.DataFrame([{c: row[c] for c in cols}])
        pred = float(self.model.predict(X)[0])
        return max(0.0, pred)

    def simular_crisis(
        self,
        medicamento_id: str,
        departamento: str,
        mes: int,
        nivel_dengue: float = 1.0,
        evento_nino: float = 1.0,
        lluvia_mm: float = 20.0,
        desembalse_almanzor: float = 1.0,
        stock_actual: float | None = None,
    ) -> dict:
        base = self._get_baseline_row(medicamento_id, departamento, mes)

        # 1) Escenario base normal (sin crisis)
        row_normal = dict(base)
        row_normal["nivel_dengue"] = 1.0
        row_normal["evento_nino"] = 1.0
        row_normal["lluvia_mm"] = 15.0
        row_normal["desembalse_almanzor"] = 1.0
        row_normal["pronostico_dengue_mes_objetivo"] = 1.0
        row_normal["pronostico_nino_mes_objetivo"] = 1.0
        pred_normal = self._predict_row(row_normal)

        # 2) Escenario simulado de crisis
        row_crisis = dict(base)
        row_crisis["nivel_dengue"] = float(nivel_dengue)
        row_crisis["evento_nino"] = float(evento_nino)
        row_crisis["lluvia_mm"] = float(lluvia_mm)
        row_crisis["desembalse_almanzor"] = float(desembalse_almanzor)
        row_crisis["pronostico_dengue_mes_objetivo"] = float(nivel_dengue)
        row_crisis["pronostico_nino_mes_objetivo"] = float(evento_nino)

        # Ajustar consumo actual proporcional a sensibilidad si hay crisis activa
        factor_shock = (
            1.0
            + (float(nivel_dengue) - 1.0) * (base["sensibilidad_dengue"] * 0.35)
            + (float(evento_nino) - 1.0) * (base["sensibilidad_clima"] * 0.30)
            + (float(desembalse_almanzor) - 1.0) * 0.40
        )
        factor_shock = max(0.85, factor_shock)
        row_crisis["consumo_mes_actual"] = base["consumo_mes_actual"] * factor_shock
        row_crisis["pedido_departamento"] = base["pedido_departamento"] * factor_shock

        pred_crisis = self._predict_row(row_crisis)

        # Stock de seguridad = 1.5 * desviacion_movil_12 (colchón operativo)
        stock_seguridad = 1.5 * base["desviacion_movil_12"]
        requerimiento_total = pred_crisis + stock_seguridad
        if stock_actual is not None:
            requerimiento_sugerido = max(0.0, requerimiento_total - float(stock_actual))
        else:
            requerimiento_sugerido = requerimiento_total

        delta_pct = ((pred_crisis - pred_normal) / pred_normal * 100.0) if pred_normal > 0 else 0.0
        control_3s = self.evaluar_3sigma(pred_crisis, base["media_movil_12"], base["desviacion_movil_12"])

        return {
            "medicamento_id": medicamento_id,
            "medicamento": base["medicamento"],
            "categoria": base["categoria"],
            "unidad": base["unidad"],
            "departamento": departamento,
            "mes": int(mes),
            "costo_unitario": round(float(base["costo_unitario"]), 2),
            "demanda_base_normal": int(round(pred_normal)),
            "demanda_proyectada_crisis": int(round(pred_crisis)),
            "variacion_crisis_pct": round(delta_pct, 1),
            "stock_seguridad": int(round(stock_seguridad)),
            "stock_actual": int(round(stock_actual)) if stock_actual is not None else None,
            "requerimiento_sugerido": int(round(requerimiento_sugerido)),
            "costo_estimado_soles": round(requerimiento_sugerido * float(base["costo_unitario"]), 2),
            "control_3sigma": control_3s,
            "parametros_crisis": {
                "nivel_dengue": float(nivel_dengue),
                "evento_nino": float(evento_nino),
                "lluvia_mm": float(lluvia_mm),
                "desembalse_almanzor": float(desembalse_almanzor),
            },
        }

    def serie_3sigma(self, medicamento_id: str, departamento: str, escenario_id: int | None = None) -> list:
        sub = self.df[
            (self.df["medicamento_id"] == medicamento_id)
            & (self.df["departamento"] == departamento)
        ].copy()
        if sub.empty:
            return []
        if escenario_id is None:
            # Pick most recent year's highest scenario_id
            max_anio = sub["anio"].max()
            escenario_id = int(sub[sub["anio"] == max_anio]["escenario_id"].max())
        s = sub[sub["escenario_id"] == int(escenario_id)].sort_values("mes")
        out = []
        for _, r in s.iterrows():
            c3 = self.evaluar_3sigma(r["consumo_mes_actual"], r["media_movil_12"], r["desviacion_movil_12"])
            out.append(
                {
                    "escenario_id": int(r["escenario_id"]),
                    "anio": int(r["anio"]),
                    "mes": int(r["mes"]),
                    "consumo": int(r["consumo_mes_actual"]),
                    "pedido": int(r["pedido_departamento"]),
                    "demanda_objetivo": int(r["demanda_mes_anio_siguiente"]),
                    "media_12": c3["media_12"],
                    "lcs_3sigma": c3["lcs_3sigma"],
                    "alerta_2sigma": c3["alerta_2sigma"],
                    "lci_3sigma": c3["lci_3sigma"],
                    "z_score": c3["z_score"],
                    "estado": c3["estado"],
                    "nivel_alerta": c3["nivel_alerta"],
                    "nivel_dengue": round(float(r["nivel_dengue"]), 2),
                    "evento_nino": round(float(r["evento_nino"]), 2),
                }
            )
        return out


if __name__ == "__main__":
    eng = SiproFarEngine()
    print("=== PRUEBA MOTOR SIPRO-FAR (Crisis Dengue + Niño + Desembalse) ===")
    sim = eng.simular_crisis(
        medicamento_id="MED-001",
        departamento="Emergencia y Shock Trauma",
        mes=3,
        nivel_dengue=2.2,
        evento_nino=1.4,
        lluvia_mm=110.0,
        desembalse_almanzor=1.25,
        stock_actual=4500,
    )
    print(json.dumps(sim, indent=2, ensure_ascii=False))
