# Generación de links de pago QPayPro para cobro por WhatsApp

> **Estado:** diseño aprobado, pendiente de plan de implementación.
> **Fecha:** 2026-07-03.
> **Contexto del ERP:** ver `CONTEXTO_ACTUAL_ERP.md`. App interna Streamlit + Python +
> PostgreSQL/Supabase, hosteada en **Streamlit Cloud** con el **repositorio público en GitHub**.

## 1. Problema y objetivo

Hoy, para cobrar con tarjeta, el operador entra manualmente al panel web de QPayPro, crea un
link de pago, lo copia y lo pega en el mensaje de cobro que envía por WhatsApp. Ese link es un
recurso que crea el panel (formato `https://payments.qpaypro.com/checkout/{código}/{id}`).

El ERP ya tiene un módulo de "mensaje de cobro" ([mensajes.py](../../../mensajes.py),
[ui_mensajes.py](../../../ui_mensajes.py)) que, cuando el método de pago es "Tarjeta", muestra
un campo de texto donde el operador **pega el link a mano**
([ui_mensajes.py:39](../../../ui_mensajes.py)).

**Objetivo:** que el ERP genere ese link automáticamente vía la API de QPayPro y lo inserte solo
en el mensaje, eliminando el paso manual del panel.

## 2. Alcance

### Dentro (v1)
- Un módulo cliente de la API de QPayPro que genera un link de pago alojado a partir de los datos
  de un pedido (monto y datos del cliente).
- Un botón "Generar link de pago" en la sección de mensaje de cobro (solo cuando el método es
  "Tarjeta") que llama a la API y rellena el link en el mensaje.
- Manejo de errores que nunca tumba la página y deja el campo manual como respaldo.
- Configuración de credenciales y entorno (sandbox/producción) vía secrets.
- Pruebas unitarias del cliente.
- **Verificación en sandbox** de si la página de pago alojada que genera la API ofrece el
  formulario de **facturación electrónica (FEL)** para que el cliente ingrese sus datos, tal
  como hoy sucede con los links del panel (ver §3.5).

### Fuera (v1) — explícitamente no se hace
- **Conciliación automática de pagos** (marcar el pedido como Pagado cuando el cliente paga).
  Requiere recibir callbacks/webhooks de QPayPro; el ERP no está diseñado para exponer endpoints.
  La confirmación de pago sigue siendo manual, como hoy.
- **Emisión de FEL desde el ERP vía la API `QpayFel`** (comercio factura por transacción con
  `nit_cui`/`email`). Es un flujo distinto al actual (el cliente ya no ingresaría sus propios
  datos) y queda fuera de v1. Ver §3.5.
- Consultar estado del pago desde el ERP (`get_transaction_detail`).
- Persistir el token o el link en la base de datos.
- Página dedicada de "cobros sueltos" sin pedido (enfoque C descartado para v1).
- Reproducir el formato exacto de URL del panel (no existe endpoint público que lo genere).

## 3. Realidad técnica que condiciona el diseño

1. **El link del ERP se verá distinto al del panel.** El endpoint
   `POST /checkout/register_transaction_store` devuelve un token, y el link final es
   `{base}/checkout/store?token={token}`. Funciona igual (página de pago alojada por QPayPro que
   cobra el monto indicado), pero la URL tiene otro formato. En la documentación de QPayPro
   disponible no existe un endpoint que reproduzca el formato `/checkout/{código}/{id}` del panel.

2. **Streamlit re-ejecuta el script en cada interacción.** Por eso la generación del link debe
   dispararse con una **acción explícita (botón)**, no automáticamente al renderizar, para no
   crear un token nuevo de QPayPro en cada rerun. El resultado se guarda en `st.session_state`.

3. **Repo público + Streamlit Cloud.** Las credenciales de API **no pueden vivir en el repo**.
   Van en secrets (ver §6). `.streamlit/secrets.toml` ya está en `.gitignore` y no está trackeado.

4. **Forma de la respuesta de la API parcialmente desconocida.** La documentación no detalla con
   exactitud en qué campo viene el token de `register_transaction_store`. Por eso se construye con
   toggle de sandbox y la primera prueba real contra sandbox confirma el parsing antes de producción
   (ver §5 y §8).

