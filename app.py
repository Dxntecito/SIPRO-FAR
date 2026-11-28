import hashlib
import json
import os
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from db.connection import get_connection, load_env_file
from ml.engine import SiproFarEngine

load_env_file()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "siprofar-heysen-2026-local-key")

_engine = None


def get_engine() -> SiproFarEngine:
    global _engine
    if _engine is None:
        _engine = SiproFarEngine()
    return _engine


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Sesión requerida"}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "usuario_id" not in session:
                return jsonify({"error": "Sesión requerida"}), 401
            user_rol = session.get("user", {}).get("rol", "")
            if user_rol not in roles:
                return jsonify({"error": "No tiene permisos para realizar esta acción."}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ───────────────────────────── VISTAS HTML ─────────────────────────────

@app.route("/")
@app.route("/portal")
def portal_publico():
    """Portal Público de Transparencia de Stock para Asegurados (sin login)."""
    return render_template("portal.html", user=session.get("user"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("panel"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        pwd_hash = hash_password(password)

        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.usuario_id, u.username, u.nombre_completo, u.activo, r.nombre_rol
                    FROM usuarios u
                    JOIN roles r ON u.rol_id = r.rol_id
                    WHERE u.username = %s AND u.password_hash = %s AND u.activo = 1
                    """,
                    (username, pwd_hash),
                )
                row = cur.fetchone()
            conn.close()

            if row:
                session["usuario_id"] = row["usuario_id"]
                session["user"] = {
                    "usuario_id": row["usuario_id"],
                    "username": row["username"],
                    "nombre": row["nombre_completo"],
                    "rol": row["nombre_rol"],
                }
                return redirect(url_for("panel"))
            error = "Usuario o contraseña incorrectos."
        except Exception as e:
            error = f"Error de conexión a MySQL: {e}"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("portal_publico"))


@app.route("/panel")
@login_required
def panel():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT medicamento_id, nombre, unidad, categoria FROM medicamentos ORDER BY medicamento_id")
        medicamentos = cur.fetchall()
        cur.execute("SELECT departamento_id, nombre FROM departamentos ORDER BY departamento_id")
        departamentos = cur.fetchall()
        cur.execute("SELECT DISTINCT anio FROM consumo_mensual ORDER BY anio DESC")
        anios = [r["anio"] for r in cur.fetchall()]
    conn.close()

    return render_template(
        "panel.html",
        user=session["user"],
        medicamentos=medicamentos,
        departamentos=departamentos,
        anios=anios,
        fecha_hoy=datetime.now().strftime("%d/%m/%Y"),
    )


# ───────────────────────── API PORTAL PÚBLICO ──────────────────────────

@app.route("/api/publico/buscar")
def api_publico_buscar():
    q = request.args.get("q", "").strip()
    receta = request.args.get("receta", "").strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if q:
                like = f"%{q}%"
                cur.execute(
                    """
                    SELECT m.medicamento_id, m.nombre, m.categoria, m.unidad,
                           SUM(l.stock_actual) AS stock_total,
                           SUM(CASE WHEN l.estado_stock = 'DISPONIBLE' THEN 1 ELSE 0 END) AS areas_disponibles,
                           SUM(CASE WHEN l.estado_stock = 'CRITICO' THEN 1 ELSE 0 END) AS areas_criticas,
                           SUM(CASE WHEN l.estado_stock = 'AGOTADO' THEN 1 ELSE 0 END) AS areas_agotadas
                    FROM medicamentos m
                    JOIN inventario_lotes l ON m.medicamento_id = l.medicamento_id
                    WHERE m.nombre LIKE %s OR m.medicamento_id LIKE %s OR m.categoria LIKE %s
                    GROUP BY m.medicamento_id, m.nombre, m.categoria, m.unidad
                    ORDER BY m.medicamento_id
                    """,
                    (like, like, like),
                )
            else:
                cur.execute(
                    """
                    SELECT m.medicamento_id, m.nombre, m.categoria, m.unidad,
                           SUM(l.stock_actual) AS stock_total,
                           SUM(CASE WHEN l.estado_stock = 'DISPONIBLE' THEN 1 ELSE 0 END) AS areas_disponibles,
                           SUM(CASE WHEN l.estado_stock = 'CRITICO' THEN 1 ELSE 0 END) AS areas_criticas,
                           SUM(CASE WHEN l.estado_stock = 'AGOTADO' THEN 1 ELSE 0 END) AS areas_agotadas
                    FROM medicamentos m
                    JOIN inventario_lotes l ON m.medicamento_id = l.medicamento_id
                    GROUP BY m.medicamento_id, m.nombre, m.categoria, m.unidad
                    ORDER BY m.medicamento_id
                    """
                )
            resumen = cur.fetchall()

            # Detalle por departamento para cada medicamento encontrado
            for item in resumen:
                cur.execute(
                    """
                    SELECT d.nombre AS departamento, l.stock_actual, l.estado_stock, l.ultima_actualizacion
                    FROM inventario_lotes l
                    JOIN departamentos d ON l.departamento_id = d.departamento_id
                    WHERE l.medicamento_id = %s
                    ORDER BY d.departamento_id
                    """,
                    (item["medicamento_id"],),
                )
                det = cur.fetchall()
                for d in det:
                    if isinstance(d["ultima_actualizacion"], datetime):
                        d["ultima_actualizacion"] = d["ultima_actualizacion"].strftime("%d/%m/%Y %H:%M")
                item["detalle_areas"] = det
                item["stock_total"] = int(item["stock_total"] or 0)
                if item["stock_total"] == 0 or int(item["areas_agotadas"]) >= 3:
                    item["estado_general"] = "AGOTADO"
                elif int(item["areas_agotadas"]) > 0 or int(item["areas_criticas"]) > 0:
                    item["estado_general"] = "STOCK LIMITADO"
                else:
                    item["estado_general"] = "DISPONIBLE"

            # Registrar automáticamente en busquedas_sin_stock si el usuario buscó algo y está agotado o no existe
            registrado_sin_stock = False
            if q:
                if not resumen:
                    cur.execute(
                        "INSERT INTO busquedas_sin_stock (medicamento_id, termino_buscado, codigo_receta) VALUES (NULL, %s, %s)",
                        (q, receta or None),
                    )
                    conn.commit()
                    registrado_sin_stock = True
                else:
                    for item in resumen:
                        if item["estado_general"] in ("AGOTADO", "STOCK LIMITADO"):
                            cur.execute(
                                "INSERT INTO busquedas_sin_stock (medicamento_id, termino_buscado, codigo_receta) VALUES (%s, %s, %s)",
                                (item["medicamento_id"], q, receta or None),
                            )
                            registrado_sin_stock = True
                    if registrado_sin_stock:
                        conn.commit()

        return jsonify({"items": resumen, "registrado_sin_stock": registrado_sin_stock})
    finally:
        conn.close()


# ─────────────────────── API DASHBOARD & ANALÍTICA ─────────────────────

@app.route("/api/kpis")
@login_required
def api_kpis():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_lotes,
                    SUM(CASE WHEN estado_stock = 'DISPONIBLE' THEN 1 ELSE 0 END) AS disponibles,
                    SUM(CASE WHEN estado_stock = 'CRITICO' THEN 1 ELSE 0 END) AS criticos,
                    SUM(CASE WHEN estado_stock = 'AGOTADO' THEN 1 ELSE 0 END) AS agotados,
                    SUM(CASE WHEN gestion_vencimiento = 'POR_VENCER' THEN 1 ELSE 0 END) AS por_vencer
                FROM inventario_lotes
                """
            )
            inv = cur.fetchone()

            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_alertas,
                    SUM(CASE WHEN estado = 'PENDIENTE' THEN 1 ELSE 0 END) AS pendientes,
                    SUM(CASE WHEN estado = 'ATENDIDA' THEN 1 ELSE 0 END) AS atendidas
                FROM alertas_stock
                """
            )
            al = cur.fetchone()

            # Brecha real de subestimación en el escenario más reciente (sin multiplicar x5)
            cur.execute(
                """
                SELECT SUM(pedido_departamento) AS pedidos, SUM(demanda_siguiente) AS demanda
                FROM consumo_mensual
                WHERE anio = (SELECT MAX(anio) FROM consumo_mensual)
                """
            )
            brecha = cur.fetchone()
            pedidos = float(brecha["pedidos"] or 0)
            demanda = float(brecha["demanda"] or 1)
            subest_pct = round(((demanda - pedidos) / demanda) * 100.0, 1)

            cur.execute("SELECT COUNT(*) AS cnt FROM busquedas_sin_stock WHERE fecha_busqueda >= NOW() - INTERVAL 7 DAY")
            busq_7d = int(cur.fetchone()["cnt"] or 0)

        metrics_path = os.path.join(os.path.dirname(__file__), "ml", "model_metrics.json")
        with open(metrics_path, "r", encoding="utf-8") as f:
            mjson = json.load(f)
        winner = next(r for r in mjson["comparacion_modelos"] if r["modelo"] == mjson["modelo_ganador"])

        total_lotes = int(inv["total_lotes"] or 1)
        disp_pct = round(((total_lotes - int(inv["agotados"] or 0)) / total_lotes) * 100.0, 1)

        return jsonify({
            "disponibilidad_petitorio_pct": disp_pct,
            "lotes_disponibles": int(inv["disponibles"] or 0),
            "lotes_criticos": int(inv["criticos"] or 0),
            "lotes_agotados": int(inv["agotados"] or 0),
            "lotes_por_vencer": int(inv["por_vencer"] or 0),
            "total_lotes": total_lotes,
            "subestimacion_depts_pct": subest_pct,
            "alertas_pendientes": int(al["pendientes"] or 0),
            "alertas_atendidas": int(al["atendidas"] or 0),
            "busquedas_sin_stock_7d": busq_7d,
            "modelo_nombre": mjson["modelo_ganador"],
            "r2": winner["r2"],
            "mae": winner["mae"],
            "rmse": winner["rmse"],
            "mape_pct": winner["mape_pct"],
        })
    finally:
        conn.close()


@app.route("/api/shewhart")
@login_required
def api_shewhart():
    med_id = request.args.get("med_id", "MED-001")
    dep_id = int(request.args.get("dep_id", "1"))
    anio = int(request.args.get("anio", "2025"))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mes, pedido_departamento, consumo_real, media_movil_12, desviacion_movil_12,
                       nivel_dengue, evento_nino, demanda_siguiente
                FROM consumo_mensual
                WHERE medicamento_id = %s AND departamento_id = %s AND anio = %s
                ORDER BY mes
                """,
                (med_id, dep_id, anio),
            )
            rows = cur.fetchall()

        meses_lbl = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        labels, consumo, pedido, media, ucl, alerta2, lcl, demanda_sig, alertas_mes = [], [], [], [], [], [], [], [], []
        for r in rows:
            mu = float(r["media_movil_12"])
            sd = float(r["desviacion_movil_12"])
            c = int(r["consumo_real"])
            u = round(mu + 3 * sd, 1)
            a2 = round(mu + 2 * sd, 1)
            l = round(max(0.0, mu - 3 * sd), 1)
            labels.append(meses_lbl[int(r["mes"]) - 1])
            consumo.append(c)
            pedido.append(int(r["pedido_departamento"]))
            media.append(round(mu, 1))
            ucl.append(u)
            alerta2.append(a2)
            lcl.append(l)
            demanda_sig.append(int(r["demanda_siguiente"]))
            if c > u:
                alertas_mes.append({"mes": meses_lbl[int(r["mes"]) - 1], "consumo": c, "limite": u, "tipo": "CRITICO 3σ"})
            elif c > a2:
                alertas_mes.append({"mes": meses_lbl[int(r["mes"]) - 1], "consumo": c, "limite": a2, "tipo": "ALERTA +2σ"})

        return jsonify({
            "labels": labels,
            "consumo": consumo,
            "pedido": pedido,
            "media": media,
            "ucl": ucl,
            "alerta2": alerta2,
            "lcl": lcl,
            "demanda_siguiente": demanda_sig,
            "ucl_ultimo": ucl[-1] if ucl else 0,
            "media_ultimo": media[-1] if media else 0,
            "lcl_ultimo": lcl[-1] if lcl else 0,
            "alertas_detectadas": alertas_mes,
        })
    finally:
        conn.close()


@app.route("/api/conciliacion")
@login_required
def api_conciliacion():
    """Matriz Departamentos vs Predicción IA (1 solo escenario real, sin multiplicar x5)."""
    mes = int(request.args.get("mes", "3"))
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.medicamento_id, m.nombre AS medicamento, m.unidad, m.costo_unitario,
                       SUM(c.pedido_departamento) AS suma_depts,
                       SUM(c.consumo_real) AS consumo_real,
                       SUM(c.demanda_siguiente) AS demanda_ia,
                       SUM(c.desviacion_movil_12) AS desv_total
                FROM consumo_mensual c
                JOIN medicamentos m ON c.medicamento_id = m.medicamento_id
                WHERE c.anio = (SELECT MAX(anio) FROM consumo_mensual) AND c.mes = %s
                GROUP BY m.medicamento_id, m.nombre, m.unidad, m.costo_unitario
                ORDER BY m.medicamento_id
                """,
                (mes,),
            )
            rows = cur.fetchall()

        items = []
        total_depts_pen = 0.0
        total_ia_pen = 0.0
        for r in rows:
            suma_d = int(r["suma_depts"])
            dem_ia = int(r["demanda_ia"])
            stock_seg = int(round(1.96 * float(r["desv_total"]) * 0.45))
            req_sug = dem_ia + stock_seg
            costo_u = float(r["costo_unitario"])
            brecha_u = req_sug - suma_d
            subest = round(((suma_d - dem_ia) / dem_ia) * 100.0, 1) if dem_ia > 0 else 0.0
            brecha_pen = round(brecha_u * costo_u, 2)
            total_depts_pen += suma_d * costo_u
            total_ia_pen += req_sug * costo_u
            riesgo = "CRÍTICO" if subest <= -25 else ("ALTO" if subest <= -12 else "MODERADO")
            items.append({
                "medicamento_id": r["medicamento_id"],
                "medicamento": r["medicamento"],
                "unidad": r["unidad"],
                "costo_unitario": costo_u,
                "suma_depts": suma_d,
                "demanda_ia": dem_ia,
                "stock_seguridad": stock_seg,
                "req_sugerido": req_sug,
                "brecha_unidades": brecha_u,
                "subestimacion_pct": subest,
                "brecha_pen": brecha_pen,
                "total_sugerido_pen": round(req_sug * costo_u, 2),
                "riesgo": riesgo,
            })

        return jsonify({
            "mes": mes,
            "items": items,
            "total_depts_pen": round(total_depts_pen, 2),
            "total_sugerido_pen": round(total_ia_pen, 2),
            "brecha_total_pen": round(total_ia_pen - total_depts_pen, 2),
        })
    finally:
        conn.close()


@app.route("/api/sesgo")
@login_required
def api_sesgo():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.nombre AS departamento,
                       SUM(c.pedido_departamento) AS total_pedido,
                       SUM(c.consumo_real) AS total_consumo,
                       SUM(c.demanda_siguiente) AS total_demanda
                FROM consumo_mensual c
                JOIN departamentos d ON c.departamento_id = d.departamento_id
                WHERE c.anio >= (SELECT MAX(anio) - 1 FROM consumo_mensual)
                GROUP BY d.departamento_id, d.nombre
                """
            )
            rows = cur.fetchall()
        out = []
        for r in rows:
            ped = float(r["total_pedido"] or 0)
            cons = float(r["total_consumo"] or 1)
            dem = float(r["total_demanda"] or 1)
            sesgo_cons = round(((ped - cons) / cons) * 100.0, 1)
            sesgo_dem = round(((ped - dem) / dem) * 100.0, 1)
            out.append({
                "departamento": r["departamento"],
                "total_pedido": int(ped),
                "total_consumo": int(cons),
                "sesgo_vs_consumo_pct": sesgo_cons,
                "sesgo_vs_demanda_pct": sesgo_dem,
            })
        out.sort(key=lambda x: x["sesgo_vs_demanda_pct"])
        return jsonify(out)
    finally:
        conn.close()


@app.route("/api/simular", methods=["POST"])
@login_required
def api_simular():
    """Ejecuta el Random Forest REAL (ml/engine.py) para los 15 medicamentos en el año objetivo (2027-2030)."""
    body = request.get_json() or {}
    anio_objetivo = int(body.get("anio_objetivo", 2027))
    departamento = body.get("departamento", "Emergencia y Shock Trauma")
    mes = int(body.get("mes", 3))
    nivel_dengue = float(body.get("nivel_dengue", 1.65))
    evento_nino = float(body.get("evento_nino", 1.25))
    lluvia_mm = float(body.get("lluvia_mm", 75.0))
    desembalse = float(body.get("desembalse_almanzor", 1.15))

    # Factor de crecimiento poblacional compuesto (+3.5% anual a partir de 2026)
    factor_anio = 1.035 ** max(0, anio_objetivo - 2026)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.medicamento_id, l.stock_actual
                FROM inventario_lotes l
                JOIN departamentos d ON l.departamento_id = d.departamento_id
                WHERE d.nombre = %s
                """,
                (departamento,),
            )
            stock_map = {r["medicamento_id"]: int(r["stock_actual"]) for r in cur.fetchall()}
    finally:
        conn.close()

    eng = get_engine()
    med_ids = [f"MED-{i:03d}" for i in range(1, 16)]
    items = []
    total_normal_pen = 0.0
    total_crisis_pen = 0.0
    alertas_rojas = 0

    for mid in med_ids:
        res = eng.simular_crisis(
            medicamento_id=mid,
            departamento=departamento,
            mes=mes,
            nivel_dengue=nivel_dengue,
            evento_nino=evento_nino,
            lluvia_mm=lluvia_mm,
            desembalse_almanzor=desembalse,
            stock_actual=stock_map.get(mid, 0),
        )
        if factor_anio > 1.0:
            res["demanda_base_normal"] = int(round(res["demanda_base_normal"] * factor_anio))
            res["demanda_proyectada_crisis"] = int(round(res["demanda_proyectada_crisis"] * factor_anio))
            req_tot = res["demanda_proyectada_crisis"] + res["stock_seguridad"]
            res["requerimiento_sugerido"] = max(0, int(round(req_tot - (res["stock_actual"] or 0))))
            res["costo_estimado_soles"] = round(res["requerimiento_sugerido"] * res["costo_unitario"], 2)

        total_normal_pen += res["demanda_base_normal"] * res["costo_unitario"]
        total_crisis_pen += res["costo_estimado_soles"]
        if res["control_3sigma"]["nivel_alerta"] == "ROJO":
            alertas_rojas += 1
        items.append(res)

    return jsonify({
        "anio_objetivo": anio_objetivo,
        "departamento": departamento,
        "mes": mes,
        "modelo": "Random Forest (scikit-learn, inferencia real)",
        "items": items,
        "presupuesto_base_pen": round(total_normal_pen, 2),
        "presupuesto_crisis_pen": round(total_crisis_pen, 2),
        "alertas_3sigma_rojas": alertas_rojas,
    })


@app.route("/api/proyeccion-anual", methods=["POST"])
@login_required
def api_proyeccion_anual():
    """Proyecta los 12 meses (Ene-Dic) del año objetivo (2027-2030) con Random Forest real."""
    body = request.get_json() or {}
    anio_objetivo = int(body.get("anio_objetivo", 2027))
    medicamento_id = body.get("medicamento_id", "MED-001")
    departamento = body.get("departamento", "Emergencia y Shock Trauma")
    nivel_dengue = float(body.get("nivel_dengue", 1.65))
    evento_nino = float(body.get("evento_nino", 1.25))
    lluvia_mm = float(body.get("lluvia_mm", 75.0))
    desembalse = float(body.get("desembalse_almanzor", 1.15))

    factor_anio = 1.035 ** max(0, anio_objetivo - 2026)
    eng = get_engine()
    meses_lbl = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    dem_normal, dem_crisis, ucl_linea = [], [], []
    med_nombre = medicamento_id
    unidad = "unidades"
    costo_u = 0.0

    for m in range(1, 13):
        peso_est = 1.0 if m in (1, 2, 3, 4) else 0.45
        d_mes = 1.0 + (nivel_dengue - 1.0) * peso_est
        n_mes = 1.0 + (evento_nino - 1.0) * peso_est
        res = eng.simular_crisis(
            medicamento_id=medicamento_id,
            departamento=departamento,
            mes=m,
            nivel_dengue=d_mes,
            evento_nino=n_mes,
            lluvia_mm=lluvia_mm * peso_est,
            desembalse_almanzor=desembalse,
        )
        med_nombre = res["medicamento"]
        unidad = res["unidad"]
        costo_u = res["costo_unitario"]
        dem_normal.append(int(round(res["demanda_base_normal"] * factor_anio)))
        dem_crisis.append(int(round(res["demanda_proyectada_crisis"] * factor_anio)))
        ucl_linea.append(int(round(res["control_3sigma"]["lcs_3sigma"] * factor_anio)))

    total_anual = sum(dem_crisis)
    total_normal = sum(dem_normal)
    var_anual_pct = round(((total_anual - total_normal) / total_normal) * 100.0, 1) if total_normal > 0 else 0.0
    idx_pico = int(max(range(12), key=lambda i: dem_crisis[i]))
    meses_superan_3s = sum(1 for i in range(12) if dem_crisis[i] > ucl_linea[i])

    return jsonify({
        "anio_objetivo": anio_objetivo,
        "medicamento_id": medicamento_id,
        "medicamento": med_nombre,
        "unidad": unidad,
        "departamento": departamento,
        "labels": [f"{lbl} {anio_objetivo}" for lbl in meses_lbl],
        "demanda_normal": dem_normal,
        "demanda_crisis": dem_crisis,
        "ucl_3sigma": ucl_linea,
        "total_anual_normal": total_normal,
        "total_anual_crisis": total_anual,
        "variacion_anual_pct": var_anual_pct,
        "costo_anual_crisis": round(total_anual * costo_u, 2),
        "mes_pico": f"{meses_lbl[idx_pico]} {anio_objetivo}",
        "valor_pico": dem_crisis[idx_pico],
        "meses_en_alerta_3s": meses_superan_3s,
    })


# ─────────────────────── API CRUD FARMACIA & ALERTAS ───────────────────

@app.route("/api/inventario")
@login_required
def api_inventario_list():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.lote_id, l.medicamento_id, m.nombre AS medicamento, m.unidad,
                       d.nombre AS departamento, l.codigo_lote, l.stock_actual,
                       l.stock_minimo, l.stock_maximo, l.fecha_vencimiento,
                       l.estado_stock, l.gestion_vencimiento, l.ultima_actualizacion,
                       u.username AS actualizado_por
                FROM inventario_lotes l
                JOIN medicamentos m ON l.medicamento_id = m.medicamento_id
                JOIN departamentos d ON l.departamento_id = d.departamento_id
                LEFT JOIN usuarios u ON l.actualizado_por = u.usuario_id
                ORDER BY
                    FIELD(l.estado_stock, 'AGOTADO', 'CRITICO', 'DISPONIBLE'),
                    l.fecha_vencimiento ASC
                """
            )
            rows = cur.fetchall()
            for r in rows:
                r["fecha_vencimiento"] = str(r["fecha_vencimiento"])
                if isinstance(r["ultima_actualizacion"], datetime):
                    r["ultima_actualizacion"] = r["ultima_actualizacion"].strftime("%d/%m/%Y %H:%M")
        return jsonify(rows)
    finally:
        conn.close()


