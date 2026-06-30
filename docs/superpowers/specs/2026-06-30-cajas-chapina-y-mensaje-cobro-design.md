# Diseño: Cajas CHAPINA y mensaje de cobro

> **Fecha:** 2026-06-30
> **Estado:** Aprobado por el usuario (brainstorming).

## Objetivo

Dos entregables independientes pedidos por el dueño del negocio (GrassFed GT):

1. **Dos promociones nuevas** ("Value Box Chapina" y "Premium Box Chapina") que conviven
   con las cajas actuales (Value Box / Premium Box).
2. Un **mensaje de cobro para copiar y pegar** (estilo WhatsApp) que arma el saludo, el
   total y los datos de pago (transferencia / tarjeta), generable desde dos pantallas.

## Parte 1 — Cajas CHAPINA

### Enfoque

Seguir el patrón existente (`BUNDLE_CONFIGS` en `pages/1_Registro_de_Detalles.py`): las cajas
son datos hardcodeados en Python; la caja se inserta como una línea con precio, y cada
componente como línea con precio Q0 (para descontar inventario sin cobrar doble). Es
consistente con lo actual y de bajo riesgo. (Migrar a una tabla de configuración en BD queda
como mejora futura, fuera de alcance.)

### Productos de catálogo nuevos (requeridos por la FK `DetallePedido.SKU → Productos.SKU`)

Insert idempotente en `Productos`:

| SKU | Producto | Precio |
|---|---|---|
| `P0003` | Value Box Chapina | 550 |
| `P0004` | Premium Box Chapina | 675 |

```sql
INSERT INTO "Productos" ("SKU","Producto","Precio") VALUES
  ('P0003','Value Box Chapina',550),
  ('P0004','Premium Box Chapina',675)
ON CONFLICT ("SKU") DO NOTHING;
```

### Recetas (pesos default editables al registrar; recados = 1 unidad → peso 1.0)

**Value Box Chapina — `P0003` — Q550:**

| Componente (etiqueta) | SKU | Peso (lb) | Cant |
|---|---|---|---|
| Carne para bistec | 20004 | 1.5 | 1 |
| Carne para cocer | 30005 | 1.5 | 1 |
| Carne para guisar | 30008 | 1.5 | 1 |
| Molida 80/20 | 30011 | 2.0 | 1 |
| Pollo entero | 50002 | 5.0 | 1 |
| Recado de pepián | 30032 | 1.0 | 1 |
| Recado de jocón | 30035 | 1.0 | 1 |

**Premium Box Chapina — `P0004` — Q675:**

| Componente (etiqueta) | SKU | Peso (lb) | Cant |
|---|---|---|---|
| Lomito Steak | 10003 | 1.5 | 1 |
| Manita de Rochoy | 10010 | 1.5 | 1 |
| Bolovique | 10001 | 1.5 | 1 |
| Molida de puyaso | 10004 | 2.0 | 1 |
| Pollo entero | 50002 | 5.0 | 1 |
| Recado de pepián | 30032 | 1.0 | 1 |
| Recado de jocón | 30035 | 1.0 | 1 |

> "Recado de pepián" = **Recado de Pepián Colorado (30032)**. "Lomito Steak" =
> **Lomito Porcionado (10003)**, el mismo corte que usa la Premium Box actual.

### UI

Agregar 2 botones en el expander "🎁 Agregar Promoción", organizados 2×2 (cajas actuales
arriba, Chapinas abajo). El editor de pesos, el guardado al carrito y el cálculo son
genéricos (leen `BUNDLE_CONFIGS`) y **no cambian**.

## Parte 2 — Mensaje de cobro

### Módulo `mensajes.py`

Función pura, sin dependencias de Streamlit ni de BD, reutilizable y testeable:

```python
DATOS_BANCARIOS = {
    "banco": "Banrural",
    "tipo": "Cuenta monetaria",
    "numero": "3256009530",
    "nombre": "PRODECA",
}

def generar_mensaje_cobro(nombre, total, metodo_pago, titulo="Doña", link_tarjeta=""):
    ...  # devuelve str
```

### Reglas de contenido

- Saludo: `Buen día {titulo} {Nombre},` donde `titulo ∈ {Doña, Don}`.
- Total: `GTQ {total:,.2f}`.
- Bloque de pago según método:
  - **Transferencia:** datos de `DATOS_BANCARIOS` + petición de comprobante.
  - **Tarjeta:** el `link_tarjeta` si se proporcionó (si no, una nota de que se enviará) +
    petición de comprobante.
  - **Efectivo:** sin bloque de pago ni petición de comprobante; cierre simple.

### Integración UI

Helper en cada página que muestra: selector **Doña/Don**, campo de **link** (solo si
Tarjeta) y el texto resultante en `st.code(...)` (botón de copiar de un clic).

- `pages/1_Registro_de_Detalles.py`: usa nombre del cliente, total del pedido en pantalla y
  `metodo_pago` seleccionado. Visible cuando hay cliente y líneas.
- `pages/2_Consultar_Detalle.py`: usa `cliente_nombre`, `pedido["Total"]` y el método de pago
  seleccionado (`nuevo_pago`).

## Pruebas

`tests/test_mensajes.py` cubre `generar_mensaje_cobro` para transferencia (incluye datos de
Banrural), tarjeta (con y sin link), efectivo (sin bloque ni comprobante) y título Don/Doña.
Las cajas son solo datos; no llevan test automatizado.

## Fuera de alcance

- Migrar bundles a una tabla en BD.
- Envío automático del mensaje por WhatsApp/API (es copiar-pegar manual).
- Cambios a las cajas actuales (no se tocan).