### 3.5 Facturación electrónica (FEL): comportamiento a verificar
Hoy el operador, al crear un link en el panel, habilita la FEL para que **el propio cliente**
ingrese sus datos de facturación en la página de pago y se genere la factura automáticamente.

La documentación de `register_transaction_store` **no expone un parámetro** para habilitar esa
FEL. Hay dos hipótesis y no se puede saber cuál aplica sin probar:
1. La página alojada **hereda** la configuración FEL del comercio (si la cuenta tiene QpayFel
   activo, el formulario de facturación aparece solo en todos los links). — Plausible, sin confirmar.
2. El switch es **por-link y solo del panel**, y los links de la API no traen FEL.

**Decisión (acordada):** se construye la generación del link y se **verifica empíricamente en
sandbox** si la página alojada ofrece el formulario de facturación. Según el resultado:
- Si **sí** aparece (hipótesis 1): objetivo cumplido, sin trabajo extra.
- Si **no** aparece: es un hallazgo, no un fracaso del diseño. Se documenta y se decide en una
  fase posterior (p. ej. preguntar a QPayPro por un parámetro no documentado, o evaluar emitir la
  FEL con la API `QpayFel` del lado del comercio — fuera de v1). Mientras tanto, para los pedidos
  que requieran factura, el operador puede seguir creando el link en el panel como hoy.

#### Hallazgos de la prueba en sandbox (2026-07-03)
Prueba real contra `sandboxpayments.qpaypro.com` con las credenciales de sandbox de la doc:
- ✅ **Generación de link: funciona.** Tras corregir los campos requeridos (ver abajo), la API
  devuelve HTTP 200 con `{"estado":"success","data":{"token":"..."}}`. El token está en
  `data.token` (confirmado; el extractor ya lo maneja).
- ✅ **Campos requeridos no documentados:** la API exige además `x_url_cancel`, `http_origin`,
  `x_company`, `x_address`, `x_city`, `x_state`, `x_zip`, `taxes`, `origen`. Ya incorporados al
  payload (con `http_origin` y `url_retorno` configurables).
- ⚠️ **FEL: sin resolver, requiere acción externa.** El HTML de la página alojada trae un flag
  `"facturar":false`. No se hereda solo. Se probaron ~11 nombres de parámetro candidatos
  (`facturar`, `x_fel`, `facturacion`, etc.) con valores `true`/`"si"`/`1`; **ninguno** activó el
  flag. Conclusión: o no existe un parámetro público, o el comercio de prueba de sandbox no tiene
  QpayFel activo (por lo que `facturar` no puede volverse `true` con esas credenciales). No es
  distinguible desde sandbox. **Siguiente paso:** confirmar con QPayPro si `register_transaction_store`
  respeta la FEL (parámetro o herencia de la cuenta), y/o probar con credenciales de producción
  una vez que la cuenta tenga QpayFel activo.

## 4. Arquitectura

Se sigue el patrón ya establecido por `mensajes.py` (lógica pura, sin Streamlit) +
`ui_mensajes.py` (capa de UI), para mantener la lógica testeable de forma aislada.

```
Datos del pedido (nombre, teléfono, correo, total, ID_Pedido)
        │
        ▼
qpaypro.py
  ├── construir_payload(datos, config)   → dict  (función pura, testeable sin red)
  └── generar_link_pago(datos, config)   → ResultadoLink  (hace el POST, parsea, arma URL)
        │
        ▼
ui_mensajes.py  (botón "Generar link de pago", guarda en session_state)
        │
        ▼
mensajes.generar_mensaje_cobro(..., link_tarjeta=url)  → texto para WhatsApp (sin cambios)
```

### 4.1 Módulo nuevo: `qpaypro.py`
Sin dependencias de Streamlit ni de la base de datos.

