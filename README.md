# FarmaExpress - Sistema Integral de Gestión Farmacéutica

**Proyecto Integrador de Aprendizaje (PIA) · Componentes de Lógica de Negocio · Equipo 10**

- 🌐 **Aplicación Web en Producción (Render):** [https://pia-logicadenegocio-eq10.onrender.com](https://pia-logicadenegocio-eq10.onrender.com)
- 📄 **Documentación Interactiva Swagger / OpenAPI (`/docs`):** [https://pia-logicadenegocio-eq10.onrender.com/docs](https://pia-logicadenegocio-eq10.onrender.com/docs)

---

## 1. Descripción del Proyecto y Caso de Negocio

**FarmaExpress** es una empresa del giro farmacéutico dedicada a la venta de medicamentos y artículos de cuidado personal a través de múltiples sucursales (`SUC-01 Sucursal Centro`, `SUC-02 Sucursal San Nicolás`, `SUC-03 Sucursal San Pedro`).

Este sistema resuelve la problemática documentada en el **BRD**, las **17 User Stories con Gherkin**, el **BPMN**, el **Glosario de Dominio (43 términos)** y los **7 ADRs** del equipo:
1. **Control de ventas seguro (`CU-01`, `CU-04`):** Impide vender productos sin existencia (`BR-01`), caducados (`BR-02`) o pertenecientes a lotes retirados (`BR-03`).
2. **Validación de medicamentos con requisitos especiales (`CU-02`):** Identifica antibióticos y medicamentos controlados (`BR-04`) y exige la autorización del **Responsable de Farmacia** antes de cobrar (`BR-05`).
3. **Gestión de sustituciones (`CU-03`):** Permite solicitar alternativas cuando un producto no tiene stock (`US-07`), validarlas por el Responsable de Farmacia (`BR-08`, `US-08`) y agregarlas automáticamente a la venta cuando el cliente acepta (`Secuencia 2`).
4. **Control de lotes, caducidades y recepción en Almacén (`CU-05`):** Registra entradas con lote y caducidad (`BR-06`, `BR-15`, `US-14`), detecta lotes próximos a caducar según la política de la empresa (`BR-11`, `BR-12`, `US-05`) y bloquea lotes retirados (`US-06`, `US-15`).
5. **Control de diferencias de inventario físico vs registrado (`US-10`):** Almacén registra discrepancias de conteo físico (`BR-13`, `RF-14`), se prohíben modificaciones directas del cajero (`BR-14`) y todo ajuste requiere revisión autorizada y auditable (`RF-15`, `RNF-08`).
6. **Detección de existencia baja y resurtido manual por Compras (`US-11`, `US-12`):** Detecta automáticamente cuando la existencia de un producto cae por debajo del nivel mínimo en su sucursal (`BR-09`) y notifica a **Compras** para su análisis previo, sin generar compras automáticas (`BR-10`).
7. **Visibilidad entre sucursales e indicadores ejecutivos (`US-13`, `US-16`):** Permite consultar existencias entre sucursales (`BR-16`, `REP-05`) y ofrece a **Administración** los 5 indicadores (`IND-01` a `IND-05`) y 7 reportes consolidados (`REP-01` a `REP-07`).

---

## 2. Arquitectura y Patrones Implementados

El proyecto aplica **Clean Architecture** y **Domain-Driven Design (DDD)** separados en 4 capas:

- **Dominio (`src/domain.py`):**
  - **5 Aggregates principales (`ADR-002`, `Mapa de dominio.png`):** `Producto` (Catálogo), `InventarioDeProducto` (con entidad `Lote`), `Venta` (con entidad `LineaDeVenta`), `SolicitudDeSustitucion` y `RecepcionDeMercancia` (con `LineaDeRecepcion`), además de las entidades de control `DiferenciaDeInventario` y `SolicitudDeResurtido`.
  - **Value Objects:** `Dinero`, `Cantidad`, `NumeroDeLote`, `FechaDeCaducidad`, `NivelMinimo`, `RequisitoEspecial`, `EstadoDeValidacion`, `DecisionDeFarmacia`, `DecisionDelCliente`, `ResultadoDeOperacion`, `PoliticaFarmaExpress`.
  - **Patrón Specification (`ADR-006`):** `Specification` componible (`&`, `|`, `~`), `ReglaDeVendibilidad`, `LoteNoCaducado`, `LoteNoRetirado`, `LoteConExistenciaSuficiente`, `LoteProximoACaducarSpec`, `InventarioBajoMinimoSpec`, `VentaListaParaCobroSpec`.
  - **Patrón State Machine:** `MaquinaEstadoVenta`, `MaquinaEstadoLote`, `MaquinaEstadoValidacion`, `MaquinaEstadoSustitucion`, `MaquinaEstadoDiferencia`, `MaquinaEstadoResurtido`.
  - **Eventos de Dominio:** `VentaCompletada`, `VentaRechazada`, `ExistenciaBajaDetectada`, `MercanciaRecibida`, `SustitucionResuelta`.
- **Aplicación (`src/application.py`):**
  - **Service Layer y CQRS básico (`ADR-003`):** Servicios de comando por caso de uso y servicios de consulta (`Query`) desacoplados mediante puertos (`Protocol`).
  - **Unit of Work y orden de cobro seguro (`ADR-004`, `Secuencia 1`):** En `CompletarVentaService`, primero se verifican requisitos y disponibilidad, luego se cobra en la pasarela, y solo si el pago es aceptado se descuenta el inventario y se confirma la transacción.
- **Infraestructura (`src/infrastructure.py`):**
  - Repositorios en memoria (`ADR-005`), simulador de pasarela de pagos, unidad de trabajo y persistencia de bitácora de auditoría con **SQLAlchemy** (`SQLite` / `PostgreSQL`).
- **API REST e Interfaz Web (`src/api.py` + `src/static/`):**
  - Endpoints REST con **FastAPI**, validación con **Pydantic v2**, documentación de errores en **Swagger UI (`403`, `404`, `409`, `422`)** e interfaz gráfica en **HTML y CSS** clara y entendible para los 5 roles del negocio.

---

## 3. Matriz de Trazabilidad Obligatoria (BRD · User Stories · BPMN · ADRs · Código · Pruebas)

| Regla / Req. | User Story / BPMN | ADR / Patrón | Modelo de Dominio (`src/domain.py`) | Servicio / Endpoint (`src/application.py` / `src/api.py`) | Pruebas Automatizadas (`tests/`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BR-01 / RF-02** (Existencia suficiente) | `US-01`, `US-02` | `ADR-001`, `ADR-002` / Specification | `InventarioDeProducto.verificar_venta`, `LoteConExistenciaSuficiente` | `RegistrarProductoEnVentaService`, `CompletarVentaService` / `POST /orders/{id}/lineas` | `test_domain.py`, `test_application.py` |
| **BR-02 / RF-03** (Bloquear caducados) | `US-04` | `ADR-006` / Specification | `FechaDeCaducidad.fue_alcanzada`, `LoteNoCaducado` | `RegistrarProductoEnVentaService`, `CompletarVentaService` | `test_lote_caducado_no_es_vendible` |
| **BR-03 / RF-04** (Bloquear lotes retirados) | `US-06`, `US-15` | `ADR-006` / State Machine | `Lote.retirar`, `MaquinaEstadoLote`, `LoteNoRetirado` | `RetirarLoteService` / `POST /lotes/retirar` | `test_lote_retirado_no_es_vendible`, `test_api.py` |
| **BR-04, BR-05 / RF-05, RF-06** (Requisitos especiales y rol Farmacia) | `US-03` | `ADR-001`, `ADR-003` / State Machine + Specification | `Producto.requiere_validacion_especial`, `Venta.resolver_validacion`, `VentaListaParaCobroSpec` | `ResolverValidacionEspecialService` / `POST /orders/{id}/validaciones` | `test_venta_calcula_total_y_valida_requisitos_especiales`, `test_api_validacion_especial_y_restriccion_rol_403` |
| **BR-06, BR-07 / RF-07** (Descuento automático tras venta) | `US-09`, `US-17` | `ADR-002`, `ADR-004` / Unit of Work | `InventarioDeProducto.verificar_y_descontar`, `Venta.completar` | `CompletarVentaService` / `POST /orders/{id}/completar` | `test_completar_venta_exitososa`, `test_completar_venta_pago_rechazado_no_descuenta_inventario` |
| **BR-08 / RF-16** (Validar sustituciones) | `US-07`, `US-08` | `ADR-002`, `ADR-004` / State Machine | `SolicitudDeSustitucion`, `MaquinaEstadoSustitucion`, `DecisionDeFarmacia` | `SolicitarSustitucionService`, `ValidarSustitucionService`, `RegistrarDecisionDelClienteService` / `/sustituciones` | `test_flujo_completo_sustitucion_cu03_y_recepcion_cu05` |
| **BR-09, BR-10 / RF-11, RF-12** (Existencia baja y análisis manual de Compras) | `US-11`, `US-12` | `ADR-001`, `ADR-004` / Domain Events + State Machine | `NivelMinimo`, `InventarioBajoMinimoSpec`, `ExistenciaBajaDetectada`, `SolicitudDeResurtido` | `AnalizarResurtidoService` / `GET /resurtidos`, `POST /resurtidos/{id}/analizar` | `test_inventario_descuenta_correctamente_y_detecta_minimo`, `test_diferencia_inventario_y_resurtido_sin_compra_automatica` |
| **BR-11, BR-12 / RF-13** (Próximos a caducar y política configurable) | `US-05` | `ADR-006` / Specification | `LoteProximoACaducarSpec`, `PoliticaFarmaExpress` | `ConsultarIndicadoresConsolidadosQuery` / `POST /politicas/caducidad` | `test_specifications_componibles_y_proximidad_caducidad` |
| **BR-13, BR-14 / RF-14, RF-15** (Diferencias de inventario y bloqueo al cajero) | `US-10` | `ADR-005` / State Machine | `DiferenciaDeInventario`, `MaquinaEstadoDiferencia`, `InventarioDeProducto.aplicar_ajuste_autorizado` | `RegistrarDiferenciaInventarioService`, `RevisarDiferenciaInventarioService` / `/diferencias-inventario` | `test_diferencia_inventario_y_resurtido_sin_compra_automatica`, `test_api.py` |
| **BR-15 / RF-09, RF-10** (Recepción en Almacén con lote y caducidad) | `US-14` | `ADR-002`, `ADR-004` | `RecepcionDeMercancia`, `LineaDeRecepcion`, `InventarioDeProducto.registrar_entrada` | `RegistrarRecepcionDeMercanciaService` / `POST /recepciones` | `test_flujo_completo_sustitucion_cu03_y_recepcion_cu05` |
| **BR-16 / RF-08, RF-17, RF-18** (Visibilidad entre sucursales e indicadores) | `US-13`, `US-16` | `ADR-003`, `ADR-007` / CQRS Query | `InventarioDeProducto` por sucursal | `ConsultarDisponibilidadPorSucursalQuery`, `ConsultarIndicadoresConsolidadosQuery` / `/disponibilidad-sucursales/{id}`, `/indicadores` | `test_diferencias_retiro_resurtido_e_indicadores`, `test_api.py` |

---

## 4. Instrucciones de Instalación y Ejecución Local

### Clonar el repositorio y activar el entorno virtual
```powershell
git clone https://github.com/Prixel336k/PIA-Logica-de-negocio
cd PIA-EQ10
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Instalar dependencias
```powershell
pip install -r requirements.txt
```

### Ejecutar la aplicación y la interfaz web
```powershell
uvicorn src.api:app --reload
```
Una vez encendida, abre en tu navegador:
- **Interfaz Gráfica de Usuario (HTML/CSS):** [http://localhost:8000/](http://localhost:8000/)
- **Documentación Interactiva (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Documentación Alternativa (Redoc):** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 5. Pruebas Automatizadas y Cobertura (>88%)

Para ejecutar toda la suite de pruebas unitarias y de integración junto con el reporte de cobertura:
```powershell
python -m pytest --cov=src --cov-report=term-missing
```

---

## 6. Ejecución con Docker Compose (DB + App + Tests)

El archivo `docker-compose.yml` incluye los 3 contenedores solicitados en la rúbrica (`db` PostgreSQL, `farmaexpress-api` y `tests`):

```powershell
# Levantar Base de Datos + Aplicación + Ejecutar Pruebas
docker compose up --build

# Ejecutar únicamente el contenedor de pruebas automatizadas
docker compose run --rm tests
```

---

## 7. Despliegue en Render (Producción)

- **URL Pública de la Interfaz Web:** [https://pia-logicadenegocio-eq10.onrender.com](https://pia-logicadenegocio-eq10.onrender.com)
- **URL Pública de Swagger UI (`/docs`):** [https://pia-logicadenegocio-eq10.onrender.com/docs](https://pia-logicadenegocio-eq10.onrender.com/docs)

El proyecto está desplegado directamente en **Render** usando el `Dockerfile` incluido (el cual escucha dinámicamente en `${PORT:-8000}`):

1. Sube tus cambios a tu repositorio de GitHub (`git add . && git commit -m "Implementacion completa FarmaExpress PIA" && git push`).
2. Entra a [https://dashboard.render.com/](https://dashboard.render.com/) y haz clic en **New +** -> **Web Service**.
3. Selecciona tu repositorio de GitHub (`PIA-Logica-de-negocio`).
4. En **Runtime / Environment**, selecciona **Docker** (Render detectará automáticamente el `Dockerfile` de la raíz).
5. En **Instance Type**, selecciona **Free** y haz clic en **Create Web Service**.
6. Al finalizar el build, tu URL pública mostrará:
   - En `/` la **Interfaz Web de FarmaExpress (HTML/CSS)**.
   - En `/docs` el **Swagger UI / OpenAPI activo en producción**.

---

## 8. Estructura del Repositorio

```text
PIA-EQ10/
├── .github/workflows/ci.yml   # Pipeline de integración continua (CI) en GitHub Actions
├── docs/                      # Artefactos de análisis (BRD, BPMN, US, Glosario) y Arquitectura (ADRs, UML, API.md)
├── src/                       # Código fuente (Clean Architecture + DDD)
│   ├── static/                # Interfaz de usuario entendible en HTML y CSS
│   │   ├── index.html
│   │   └── styles.css
│   ├── domain.py              # Aggregates, Value Objects, Specifications, State Machines y Eventos
│   ├── application.py         # Casos de uso (Commands), Queries (CQRS) y Puertos
│   ├── infrastructure.py      # Repositorios en memoria, adaptadores y auditoría SQLAlchemy
│   └── api.py                 # Endpoints FastAPI, errores documentados en Swagger y servidor web
├── tests/                     # Pruebas automatizadas unitarias y de integración (pytest)
│   ├── test_domain.py
│   ├── test_application.py
│   └── test_api.py
├── .env.example               # Variables de entorno de ejemplo (sin secretos reales)
├── Dockerfile                 # Imagen Docker lista para local y Render ($PORT)
├── docker-compose.yml         # Orquestación reproducible para DB + App + Tests
├── requirements.txt           # Dependencias del proyecto
└── README.md                  # Documentación técnica, matriz de trazabilidad y guía de despliegue
```