@app.route("/api/inventario/<int:lote_id>", methods=["POST"])
@role_required("FARMACEUTICO", "DIGITADOR")
def api_inventario_update(lote_id):
    body = request.get_json() or {}
    stock_actual = max(0, int(body.get("stock_actual", 0)))
    stock_minimo = max(0, int(body.get("stock_minimo", 50)))
    fecha_venc = body.get("fecha_vencimiento")
    gest_venc = body.get("gestion_vencimiento", "VIGENTE")

    if stock_actual == 0:
        estado = "AGOTADO"
    elif stock_actual < stock_minimo:
        estado = "CRITICO"
    else:
        estado = "DISPONIBLE"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inventario_lotes
                SET stock_actual = %s,
                    stock_minimo = %s,
                    fecha_vencimiento = %s,
                    estado_stock = %s,
                    gestion_vencimiento = %s,
                    actualizado_por = %s
                WHERE lote_id = %s
                """,
                (stock_actual, stock_minimo, fecha_venc, estado, gest_venc, session["usuario_id"], lote_id),
            )
            conn.commit()
        return jsonify({"ok": True, "estado_stock": estado})
    finally:
        conn.close()


@app.route("/api/alertas")
@login_required
def api_alertas_list():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.alerta_id, a.medicamento_id, m.nombre AS medicamento,
                       d.nombre AS departamento, a.tipo_alerta, a.nivel,
                       a.z_score, a.requerimiento_sugerido, a.mensaje,
                       a.estado, a.fecha_creacion, a.fecha_atencion,
                       u.username AS atendido_por
                FROM alertas_stock a
                JOIN medicamentos m ON a.medicamento_id = m.medicamento_id
                JOIN departamentos d ON a.departamento_id = d.departamento_id
                LEFT JOIN usuarios u ON a.atendido_por = u.usuario_id
                ORDER BY FIELD(a.estado, 'PENDIENTE', 'ATENDIDA'), FIELD(a.nivel, 'ROJO', 'AMBAR'), a.fecha_creacion DESC
                """
            )
            rows = cur.fetchall()
            for r in rows:
                r["z_score"] = float(r["z_score"]) if r["z_score"] is not None else None
                if isinstance(r["fecha_creacion"], datetime):
                    r["fecha_creacion"] = r["fecha_creacion"].strftime("%d/%m/%Y %H:%M")
                if isinstance(r["fecha_atencion"], datetime):
                    r["fecha_atencion"] = r["fecha_atencion"].strftime("%d/%m/%Y %H:%M")
        return jsonify(rows)
    finally:
        conn.close()


