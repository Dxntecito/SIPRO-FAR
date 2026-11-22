-- SIPRO-FAR — Esquema de Base de Datos Relacional (Trabajar con workbench 8.0+ de preferencia)
-- Hospital II-1 Luis Enrique Heysen Incháustegui 
-- Alineación COBIT 2019: MEA03 (Nivel 4), DSS04 (Nivel 4), Ley 29733 y OEI 5

CREATE DATABASE IF NOT EXISTS siprofar_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE siprofar_db;

-- 1. Roles del Sistema (permite escalar y agregar nuevos roles sin alterar tablas)
CREATE TABLE IF NOT EXISTS roles (
    rol_id       INT AUTO_INCREMENT PRIMARY KEY,
    nombre_rol   VARCHAR(50)  NOT NULL UNIQUE,
    descripcion  VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

-- 2. Usuarios y Control de Acceso por Rol (Ley 29733 para evitar filtraciones de datos sensibles)
CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id      INT AUTO_INCREMENT PRIMARY KEY,
    rol_id          INT          NOT NULL,
    username        VARCHAR(60)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(150) NOT NULL,
    activo          TINYINT(1)   NOT NULL DEFAULT 1,
    fecha_creacion  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usuarios_rol
        FOREIGN KEY (rol_id) REFERENCES roles(rol_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 3. Catálogo de Medicamentos Críticos (15 ítems)
CREATE TABLE IF NOT EXISTS medicamentos (
    medicamento_id      VARCHAR(20)    PRIMARY KEY,
    nombre              VARCHAR(180)   NOT NULL,
    categoria           VARCHAR(150)   NOT NULL,
    unidad              VARCHAR(50)    NOT NULL,
    costo_unitario      DECIMAL(10, 2) NOT NULL CHECK (costo_unitario >= 0),
    base_mensual        INT            NOT NULL CHECK (base_mensual >= 0),
    sensibilidad_dengue DECIMAL(5, 2)  NOT NULL DEFAULT 1.00,
    sensibilidad_clima  DECIMAL(5, 2)  NOT NULL DEFAULT 1.00
) ENGINE=InnoDB;

-- 4. Departamentos / UPSS del Hospital Luis Heysen (5 áreas críticas)
CREATE TABLE IF NOT EXISTS departamentos (
    departamento_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- 5. Inventario Actual y Control de Lotes / Vencimientos (CRUD + Portal Público + KPI-04)
CREATE TABLE IF NOT EXISTS inventario_lotes (
    lote_id              INT AUTO_INCREMENT PRIMARY KEY,
    medicamento_id       VARCHAR(20) NOT NULL,
    departamento_id      INT         NOT NULL,
    codigo_lote          VARCHAR(50) NOT NULL,
    stock_actual         INT         NOT NULL CHECK (stock_actual >= 0),
    stock_minimo         INT         NOT NULL CHECK (stock_minimo >= 0),
    stock_maximo         INT         NOT NULL CHECK (stock_maximo >= 0),
    fecha_vencimiento    DATE        NOT NULL,
    estado_stock         ENUM('DISPONIBLE', 'CRITICO', 'AGOTADO') NOT NULL DEFAULT 'DISPONIBLE',
    gestion_vencimiento  ENUM('VIGENTE', 'POR_VENCER', 'REDISTRIBUIDO', 'DADO_DE_BAJA') NOT NULL DEFAULT 'VIGENTE',
    actualizado_por      INT         NULL,
    ultima_actualizacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_inv_medicamento
        FOREIGN KEY (medicamento_id) REFERENCES medicamentos(medicamento_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_inv_departamento
        FOREIGN KEY (departamento_id) REFERENCES departamentos(departamento_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_inv_usuario
        FOREIGN KEY (actualizado_por) REFERENCES usuarios(usuario_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_inv_med_dep (medicamento_id, departamento_id),
    INDEX idx_inv_estado (estado_stock, fecha_vencimiento)
) ENGINE=InnoDB;

-- 6. Historial de consumos mensuales (alimenta control 3-Sigma y ML)
CREATE TABLE IF NOT EXISTS consumo_mensual (
    consumo_id           INT AUTO_INCREMENT PRIMARY KEY,
    escenario_id         INT            NOT NULL,
    medicamento_id       VARCHAR(20)    NOT NULL,
    departamento_id      INT            NOT NULL,
    anio                 SMALLINT       NOT NULL,
    mes                  TINYINT        NOT NULL CHECK (mes BETWEEN 1 AND 12),
    pedido_departamento  INT            NOT NULL,
    consumo_real         INT            NOT NULL,
    media_movil_12       DECIMAL(10, 2) NOT NULL,
    desviacion_movil_12  DECIMAL(10, 2) NOT NULL,
    nivel_dengue         DECIMAL(5, 3)  NOT NULL,
    evento_nino          DECIMAL(5, 3)  NOT NULL,
    lluvia_mm            DECIMAL(6, 2)  NOT NULL,
    desembalse_almanzor  DECIMAL(5, 3)  NOT NULL,
    demanda_siguiente    INT            NOT NULL,
    CONSTRAINT fk_cons_medicamento
        FOREIGN KEY (medicamento_id) REFERENCES medicamentos(medicamento_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_cons_departamento
        FOREIGN KEY (departamento_id) REFERENCES departamentos(departamento_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_cons_med_dep_fecha (medicamento_id, departamento_id, anio, mes)
) ENGINE=InnoDB;

-- 7. Alertas predictivas 3-Sigma, stock mínimo y vencimientos (KPI-03: atención <= 48 h)
CREATE TABLE IF NOT EXISTS alertas_stock (
    alerta_id              INT AUTO_INCREMENT PRIMARY KEY,
    medicamento_id         VARCHAR(20)  NOT NULL,
    departamento_id        INT          NOT NULL,
    tipo_alerta            ENUM('3SIGMA', 'STOCK_MIN', 'VENCIMIENTO') NOT NULL,
    nivel                  ENUM('ROJO', 'AMBAR') NOT NULL,
    z_score                DECIMAL(6, 2) NULL,
    requerimiento_sugerido INT          NOT NULL DEFAULT 0,
    mensaje                VARCHAR(500) NOT NULL,
    estado                 ENUM('PENDIENTE', 'ATENDIDA') NOT NULL DEFAULT 'PENDIENTE',
    fecha_creacion         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_atencion         DATETIME     NULL,
    atendido_por           INT          NULL,
    CONSTRAINT fk_alerta_medicamento
        FOREIGN KEY (medicamento_id) REFERENCES medicamentos(medicamento_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_alerta_departamento
        FOREIGN KEY (departamento_id) REFERENCES departamentos(departamento_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_alerta_usuario
        FOREIGN KEY (atendido_por) REFERENCES usuarios(usuario_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_alertas_estado (estado, nivel)
) ENGINE=InnoDB;

-- 8. Registro de Búsquedas sin Stock en Portal Público (Reporte Semanal ex Propuesta 4)
CREATE TABLE IF NOT EXISTS busquedas_sin_stock (
    busqueda_id     INT AUTO_INCREMENT PRIMARY KEY,
    medicamento_id  VARCHAR(20)  NULL,
    termino_buscado VARCHAR(180) NOT NULL,
    codigo_receta   VARCHAR(60)  NULL,
    fecha_busqueda  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_busq_medicamento
        FOREIGN KEY (medicamento_id) REFERENCES medicamentos(medicamento_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_busq_fecha (fecha_busqueda)
) ENGINE=InnoDB;

-- Datos iniciales mínimos de roles
INSERT IGNORE INTO roles (nombre_rol, descripcion) VALUES
    ('FARMACEUTICO', 'Químico Farmacéutico: gestión CRUD de inventario, lotes, vencimientos y alertas 3-Sigma'),
    ('DIGITADOR',    'Digitador Asistencial: registro diario de stock y apoyo operativo en UPSS Farmacia'),
    ('PLANEAMIENTO', 'División de Planeamiento y Calidad: consulta analítica, simulador de crisis y auditoría KPI/KGI'),
    ('DIRECCION',    'Dirección del Hospital: supervisión ejecutiva, aprobación de requerimientos y gobierno COBIT');
