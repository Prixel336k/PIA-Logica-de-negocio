# Documentación del Contrato API y OpenAPI - FarmaExpress (Equipo 10)

Esta documentación especifica los contratos de interfaz HTTP REST, esquemas de entrada/salida y códigos de estado implementados en **FarmaExpress API**, alineados con el **BRD**, las **17 Historias de Usuario (Gherkin)**, el **BPMN** y los **ADRs (ADR-001 a ADR-007)**.

- **Interfaz Web Interactiva en Producción (Render):** `https://pia-logicadenegocio-eq10.onrender.com/` (Local: `http://localhost:8000/`)
- **Documentación Interactiva Swagger UI (`/docs`):** `https://pia-logicadenegocio-eq10.onrender.com/docs` (Local: `http://localhost:8000/docs`)
- **Especificación OpenAPI JSON:** `https://pia-logicadenegocio-eq10.onrender.com/openapi.json` (Local: `http://localhost:8000/openapi.json`)

---

## Estándar de Errores y Excepciones en Swagger

La API utiliza un patrón unificado de traducción de excepciones del dominio (`ejecutar_operacion_negocio`, `run_action` y `get_venta_or_404`) documentado explícitamente en los esquemas de respuesta (`responses`) de Swagger:

| Código HTTP | Significado en el Dominio de FarmaExpress | Ejemplo de Respuesta (`ErrorResponse`) |
| :--- | :--- | :--- |
| **403 Forbidden** | Violación de permisos por rol (`RNF-01`, `RNF-07`, `BR-05`, `BR-14` - `UnauthorizedRoleAction`). Ej.: Cajero intentando validar un medicamento especial o modificar existencias de inventario. | `{"detail": "Permiso denegado por regla de negocio: El cajero tiene prohibido modificar o ajustar existencias de inventario directamente (BR-14)."}` |
| **404 Not Found** | El recurso solicitado (`Venta`, `Inventario`, `SolicitudDeSustitucion`, `DiferenciaDeInventario` o `SolicitudDeResurtido`) no existe en el sistema. | `{"detail": "Lo sentimos, la venta solicitada no se encuentra registrada en el sistema."}` |
| **409 Conflict** | Transición inválida en la Máquina de Estados (`InvalidOrderTransition`). Ej.: intentar modificar o volver a cobrar una venta ya `COMPLETADA` o `RECHAZADA`. | `{"detail": "Atención: No se pudo completar la operación debido al estado actual: La venta V-001 ya ha sido completada y no admite más cambios de estado."}` |
| **422 Unprocessable Content** | Violación de reglas de negocio farmacéutico (`BR-01` a `BR-16` / `InvalidDomainData`) o rechazo del procesador de pagos (`ADR-004`). | `{"detail": "Error de validación en las reglas de negocio farmacéutico: Lote no vendible: El lote se encuentra caducado (BR-02)."}` |

---

## Catálogo de Endpoints por Módulo de Negocio

### 1. Ventas y Caja (`CU-01`, `CU-04`, `US-01`, `US-04`, `US-17`)
- `GET /orders`: Lista todas las ventas registradas en el sistema.
- `POST /orders`: Inicia una nueva operación de venta en estado `EN_CAPTURA` (`RF-01`, `US-01`).
- `GET /orders/{venta_id}`: Consulta el detalle de una venta, sus líneas, validaciones y eventos emitidos.
- `POST /orders/{venta_id}/lineas`: Agrega un producto a la venta verificando existencia (`BR-01`), que el lote no esté caducado (`BR-02` / `US-04`) ni retirado (`BR-03`), y detectando automáticamente si requiere validación especial (`BR-04`).
- `POST /orders/{venta_id}/completar`: Ejecuta `CU-04` siguiendo el orden transaccional de `ADR-004`:
  1. Verifica que no existan validaciones especiales pendientes o rechazadas (`BR-04`, `BR-05`).
  2. Verifica disponibilidad y vendibilidad de cada línea (`BR-01`, `BR-02`, `BR-03`).
  3. Procesa el cobro con `ProcesadorDePagos`. Si se envía `?simular_fallo_pago=true`, rechaza la venta y **no descuenta el inventario** (`ADR-004`).
  4. Descuenta el inventario del lote utilizado (`BR-07`, `US-17`), emite `ExistenciaBajaDetectada` si cae por debajo del nivel mínimo (`BR-09`, `US-11`) y marca la venta como `COMPLETADA`.