- **`construir_payload(datos_pedido, config) -> dict`** — función pura. Arma el cuerpo del
  request a partir de:
  - `x_login`, `x_api_key` ← `config` (secrets).
  - `x_amount` ← total del pedido, formateado como string con 2 decimales.
  - `x_currency_code` ← `"GTQ"`.
  - `x_first_name` / `x_last_name` ← nombre del cliente. Se separa en el primer espacio; si no
    hay apellido, `x_last_name` toma un valor de relleno (p. ej. `"-"`) porque la API lo exige.
  - `x_phone` ← teléfono del cliente (PK en `Clientes`), sanitizado a solo dígitos.
  - `x_email` ← correo del cliente si existe; si no, un correo de relleno configurable
    (p. ej. `cf@grassfedgt.com`).
  - `x_description` ← `"{nombre} # {ID_Pedido}"` — replica la convención que el operador usa
    hoy en el panel (`NOMBRE # PEDIDO`). Si aún no hay `ID_Pedido`, se omite el sufijo.
  - `x_invoice_num` ← `ID_Pedido` como string, si está disponible.
  - `products` ← una sola línea con el arreglo JSON escapado que exige la API, usando el nombre
    de producto que el operador usa hoy: `"Caja surtida de carne de pastoreo"`
    (`[["Caja surtida de carne de pastoreo","{total}","","1","0","1"]]`). El nombre del producto
    es configurable. Se cubre con test por su formato delicado.
  - `store_type` ← `"hostedpage"`.
  - `x_url_success` / `x_url_error` / `x_url_cancel` ← configurables; por defecto vacíos (QPayPro
    usa las URLs configuradas en el comercio).

- **`generar_link_pago(datos_pedido, config) -> ResultadoLink`** — hace `POST` al endpoint
  `register_transaction_store` de la base correspondiente al entorno, con
  `Content-Type: application/json`. Lee el token de la respuesta y devuelve
  `{base}/checkout/store?token={token}`.
  - Devuelve un resultado explícito (p. ej. un dataclass/dict `ResultadoLink` con
    `ok: bool`, `url: str | None`, `error: str | None`). **Nunca lanza excepción hacia la UI**:
    errores de red, timeout, status != 2xx o respuesta sin token se traducen en `ok=False` con un
    mensaje claro.
  - Timeout explícito en la llamada HTTP.

### 4.2 Entornos (URLs base)
Seleccionadas por `config["entorno"]`:

| Entorno | Base de pagos | Endpoint token | Link final |
|---|---|---|---|
| `sandbox` | `https://api-sandboxpayments.qpaypro.com` | `.../checkout/register_transaction_store` | `https://sandboxpayments.qpaypro.com/checkout/store?token=...` |
| `produccion` | `https://api-payments.qpaypro.com` | `.../checkout/register_transaction_store` | `https://payments.qpaypro.com/checkout/store?token=...` |

> Nota: el host que crea el token (`api-...`) y el host del link final (`...payments`) son
> distintos; ambos se derivan del entorno.

### 4.3 Integración en `ui_mensajes.py`
Dentro de `render_seccion_mensaje_cobro`, en la rama `metodo_pago == "Tarjeta"`:
1. Botón **"Generar link de pago"**.
2. Al pulsarlo: llamar a `generar_link_pago` con los datos del pedido y la config de secrets.
   - Si `ok`: guardar `url` en `st.session_state[f"{key_prefix}_link_generado"]` y usarla como
     `link_tarjeta`.
   - Si falla: `st.error(resultado.error)` y mantener el campo de texto manual para pegar un link
     del panel como respaldo.
3. El campo de texto manual se conserva siempre (respaldo / override).
4. `mensajes.generar_mensaje_cobro` **no cambia**: ya sabe insertar el link vía `link_tarjeta`.

La firma de `render_seccion_mensaje_cobro` puede necesitar datos adicionales del cliente
(teléfono, correo, ID del pedido) que hoy no recibe. Se ampliará de forma retrocompatible.

## 5. Flujo de datos (camino feliz)
1. El operador arma/consulta un pedido con método "Tarjeta".
2. Abre "📩 Mensaje de cobro" y pulsa "Generar link de pago".
3. `qpaypro.generar_link_pago` hace POST a QPayPro → token → URL.
4. La URL se inserta en el mensaje de cobro.
5. El operador copia el mensaje completo y lo pega en WhatsApp.
6. (Fuera del ERP) El cliente paga en la página alojada de QPayPro.
7. (Manual, como hoy) El operador confirma el pago y marca el pedido como Pagado.

## 6. Configuración y secrets

