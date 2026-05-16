# Recálculo del inventario con baseline de `InventarioHistórico`

**Fecha:** 2026-05-16
**Archivo objetivo:** `Inicio.py` (función `get_inventario` y `column_config` del tab de inventario)

## Problema

La vista de inventario actual calcula el stock como:

```
Stock = SUM(MovimientosInventario.Debe)
      − SUM(MovimientosInventario.Haber)
      − SUM(DetallePedido.Peso de pedidos no anulados)
```

Esto recorre **todo el historial** de movimientos y ventas desde el inicio del tiempo. No usa los snapshots físicos registrados en `InventarioHistórico`, por lo que cualquier discrepancia entre el conteo físico y el cálculo contable se acumula indefinidamente.

## Solución

Anclar el cálculo al **último snapshot por SKU** y sumar/restar únicamente lo posterior:

```
Stock = Inicial
      + SUM(Debe posteriores al snapshot)
      − SUM(Haber posteriores al snapshot)
      − SUM(Ventas no anuladas posteriores al snapshot)
```

### Reglas precisas

| Caso | Tratamiento |
|---|---|
| SKU con snapshot en `InventarioHistórico` | `Inicial = "Peso"` del snapshot más reciente (`MAX(Fecha)`); movimientos/ventas contados solo si `Fecha > snapshot.Fecha` (estricto, snapshot es fin-de-día) |
| SKU sin snapshot | `Inicial = 0`; se cuentan **todos** los movimientos y ventas del SKU (reproduce el cálculo actual hasta que se registre el primer snapshot) |
| Pedidos | Excluir `Estado = 'Anulado'`; incluir `'Pagado'` y `'Pendiente de Pago'` |
| Movimientos | Sumar todos (no hay flag de anulación en `MovimientosInventario`) |

### Columnas devueltas (orden definido)

`SKU`, `Producto`, `Inicial (lb)`, `Ingresos (lb)`, `Transf. Salida (lb)`, `Ventas (lb)`, `Stock (lb)`

`Inicial (lb)` es nueva (sufijo `(lb)` por consistencia con las otras columnas de peso). Las demás conservan nombre y semántica, pero `Ingresos`, `Transf. Salida` y `Ventas` ahora son **post-snapshot**, no acumuladas históricas.

## Implementación

### 1. SQL nuevo dentro de `get_inventario` (reemplazo del CTE actual)

```sql
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
ORDER BY b."Producto";
```

### 2. Cambios en Python

- `Inicio.py:222-259` (`get_inventario`): reemplazar el SQL del CTE actual con el bloque de arriba. Ampliar la lista de columnas del `DataFrame` vacío (caso sin filas) para incluir `"Inicial (lb)"` después de `"Producto"`.
- Docstring de `get_inventario`: actualizar para describir la nueva fórmula con baseline.
- `Inicio.py:362-383` (`column_config` del `st.dataframe` del tab de inventario): agregar entrada para `"Inicial (lb)"` con `st.column_config.NumberColumn("Inicial (lb)", format="%.2f")`, posicionada en el orden lógico (después de `Producto`, antes de `Ingresos (lb)`).

### 3. Métricas resumen

`Inicio.py:351-358` calcula `total_stock`, `productos_con_stock`, `productos_sin_stock` desde la columna `"Stock (lb)"`. La columna conserva su nombre y semántica → **no requiere cambios**.

## Verificación

Tests manuales en la app después del cambio:

1. **SKU con snapshot reciente** — verificar que `Stock = Inicial + Δ Debe − Δ Haber − Δ Ventas`, donde los `Δ` solo incluyen filas con `Fecha > snapshot.Fecha`.
2. **SKU sin snapshot** — verificar que el resultado coincide con el cálculo previo (suma histórica completa).
3. **SKU con movimientos exactamente en `snapshot.Fecha`** — verificar que NO se cuentan (frontera estricta `>`).
4. **SKU con pedido `Anulado` posterior al snapshot** — verificar que NO descuenta.
5. **Métricas resumen** — `Stock total`, `productos con/sin stock` deben mostrarse correctamente.
6. **Caso vacío** — sin productos, sin error.

## Fuera de alcance

- Crear una VIEW en PostgreSQL (se mantiene CTE inline por consistencia con el patrón del resto del ERP).
- Cambios al módulo de carga masiva o a `3_Movimientos_de_Inventario.py`.
- Histórico de cambios en el cálculo (auditoría de cuándo cambió la fórmula).
- Indicar en la UI la fecha del último snapshot por SKU (se descartó en el diseño de columnas).