### 2. Validación Farmacéutica (`CU-02`, `US-03`, `BR-04`, `BR-05`)
- `GET /validaciones-pendientes`: Lista los medicamentos con requisitos especiales que requieren intervención del Responsable de Farmacia.
- `POST /orders/{venta_id}/validaciones`: Permite al **Responsable de Farmacia** aprobar o rechazar el requisito especial (`BR-05`). Si el rol es `cajero`, devuelve `403 Forbidden`.

### 3. Atención y Validación de Sustituciones (`CU-03`, `US-07`, `US-08`, `BR-08`)
- `GET /sustituciones`: Lista todas las solicitudes de sustitución y sus decisiones.
- `GET /productos/{producto_id}/alternativas/{sucursal_id}`: Consulta productos sustitutos que sí cuentan con existencia vendible en la sucursal (`Secuencia 2`).
- `POST /sustituciones`: Registra una solicitud de sustitución ante falta de existencia (`US-07`).
- `POST /sustituciones/{solicitud_id}/validar`: El **Responsable de Farmacia** aprueba o rechaza la alternativa propuesta (`US-08`, `BR-08`).
- `POST /sustituciones/{solicitud_id}/decision-cliente`: Registra si el cliente acepta la alternativa explicada; si acepta, asigna lote automáticamente (`FEFO`) y agrega el producto a la venta en una sola `UnidadDeTrabajo` (`ADR-004`, `Secuencia 2`).

### 4. Inventario, Lotes, Caducidades y Visibilidad entre Sucursales (`US-02`, `US-05`, `US-06`, `US-09`, `US-13`, `US-15`)
- `GET /inventarios/{producto_id}/{sucursal_id}`: Consulta existencia total, existencia vendible, alerta de nivel mínimo y estado de cada lote.
- `GET /inventarios-sucursal/{sucursal_id}`: Lista el inventario completo de todos los productos del catálogo en una sucursal (`US-09`).
- `GET /disponibilidad-sucursales/{producto_id}`: Consulta la disponibilidad en tiempo real de un producto en todas las sucursales de FarmaExpress (`US-13`, `BR-16`, `REP-05`).
- `POST /lotes/retirar`: Permite al **Responsable de Farmacia** bloquear un lote como `RETIRADO` para impedir su venta en futuras operaciones (`US-06`, `BR-03`).

### 5. Almacén: Recepción de Mercancía y Diferencias de Inventario (`CU-05`, `US-10`, `US-14`, `BR-13`, `BR-14`, `BR-15`)
- `GET /recepciones`: Lista las recepciones de mercancía registradas en Almacén.
- `POST /recepciones`: El personal de **Almacén** registra el ingreso de nuevos lotes con fecha de caducidad y cantidad (`CU-05`, `US-14`, `BR-15`). El rol `cajero` es bloqueado con `403 Forbidden` (`BR-14`).
- `GET /diferencias-inventario`: Lista las discrepancias reportadas entre el inventario físico y el registrado (`REP-06`).
- `POST /diferencias-inventario`: El personal de **Almacén** reporta una diferencia encontrada durante el conteo físico (`US-10`, `BR-13`, `RF-14`).
- `POST /diferencias-inventario/{diferencia_id}/revisar`: El **Responsable de Farmacia** o **Administración** revisa el hallazgo y autoriza o rechaza el ajuste auditable sobre el lote (`RF-15`, `RNF-08`).

### 6. Compras y Análisis de Resurtido (`US-11`, `US-12`, `BR-09`, `BR-10`, `RF-11`, `RF-12`)
- `GET /resurtidos`: Consulta las alertas de existencia baja y el estado de las solicitudes de resurtido (`REP-01`, `REP-07`).
- `POST /resurtidos/{resurtido_id}/analizar`: El área de **Compras** registra su decisión manual de solicitar o descartar el abastecimiento, cumpliendo estrictamente `BR-10` (*no generar compras automáticas*).

### 7. Administración, Indicadores Consolidados y Trazabilidad (`US-16`, `BR-12`, `RNF-03`, `RNF-08`)
- `GET /indicadores`: Devuelve los **5 Indicadores de Negocio (`IND-01` a `IND-05`)** y los **Reportes Consolidados (`REP-01` a `REP-07`)** para la toma de decisiones de Administración (`US-16`).
- `POST /politicas/caducidad`: Configura el periodo en días para identificar productos próximos a caducar (`BR-12`, `US-05`).
- `GET /bitacora-eventos`: Consulta el historial de eventos de dominio y alertas publicadas (`RNF-03`, `RNF-08`).
