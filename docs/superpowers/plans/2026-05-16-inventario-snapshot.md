# Inventario con baseline de InventarioHistórico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modificar `get_inventario` en `Inicio.py` para que ancle el cálculo de stock al snapshot más reciente por SKU en `InventarioHistórico`, sumando/restando solo los movimientos posteriores.

**Architecture:** Reemplazo de un bloque SQL (CTE) dentro de una función Python en un app Streamlit + PostgreSQL. La fórmula nueva es `Stock = Inicial + Ingresos − Transf. Salida − Ventas`, con todas las cantidades post-snapshot (frontera estricta `>`). Productos sin snapshot caen al comportamiento previo (Inicial = 0, acumulado completo).

**Tech Stack:** Python 3, Streamlit, psycopg2, PostgreSQL.

**Spec:** [docs/superpowers/specs/2026-05-16-inventario-snapshot-design.md](../specs/2026-05-16-inventario-snapshot-design.md)

**Notas sobre testing en este proyecto:**
- No hay framework de tests instalado (`requirements.txt` solo trae streamlit/pandas/psycopg2/reportlab/plotly/openpyxl).
- No se va a introducir pytest para un cambio de una sola consulta SQL (fuera de alcance).
- La verificación es manual contra la BD de desarrollo usando la consola SQL ya existente (`pages/99_Query.py`) y la propia tab de Inventario del dashboard.

---

## Task 1: Reemplazar la query SQL de `get_inventario`

**Files:**
- Modify: `Inicio.py:221-259`

- [ ] **Step 1: Reemplazar el cuerpo completo de `get_inventario`**

Localiza `Inicio.py:221-259`. Reemplaza el bloque completo de la función `get_inventario` (desde el decorador `@st.cache_data(ttl=120)` hasta el final del `return`) con este código:

```python
@st.cache_data(ttl=120)
def get_inventario():
    """Calcula el stock actual por producto anclado al último snapshot físico.

    Para cada SKU:
      - Inicial      = "Peso" del registro más reciente en InventarioHistórico (0 si no hay).
      - Ingresos     = SUM(MovimientosInventario.Debe)  con Fecha > snapshot.Fecha
      - Transf. Sal. = SUM(MovimientosInventario.Haber) con Fecha > snapshot.Fecha
      - Ventas       = SUM(DetallePedido.Peso) de pedidos no anulados con Pedido.Fecha > snapshot.Fecha
      - Stock        = Inicial + Ingresos − Transf. Salida − Ventas

    SKUs sin snapshot: Inicial = 0 y todos los movimientos/ventas cuentan
    (reproduce el cálculo previo hasta que se registre el primer snapshot).
    """
    rows = run_query("""
        WITH ultimo_snapshot AS (
            SELECT "SKU", MAX("Fecha") AS fecha_base
            FROM "InventarioHistórico"
            GROUP BY "SKU"
        ),
        base AS (
            SELECT p."SKU",
                   p."Producto",
                   COALESCE(ih."Peso", 0) AS stock_inicial,
                   us.fecha_base
            FROM "Productos" p
            LEFT JOIN ultimo_snapshot us ON us."SKU" = p."SKU"
            LEFT JOIN "InventarioHistórico" ih
                   ON ih."SKU"   = us."SKU"
                  AND ih."Fecha" = us.fecha_base
        ),
        entradas AS (
            SELECT b."SKU",
                   COALESCE(SUM(m."Debe"),  0) AS debe,
                   COALESCE(SUM(m."Haber"), 0) AS haber
            FROM base b
            LEFT JOIN "MovimientosInventario" m
                ON m."SKU" = b."SKU"
               AND (b.fecha_base IS NULL OR m."Fecha" > b.fecha_base)
            GROUP BY b."SKU"
        ),
        ventas_validas AS (
            SELECT d."SKU", d."Peso", pe."Fecha"
            FROM "DetallePedido" d
            JOIN "Pedidos" pe ON pe."ID_Pedido" = d."ID_Pedido"
            WHERE pe."Estado" != 'Anulado'
        ),
        salidas AS (
            SELECT b."SKU",
                   COALESCE(SUM(v."Peso"), 0) AS peso
            FROM base b
            LEFT JOIN ventas_validas v
                ON v."SKU" = b."SKU"
               AND (b.fecha_base IS NULL OR v."Fecha" > b.fecha_base)
            GROUP BY b."SKU"
        )
        SELECT b."SKU",
               b."Producto",
               ROUND(b.stock_inicial::numeric, 2) AS "Inicial (lb)",
               COALESCE(e.debe,  0)               AS "Ingresos (lb)",
               COALESCE(e.haber, 0)               AS "Transf. Salida (lb)",
               COALESCE(s.peso,  0)               AS "Ventas (lb)",
               ROUND(
                   (b.stock_inicial
                    + COALESCE(e.debe,  0)
                    - COALESCE(e.haber, 0)
                    - COALESCE(s.peso,  0))::numeric, 2
               ) AS "Stock (lb)"
        FROM base b
        LEFT JOIN entradas e ON e."SKU" = b."SKU"
        LEFT JOIN salidas  s ON s."SKU" = b."SKU"
        ORDER BY b."Producto"
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["SKU", "Producto", "Inicial (lb)", "Ingresos (lb)",
                 "Transf. Salida (lb)", "Ventas (lb)", "Stock (lb)"]
    )
```

