import hashlib
import os
import random
from datetime import datetime, timedelta
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "dataset_medicamentos_mensual.csv"))
OUT_SQL = os.path.join(BASE_DIR, "seed_mysql.sql")


def sql_str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "NULL"
    s = str(val).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def generate_seed():
    df = pd.read_csv(CSV_PATH)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "-- =============================================================================",
        "-- SIPRO-FAR — Carga Inicial de Datos (MySQL 8.0 / Workbench / Railway)",
        "-- Generado automáticamente desde data/dataset_medicamentos_mensual.csv",
        "-- Ejecutar DESPUÉS de db/schema_mysql.sql",
        "-- =============================================================================",
        "",
        "USE siprofar_db;",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
        "TRUNCATE TABLE busquedas_sin_stock;",
        "TRUNCATE TABLE alertas_stock;",
        "TRUNCATE TABLE consumo_mensual;",
        "TRUNCATE TABLE inventario_lotes;",
        "TRUNCATE TABLE usuarios;",
        "TRUNCATE TABLE departamentos;",
        "TRUNCATE TABLE medicamentos;",
        "SET FOREIGN_KEY_CHECKS = 1;",
        "",
        "-- 1. Roles (4 roles base)",
        "INSERT IGNORE INTO roles (rol_id, nombre_rol, descripcion) VALUES",
        "  (1, 'FARMACEUTICO', 'Químico Farmacéutico: gestión CRUD de inventario, lotes, vencimientos y alertas 3-Sigma'),",
        "  (2, 'DIGITADOR',    'Digitador Asistencial: registro diario de stock y apoyo operativo en UPSS Farmacia'),",
        "  (3, 'PLANEAMIENTO', 'División de Planeamiento y Calidad: consulta analítica, simulador de crisis y auditoría KPI/KGI'),",
        "  (4, 'DIRECCION',    'Dirección del Hospital: supervisión ejecutiva, aprobación de requerimientos y gobierno COBIT');",
        "",
        "-- 2. Usuarios de prueba (contraseñas SHA-256: Farmacia2026*, Calidad2026*, Direccion2026*)",
        "INSERT INTO usuarios (usuario_id, rol_id, username, password_hash, nombre_completo, activo) VALUES",
        f"  (1, 1, 'farmacia_heysen',  {sql_str(hash_password('Farmacia2026*'))},  'Q.F. Jefe de Servicio de Farmacia', 1),",
        f"  (2, 3, 'calidad_heysen',   {sql_str(hash_password('Calidad2026*'))},   'Ing. Nilton Ascorbe Díaz (Planeamiento y Calidad)', 1),",
        f"  (3, 4, 'direccion_heysen', {sql_str(hash_password('Direccion2026*'))}, 'Dirección Hospital II-1 Luis Heysen', 1);",
        "",
        "-- 3. Catálogo de 15 Medicamentos Críticos",
        "INSERT INTO medicamentos (medicamento_id, nombre, categoria, unidad, costo_unitario, base_mensual, sensibilidad_dengue, sensibilidad_clima) VALUES",
    ]

    meds = (
        df[
            [
                "medicamento_id",
                "medicamento",
                "categoria",
                "unidad",
                "costo_unitario",
                "base_mensual",
                "sensibilidad_dengue",
                "sensibilidad_clima",
            ]
        ]
        .drop_duplicates(subset=["medicamento_id"])
        .sort_values("medicamento_id")
    )
    med_vals = []
    for r in meds.itertuples(index=False):
        med_vals.append(
            f"  ({sql_str(r.medicamento_id)}, {sql_str(r.medicamento)}, {sql_str(r.categoria)}, "
            f"{sql_str(r.unidad)}, {float(r.costo_unitario):.2f}, {int(r.base_mensual)}, "
            f"{float(r.sensibilidad_dengue):.2f}, {float(r.sensibilidad_clima):.2f})"
        )
    lines.append(",\n".join(med_vals) + ";")
    lines.append("")

    # 4. Departamentos
    depts = sorted(df["departamento"].unique().tolist())
    dept_map = {name: i + 1 for i, name in enumerate(depts)}
    lines.append("-- 4. Departamentos / UPSS del Hospital Luis Heysen (5 áreas)")
    lines.append("INSERT INTO departamentos (departamento_id, nombre) VALUES")
    lines.append(",\n".join([f"  ({i + 1}, {sql_str(name)})" for i, name in enumerate(depts)]) + ";")
    lines.append("")

    # 5. Inventario de Lotes (75 lotes) y Alertas iniciales
    rng = random.Random(42)
    promedios = (
        df.groupby(["medicamento_id", "departamento"], as_index=False)["consumo_mes_actual"]
        .mean()
        .rename(columns={"consumo_mes_actual": "prom"})
    )

    agotados_demo = {
        ("MED-001", "Emergencia y Shock Trauma"),
        ("MED-013", "Consulta Externa y Telemedicina (Cenate)"),
    }
    criticos_demo = {
        ("MED-002", "Emergencia y Shock Trauma"),
        ("MED-014", "Emergencia y Shock Trauma"),
        ("MED-015", "Hospitalización General"),
        ("MED-003", "Centro Quirúrgico y CMA (Desembalse)"),
    }

    lote_vals = []
    alerta_vals = []

    for idx, r in promedios.iterrows():
        med_id = r["medicamento_id"]
        dep_name = r["departamento"]
        dep_id = dept_map[dep_name]
        prom = int(round(r["prom"]))
        stock_min = max(50, int(round(prom * 0.35)))
        stock_max = max(200, int(round(prom * 1.60)))

        if (med_id, dep_name) in agotados_demo:
            stock_actual = 0
            estado = "AGOTADO"
        elif (med_id, dep_name) in criticos_demo:
            stock_actual = max(10, int(round(stock_min * 0.55)))
            estado = "CRITICO"
        else:
            stock_actual = int(round(prom * rng.uniform(0.75, 1.35)))
            estado = "DISPONIBLE" if stock_actual >= stock_min else "CRITICO"

        if idx % 11 == 0:
            dias_venc = rng.randint(18, 45)
            gest_venc = "POR_VENCER"
        else:
            dias_venc = rng.randint(120, 540)
            gest_venc = "VIGENTE"

        fecha_venc = (now + timedelta(days=dias_venc)).strftime("%Y-%m-%d")
        cod_lote = f"LT-{med_id[-3:]}-{dep_id:02d}-{now.strftime('%y%m')}"

        lote_vals.append(
            f"  ({sql_str(med_id)}, {dep_id}, {sql_str(cod_lote)}, {stock_actual}, {stock_min}, {stock_max}, "
            f"{sql_str(fecha_venc)}, {sql_str(estado)}, {sql_str(gest_venc)}, 1, {sql_str(now_str)})"
        )

        if estado in ("AGOTADO", "CRITICO"):
            req = max(0, stock_max - stock_actual)
            nivel = "ROJO" if estado == "AGOTADO" else "AMBAR"
            z_sim = 3.45 if estado == "AGOTADO" else 2.35
            t_alerta = "3SIGMA" if estado == "AGOTADO" else "STOCK_MIN"
            f_cre = (now - timedelta(hours=rng.randint(2, 18))).strftime("%Y-%m-%d %H:%M:%S")
            msg = f"Stock {estado.lower()} ({stock_actual} u. vs mínimo {stock_min} u.). Generar requerimiento en <=48 h."
            alerta_vals.append(
                f"  ({sql_str(med_id)}, {dep_id}, {sql_str(t_alerta)}, {sql_str(nivel)}, {z_sim:.2f}, {req}, "
                f"{sql_str(msg)}, 'PENDIENTE', {sql_str(f_cre)}, NULL, NULL)"
            )

        if gest_venc == "POR_VENCER":
            f_cre = (now - timedelta(hours=rng.randint(4, 30))).strftime("%Y-%m-%d %H:%M:%S")
            msg = f"Lote {cod_lote} vence el {fecha_venc} ({dias_venc} días). Priorizar dispensación o redistribución (KPI-04)."
            alerta_vals.append(
                f"  ({sql_str(med_id)}, {dep_id}, 'VENCIMIENTO', 'AMBAR', NULL, 0, "
                f"{sql_str(msg)}, 'PENDIENTE', {sql_str(f_cre)}, NULL, NULL)"
            )

    # 3 alertas atendidas dentro del SLA de 48h (KPI-03) por usuario 1 (farmacia_heysen)
    for med_id, dep_name, horas in [
        ("MED-001", "Hospitalización General", 14),
        ("MED-002", "Unidad de Cuidados Intensivos (UCI)", 22),
        ("MED-005", "Emergencia y Shock Trauma", 9),
    ]:
        f_cre = now - timedelta(days=3)
        f_ate = f_cre + timedelta(hours=horas)
        msg = "Pico 3-Sigma detectado; requerimiento enviado a Red Lambayeque dentro del SLA de 48 h."
        alerta_vals.append(
            f"  ({sql_str(med_id)}, {dept_map[dep_name]}, '3SIGMA', 'ROJO', 3.28, 1800, "
            f"{sql_str(msg)}, 'ATENDIDA', {sql_str(f_cre.strftime('%Y-%m-%d %H:%M:%S'))}, "
            f"{sql_str(f_ate.strftime('%Y-%m-%d %H:%M:%S'))}, 1)"
        )

    lines.append("-- 5. Inventario de Lotes (75 lotes con stock, vencimientos y auditoría)")
    lines.append(
        "INSERT INTO inventario_lotes "
        "(medicamento_id, departamento_id, codigo_lote, stock_actual, stock_minimo, stock_maximo, "
        "fecha_vencimiento, estado_stock, gestion_vencimiento, actualizado_por, ultima_actualizacion) VALUES"
    )
    lines.append(",\n".join(lote_vals) + ";")
    lines.append("")

    lines.append("-- 6. Alertas de Stock 3-Sigma, Mínimo y Vencimientos")
    lines.append(
        "INSERT INTO alertas_stock "
        "(medicamento_id, departamento_id, tipo_alerta, nivel, z_score, requerimiento_sugerido, "
        "mensaje, estado, fecha_creacion, fecha_atencion, atendido_por) VALUES"
    )
    lines.append(",\n".join(alerta_vals) + ";")
    lines.append("")

    # 7. Búsquedas sin stock (Portal Público — Reporte Semanal)
    muestra_busquedas = [
        ("MED-001", "Paracetamol 500 mg", "REC-2026-0142", 1),
        ("MED-001", "Paracetamol tableta", "REC-2026-0158", 1),
        ("MED-001", "Paracetamol 500", "REC-2026-0191", 2),
        ("MED-001", "Paracetamol 500 mg", "REC-2026-0205", 3),
        ("MED-013", "Insulina NPH", "REC-2026-0149", 1),
        ("MED-013", "Insulina Humana", "REC-2026-0177", 2),
        ("MED-013", "Insulina NPH 100 UI", "REC-2026-0211", 4),
        ("MED-002", "Cloruro de Sodio 0.9%", "REC-2026-0163", 2),
        ("MED-002", "Suero fisiologico", "REC-2026-0220", 5),
        ("MED-014", "Paracetamol gotas", "REC-2026-0188", 3),
    ]
    lines.append("-- 7. Búsquedas sin Stock en Portal Público (Reporte Semanal)")
    lines.append("INSERT INTO busquedas_sin_stock (medicamento_id, termino_buscado, codigo_receta, fecha_busqueda) VALUES")
    busq_vals = [
        f"  ({sql_str(m)}, {sql_str(t)}, {sql_str(rec)}, {sql_str((now - timedelta(days=d, hours=rng.randint(1, 10))).strftime('%Y-%m-%d %H:%M:%S'))})"
        for m, t, rec, d in muestra_busquedas
    ]
    lines.append(",\n".join(busq_vals) + ";")
    lines.append("")

    # 8. Histórico de consumo_mensual (1 escenario completo por año 2016-2025 = 9,000 filas en bloques de 500)
    selected_scenarios = df.groupby("anio")["escenario_id"].max().tolist()
    df_hist = df[df["escenario_id"].isin(selected_scenarios)].copy()
    df_hist["departamento_id"] = df_hist["departamento"].map(dept_map)

    lines.append(f"-- 8. Histórico de Consumos Mensuales ({len(df_hist)} filas: 1 escenario por año 2016-2025)")
    chunk_size = 500
    rows_list = list(
        df_hist[
            [
                "escenario_id",
                "medicamento_id",
                "departamento_id",
                "anio",
                "mes",
                "pedido_departamento",
                "consumo_mes_actual",
                "media_movil_12",
                "desviacion_movil_12",
                "nivel_dengue",
                "evento_nino",
                "lluvia_mm",
                "desembalse_almanzor",
                "demanda_mes_anio_siguiente",
            ]
        ].itertuples(index=False, name=None)
    )

    for start in range(0, len(rows_list), chunk_size):
        chunk = rows_list[start : start + chunk_size]
        lines.append(
            "INSERT INTO consumo_mensual "
            "(escenario_id, medicamento_id, departamento_id, anio, mes, pedido_departamento, "
            "consumo_real, media_movil_12, desviacion_movil_12, nivel_dengue, evento_nino, "
            "lluvia_mm, desembalse_almanzor, demanda_siguiente) VALUES"
        )
        cvals = [
            f"  ({int(r[0])}, {sql_str(r[1])}, {int(r[2])}, {int(r[3])}, {int(r[4])}, {int(r[5])}, "
            f"{int(r[6])}, {float(r[7]):.2f}, {float(r[8]):.2f}, {float(r[9]):.3f}, {float(r[10]):.3f}, "
            f"{float(r[11]):.2f}, {float(r[12]):.3f}, {int(r[13])})"
            for r in chunk
        ]
        lines.append(",\n".join(cvals) + ";")

    with open(OUT_SQL, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    size_kb = round(os.path.getsize(OUT_SQL) / 1024, 1)
    print(f"Archivo generado con éxito: {OUT_SQL} ({size_kb} KB)")
    print(f" - 4 roles, 3 usuarios, {len(meds)} medicamentos, {len(depts)} departamentos")
    print(f" - {len(lote_vals)} lotes, {len(alerta_vals)} alertas, {len(busq_vals)} búsquedas, {len(rows_list)} consumos históricos")


if __name__ == "__main__":
    generate_seed()