@app.route("/api/alertas/<int:alerta_id>/atender", methods=["POST"])
@role_required("FARMACEUTICO", "DIGITADOR")
def api_alerta_atender(alerta_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE alertas_stock
                SET estado = 'ATENDIDA', fecha_atencion = NOW(), atendido_por = %s
                WHERE alerta_id = %s
                """,
                (session["usuario_id"], alerta_id),
            )
            conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/reporte-semanal")
@login_required
def api_reporte_semanal():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(b.medicamento_id, 'NO-CAT') AS medicamento_id,
                       COALESCE(m.nombre, b.termino_buscado) AS medicamento,
                       COUNT(*) AS total_busquedas,
                       MAX(b.fecha_busqueda) AS ultima_busqueda
                FROM busquedas_sin_stock b
                LEFT JOIN medicamentos m ON b.medicamento_id = m.medicamento_id
                WHERE b.fecha_busqueda >= NOW() - INTERVAL 7 DAY
                GROUP BY COALESCE(b.medicamento_id, 'NO-CAT'), COALESCE(m.nombre, b.termino_buscado)
                ORDER BY total_busquedas DESC
                """
            )
            ranking = cur.fetchall()
            for r in ranking:
                if isinstance(r["ultima_busqueda"], datetime):
                    r["ultima_busqueda"] = r["ultima_busqueda"].strftime("%d/%m/%Y %H:%M")

            cur.execute(
                """
                SELECT b.busqueda_id, b.termino_buscado, b.codigo_receta, b.fecha_busqueda,
                       COALESCE(m.nombre, 'No catalogado') AS medicamento
                FROM busquedas_sin_stock b
                LEFT JOIN medicamentos m ON b.medicamento_id = m.medicamento_id
                ORDER BY b.fecha_busqueda DESC
                LIMIT 20
                """
            )
            recientes = cur.fetchall()
            for r in recientes:
                if isinstance(r["fecha_busqueda"], datetime):
                    r["fecha_busqueda"] = r["fecha_busqueda"].strftime("%d/%m/%Y %H:%M")

        return jsonify({"ranking": ranking, "recientes": recientes})
    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=True, host="0.0.0.0", port=port)