En `.streamlit/secrets.toml` (local, ya ignorado por git) **y** en Streamlit Cloud →
Settings → Secrets (para la app desplegada):

```toml
[qpaypro]
entorno = "sandbox"          # "sandbox" | "produccion"
x_login = "visanetgt_qpay"   # sandbox de ejemplo; reemplazar en producción
x_api_key = "88888888888"    # sandbox de ejemplo; reemplazar en producción
email_relleno = "cf@grassfedgt.com"
```

- **Nunca** se commitea una llave. El repo es público.
- Las credenciales de API de producción se obtienen del panel de QPayPro (sección de
  integraciones).
- Arrancar en `sandbox` para validar la integración; luego cambiar a `produccion`.

## 7. Manejo de errores
- **Sin sección `[qpaypro]` en secrets:** el botón informa que falta configurar credenciales; el
  campo manual sigue disponible.
- **Error de red / timeout / status != 2xx / respuesta sin token:** `st.error` con mensaje claro;
  no se rompe la página; el operador puede pegar un link del panel manualmente.
- La UI nunca recibe una excepción sin controlar desde `qpaypro.py`.

## 8. Pruebas
Nuevo `tests/test_qpaypro.py`, siguiendo el patrón de `tests/test_mensajes.py` (funciones puras,
sin red real):

- **`construir_payload`:**
  - Mapeo correcto de monto (formato 2 decimales), moneda `GTQ`, `store_type` `hostedpage`.
  - Separación de nombre en `x_first_name` / `x_last_name` (con y sin apellido).
  - Sanitización del teléfono a solo dígitos.
  - `x_email` de relleno cuando el cliente no tiene correo.
  - Formato del arreglo `products` (JSON escapado) correcto.
  - Selección de URLs base según `entorno`.
- **`generar_link_pago`** (con `requests.post` mockeado):
  - Éxito: respuesta con token → `ok=True`, `url` bien formada para el entorno.
  - Status de error (p. ej. 4xx/5xx) → `ok=False`.
  - Excepción de red / timeout → `ok=False`.
  - Respuesta 2xx sin token → `ok=False`.

> El parsing exacto del token se ajustará tras la primera prueba real contra sandbox (§3.4); los
> tests se escriben contra la forma esperada y se corrigen si la respuesta real difiere.

## 9. Dependencias
- `requests` para el POST. Streamlit ya lo trae de forma transitiva, pero se añade explícito a
  `requirements.txt` para dejar la dependencia declarada.

## 10. Impacto en archivos
| Archivo | Cambio |
|---|---|
| `qpaypro.py` | **Nuevo.** Cliente de API (payload puro + generación de link). |
| `ui_mensajes.py` | Botón "Generar link de pago" + estado en `session_state`; firma ampliada. |
| Páginas que usan `render_seccion_mensaje_cobro` | Pasar los datos extra del cliente/pedido. |
| `.streamlit/secrets.toml` | Sección `[qpaypro]` (local, no se commitea). |
| `requirements.txt` | Añadir `requests`. |
| `tests/test_qpaypro.py` | **Nuevo.** Pruebas del cliente. |
| Streamlit Cloud → Secrets | Sección `[qpaypro]` en la app desplegada. |

Sin cambios en la base de datos.

## 11. Preguntas abiertas / a resolver en implementación
1. ~~Forma exacta de la respuesta de `register_transaction_store`~~ — **resuelto (2026-07-03):**
   token en `data.token`. Ver §3.5.
2. **FEL (bloqueante para reemplazar el panel):** la prueba en sandbox mostró `"facturar":false`
   y ningún parámetro candidato lo activó (§3.5). Falta confirmar con QPayPro si el endpoint
   respeta la FEL (parámetro o herencia de cuenta) y/o probar en producción con QpayFel activo.
3. Qué páginas exactas montan `render_seccion_mensaje_cobro` y qué datos del cliente
   (teléfono/correo/ID) tienen disponibles en cada una.
4. Valor del método de pago a registrar cuando se usa link: hoy la UI usa "Tarjeta"; existe el
   enum `Pagos = 'Link'` sin uso. Decisión menor, se resuelve en implementación (v1 no cambia la
   BD, así que no bloquea).