- [ ] **Step 2: Verificar la query directamente contra la BD**

Arranca la app:

```bash
streamlit run Inicio.py
```

Entra como rol `dev` y abre la página **💻 Consola de Base de Datos** (`pages/99_Query.py`). Pega ahí el bloque `WITH ultimo_snapshot AS ( ... ORDER BY b."Producto"` exactamente (sin el `run_query("""` ni los triples cierres) y ejecuta.

Esperado:
- La consulta devuelve una fila por cada producto en `"Productos"`.
- Columnas presentes y en este orden: `SKU`, `Producto`, `Inicial (lb)`, `Ingresos (lb)`, `Transf. Salida (lb)`, `Ventas (lb)`, `Stock (lb)`.
- Ningún error de tipo, ningún SKU duplicado.

Si falla, leer el error y corregir antes de seguir. NO continuar al Step 3 sin que la consulta funcione.

---

## Task 2: Agregar columna "Inicial (lb)" al `column_config` del tab de inventario

**Files:**
- Modify: `Inicio.py:362-383`

- [ ] **Step 1: Editar el `column_config` del `st.dataframe` del tab de inventario**

Localiza en `Inicio.py:362-383` el `st.dataframe(df_inv, ...)` dentro de `with tab_inv:`. Reemplaza solo el diccionario `column_config={...}` con este (agrega `"Inicial (lb)"` después de `"Producto"`):

```python
column_config={
    "SKU": st.column_config.TextColumn("SKU"),
    "Producto": st.column_config.TextColumn("Producto"),
    "Inicial (lb)": st.column_config.NumberColumn(
        "Inicial (lb)", format="%.2f"
    ),
    "Ingresos (lb)": st.column_config.NumberColumn(
        "Ingresos (lb)", format="%.2f"
    ),
    "Transf. Salida (lb)": st.column_config.NumberColumn(
        "Transf. Salida (lb)", format="%.2f"
    ),
    "Ventas (lb)": st.column_config.NumberColumn(
        "Ventas (lb)", format="%.2f"
    ),
    "Stock (lb)": st.column_config.NumberColumn(
        "Stock (lb)", format="%.2f"
    ),
},
```

---

## Task 3: Verificación manual en la app

**Files:** (ninguno — solo correr la app)

- [ ] **Step 1: Recargar la app y abrir la tab de Inventario**

Si streamlit ya está corriendo, presiona "R" en la pestaña del navegador o reinicia con `streamlit run Inicio.py`. Entra al **🏠 Menú principal** → tab **📦 Inventario**.

Click en **🔄 Actualizar inventario** para invalidar el cache de Streamlit.

- [ ] **Step 2: Verificar que la tabla muestra las 7 columnas en orden**

Esperado en orden: `SKU`, `Producto`, `Inicial (lb)`, `Ingresos (lb)`, `Transf. Salida (lb)`, `Ventas (lb)`, `Stock (lb)`. Todas las numéricas con 2 decimales.

- [ ] **Step 3: Validar un SKU CON snapshot**

En la **💻 Consola de Base de Datos** (`pages/99_Query.py`), ejecuta:

```sql
SELECT "SKU", MAX("Fecha") AS fecha_base
FROM "InventarioHistórico"
GROUP BY "SKU"
ORDER BY fecha_base DESC
LIMIT 5;
```

Toma un SKU del resultado (ej. `SKU_X` con `fecha_base = 2026-04-30`). Ejecuta:

```sql
-- Inicial esperado
SELECT "Peso" FROM "InventarioHistórico"
WHERE "SKU" = 'SKU_X' AND "Fecha" = '2026-04-30';

-- Ingresos esperados (Debe posterior)
SELECT COALESCE(SUM("Debe"), 0) FROM "MovimientosInventario"
WHERE "SKU" = 'SKU_X' AND "Fecha" > '2026-04-30';

-- Transf. Salida esperada (Haber posterior)
SELECT COALESCE(SUM("Haber"), 0) FROM "MovimientosInventario"
WHERE "SKU" = 'SKU_X' AND "Fecha" > '2026-04-30';

-- Ventas esperadas (pedidos no anulados posteriores)
SELECT COALESCE(SUM(d."Peso"), 0)
FROM "DetallePedido" d
JOIN "Pedidos" pe ON pe."ID_Pedido" = d."ID_Pedido"
WHERE d."SKU" = 'SKU_X'
  AND pe."Estado" != 'Anulado'
  AND pe."Fecha" > '2026-04-30';
```

(Sustituir `'SKU_X'` y `'2026-04-30'` por los valores reales tomados de la consulta anterior.)

Esperado: cada uno de esos cuatro valores coincide con la celda correspondiente de ese SKU en la tab de Inventario, y `Stock = Inicial + Ingresos − Transf.Salida − Ventas`.

- [ ] **Step 4: Validar un SKU SIN snapshot**

En la consola SQL ejecuta:

```sql
SELECT p."SKU"
FROM "Productos" p
LEFT JOIN "InventarioHistórico" ih ON ih."SKU" = p."SKU"
WHERE ih."SKU" IS NULL
LIMIT 5;
```

Toma un SKU del resultado (ej. `SKU_Y`) y compáralo en la tab de Inventario:

- `Inicial (lb)` debe ser `0.00`.
- `Ingresos (lb)`, `Transf. Salida (lb)`, `Ventas (lb)` deben coincidir con la suma histórica completa de ese SKU:

```sql
SELECT
  COALESCE(SUM("Debe"),  0) AS debe_total,
  COALESCE(SUM("Haber"), 0) AS haber_total
FROM "MovimientosInventario" WHERE "SKU" = 'SKU_Y';

SELECT COALESCE(SUM(d."Peso"), 0)
FROM "DetallePedido" d
JOIN "Pedidos" pe ON pe."ID_Pedido" = d."ID_Pedido"
WHERE d."SKU" = 'SKU_Y' AND pe."Estado" != 'Anulado';
```

- [ ] **Step 5: Validar la frontera estricta `>`**

Si el SKU validado en Step 3 tiene algún movimiento o venta exactamente en `fecha_base`, verificar que NO se cuenta. Consulta para ver si existe ese caso:

```sql
SELECT 'movimiento' AS tipo, m."Fecha", m."Debe", m."Haber"
FROM "MovimientosInventario" m
WHERE m."SKU" = 'SKU_X' AND m."Fecha" = '2026-04-30'
UNION ALL
SELECT 'venta' AS tipo, pe."Fecha", d."Peso", NULL
FROM "DetallePedido" d
JOIN "Pedidos" pe ON pe."ID_Pedido" = d."ID_Pedido"
WHERE d."SKU" = 'SKU_X' AND pe."Fecha" = '2026-04-30' AND pe."Estado" != 'Anulado';
```

Si esa consulta devuelve filas, esos pesos NO deben aparecer en los totales de la tab Inventario para ese SKU. Si la consulta no devuelve filas, este step se considera ya cubierto por Step 3 y se marca completo.

- [ ] **Step 6: Validar métricas resumen**

Arriba de la tabla de inventario hay tres métricas: `Stock total`, `Productos con stock`, `Productos sin stock`. Confirma que:

- `Stock total` ≈ suma de la columna `Stock (lb)` (puede haber pequeñas diferencias por redondeo al sumar).
- `Productos con stock` = cantidad de filas con `Stock (lb) > 0`.
- `Productos sin stock` = cantidad de filas con `Stock (lb) <= 0`.

---

## Task 4: Commit

**Files:** (todos los cambios anteriores)

- [ ] **Step 1: Revisar los cambios**

```bash
git status
git diff Inicio.py
```

Esperado: cambios solo en `Inicio.py` (función `get_inventario` y `column_config` del tab de inventario).

- [ ] **Step 2: Commit**

```bash
git add Inicio.py
git commit -m "$(cat <<'EOF'
feat(inventario): anclar cálculo al último snapshot de InventarioHistórico

Stock = Inicial (último snapshot por SKU) + Ingresos posteriores
      − Transf. Salida posteriores − Ventas no anuladas posteriores.

Productos sin snapshot conservan el comportamiento previo (acumulado
histórico completo con Inicial = 0). Se agrega columna "Inicial (lb)"
a la vista del tab Inventario.
EOF
)"
```

- [ ] **Step 3: Verificar**

```bash
git log -1 --stat
```

Esperado: un commit nuevo afectando solo `Inicio.py`.
