from pathlib import Path
from typing import Optional, List
from datetime import date, timedelta
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.domain import (
    Dinero,
    Cantidad,
    NumeroDeLote,
    FechaDeCaducidad,
    EstadoDelLote,
    Lote,
    InventarioDeProducto,
    Producto,
    TipoDeProducto,
    RequisitoEspecial,
    Venta,
    EstadoValidacion,
    SolicitudDeSustitucion,
    DiferenciaDeInventario,
    SolicitudDeResurtido,
    PoliticaFarmaExpress,
    RolUsuario,
    DomainException,
    InvalidDomainData,
    InvalidOrderTransition,
    UnauthorizedRoleAction,
)
from src.application import (
    IniciarVentaService,
    RegistrarProductoEnVentaService,
    ResolverValidacionEspecialService,
    SolicitarSustitucionService,
    ValidarSustitucionService,
    RegistrarDecisionDelClienteService,
    CompletarVentaService,
    RegistrarRecepcionDeMercanciaService,
    RetirarLoteService,
    RegistrarDiferenciaInventarioService,
    RevisarDiferenciaInventarioService,
    AnalizarResurtidoService,
    ConsultarDisponibilidadQuery,
    ConsultarDisponibilidadPorSucursalQuery,
    ConsultarAlternativasDisponiblesQuery,
    ConsultarIndicadoresConsolidadosQuery,
)
from src.infrastructure import (
    MemoriaRepositorioDeVentas,
    MemoriaRepositorioDeInventarios,
    MemoriaRepositorioDeProductos,
    MemoriaRepositorioDeSustituciones,
    MemoriaRepositorioDeRecepciones,
    MemoriaRepositorioDeDiferencias,
    MemoriaRepositorioDeResurtidos,
    SimuladorProcesadorDePagos,
    MemoriaUnidadDeTrabajo,
    MemoriaPublicadorDeEventos,
    crear_session_factory,
)


# =====================================================================
# MODELOS DE ERROR Y RESPUESTA PARA SWAGGER / OPENAPI
# =====================================================================
class ErrorResponse(BaseModel):
    detail: str = Field(
        ...,
        description="Descripción clara y entendible del error de negocio, estado o permisos.",
        json_schema_extra={"example": "Error de validación en las reglas de negocio farmacéutico: El lote se encuentra caducado (BR-02)."},
    )


RESPUESTAS_ERROR_SWAGGER = {
    403: {
        "model": ErrorResponse,
        "description": "Acción no autorizada para el rol actual (RNF-01, RNF-07, BR-05, BR-14).",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Permiso denegado por regla de negocio: El cajero tiene prohibido modificar o ajustar existencias de inventario directamente (BR-14)."
                }
            }
        },
    },
    404: {
        "model": ErrorResponse,
        "description": "Recurso no encontrado en el sistema (Venta, Producto, Lote o Solicitud).",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Lo sentimos, la venta solicitada no se encuentra registrada en el sistema."
                }
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflicto con el estado actual en la Máquina de Estados (ej. orden ya completada o rechazada).",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Atención: No se pudo completar la operación debido al estado actual de la venta: Esta venta ya ha sido completada anteriormente."
                }
            }
        },
    },
    422: {
        "model": ErrorResponse,
        "description": "Violación de regla de negocio farmacéutico (BR-01 a BR-16) o datos de dominio inválidos.",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Error de validación en las reglas de negocio farmacéutico: Lote no vendible: El lote se encuentra caducado (BR-02)."
                }
            }
        },
    },
}


# =====================================================================
# CONFIGURACIÓN DE LA APLICACIÓN FASTAPI Y DOCUMENTACIÓN OPENAPI
# =====================================================================
app = FastAPI(
    title="FarmaExpress API",
    version="2.0.0",
    description=(
        "Sistema integral de gestión farmacéutica basado en **DDD, Clean Architecture, Specification y State Machine**.\n\n"
        "Implementa las **16 Reglas de Negocio (BR-01 a BR-16)**, los **18 Requerimientos Funcionales (RF-01 a RF-18)**, "
        "las **17 Historias de Usuario (US-01 a US-17)** y el proceso **BPMN** de FarmaExpress:\n"
        "- **Control de ventas y requisitos especiales** (BR-04, BR-05).\n"
        "- **Bloqueo automático de lotes caducados y retirados** (BR-02, BR-03).\n"
        "- **Gestión de sustituciones autorizadas por farmacia** (CU-03, BR-08).\n"
        "- **Recepción de mercancía y auditoría de diferencias físicas vs registradas** (CU-05, BR-13, BR-14, BR-15).\n"
        "- **Detección de existencia baja y análisis manual de resurtido por Compras** (BR-09, BR-10).\n"
        "- **Visibilidad multisucursal e indicadores ejecutivos consolidados** (BR-16, REP-01..07, IND-01..05)."
    ),
)

# Repositorios y adaptadores compartidos
session_factory = crear_session_factory()
ventas_repo = MemoriaRepositorioDeVentas()
inventarios_repo = MemoriaRepositorioDeInventarios()
productos_repo = MemoriaRepositorioDeProductos()
sustituciones_repo = MemoriaRepositorioDeSustituciones()
recepciones_repo = MemoriaRepositorioDeRecepciones()
diferencias_repo = MemoriaRepositorioDeDiferencias()
resurtidos_repo = MemoriaRepositorioDeResurtidos()
publicador_eventos = MemoriaPublicadorDeEventos(session_factory=session_factory)
politica_actual = {"dias_proximidad_caducidad": 30}

SUCURSALES_FARMAEXPRESS = {
    "SUC-01": "Sucursal Centro (Monterrey)",
    "SUC-02": "Sucursal San Nicolás (Norte)",
    "SUC-03": "Sucursal San Pedro (Sur)",
}

USUARIOS_DEMO = [
    {"id": "CAJ-01", "nombre": "Ana Gómez (Cajera)", "rol": RolUsuario.CAJERO.value, "sucursal_id": "SUC-01"},
    {"id": "FARM-01", "nombre": "Dr. Carlos Ruiz (Responsable de Farmacia)", "rol": RolUsuario.RESPONSABLE_FARMACIA.value, "sucursal_id": "SUC-01"},
    {"id": "ALM-01", "nombre": "Roberto Díaz (Personal de Almacén)", "rol": RolUsuario.ALMACEN.value, "sucursal_id": "SUC-01"},
    {"id": "COMP-01", "nombre": "Laura Méndez (Analista de Compras)", "rol": RolUsuario.COMPRAS.value, "sucursal_id": "SUC-01"},
    {"id": "ADMIN-01", "nombre": "Dirección General (Administración)", "rol": RolUsuario.ADMINISTRACION.value, "sucursal_id": "SUC-01"},
]


# =====================================================================
# PRECARGA DE DATOS INICIALES RICOS PARA DEMOSTRACIÓN DE FARMAEXPRESS
# =====================================================================
def _inicializar_datos_mock():
    ventas_repo.ventas.clear()
    inventarios_repo.inventarios.clear()
    productos_repo.productos.clear()
    sustituciones_repo.sustituciones.clear()
    recepciones_repo.recepciones.clear()
    diferencias_repo.diferencias.clear()
    resurtidos_repo.resurtidos.clear()
    publicador_eventos.eventos_publicados.clear()
    publicador_eventos.alertas_compras.clear()

    hoy = date.today()

    # 1. Catálogo de Productos (Medicamentos con/sin requisito especial y Cuidado Personal)
    catalogo = [
        Producto(
            id="PROD-01",
            nombre="Paracetamol 500mg (Caja con 20 tabletas)",
            tipo=TipoDeProducto.MEDICAMENTO,
            precio=Dinero(Decimal("250.00")),
            requisito=RequisitoEspecial(""),
            sustitutos_ids=["PROD-04"],
            categoria="Analgésico / Antipirético",
        ),
        Producto(
            id="PROD-02",
            nombre="Amoxicilina + Ácido Clavulánico 500mg (Antibiótico)",
            tipo=TipoDeProducto.MEDICAMENTO,
            precio=Dinero(Decimal("320.00")),
            requisito=RequisitoEspecial("Receta médica obligatoria con cédula profesional vigente (BR-04)"),
            sustitutos_ids=["PROD-03"],
            categoria="Antibiótico controlado",
        ),
        Producto(
            id="PROD-03",
            nombre="Azitromicina 500mg (Caja 3 tabletas - Antibiótico)",
            tipo=TipoDeProducto.MEDICAMENTO,
            precio=Dinero(Decimal("290.00")),
            requisito=RequisitoEspecial("Receta médica retenida obligatoria para antibióticos (BR-04)"),
            sustitutos_ids=["PROD-02"],
            categoria="Antibiótico controlado",
        ),
        Producto(
            id="PROD-04",
            nombre="Ibuprofeno 400mg (Caja con 20 cápsulas blandas)",
            tipo=TipoDeProducto.MEDICAMENTO,
            precio=Dinero(Decimal("180.00")),
            requisito=RequisitoEspecial(""),
            sustitutos_ids=["PROD-01"],
            categoria="Analgésico / Antiinflamatorio",
        ),
        Producto(
            id="PROD-05",
            nombre="Gel Dermolimpiador Hidratante 500ml",
            tipo=TipoDeProducto.CUIDADO_PERSONAL,
            precio=Dinero(Decimal("195.00")),
            requisito=RequisitoEspecial(""),
            sustitutos_ids=["PROD-06"],
            categoria="Higiene y Cuidado Personal",
        ),
        Producto(
            id="PROD-06",
            nombre="Protector Solar Dermatológico FPS 50+",
            tipo=TipoDeProducto.CUIDADO_PERSONAL,
            precio=Dinero(Decimal("340.00")),
            requisito=RequisitoEspecial(""),
            sustitutos_ids=["PROD-05"],
            categoria="Cuidado Dermatológico",
        ),
    ]
    for p in catalogo:
        productos_repo.guardar(p)

    # 2. Inventarios por sucursal con escenarios reales (Vigentes, Próximos a caducar, Caducados, Retirados y Existencia Baja)
    # PROD-01 en SUC-01 (LOTE-100 vigente para pruebas base + otro lote en SUC-02 y SUC-03)
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-01",
            sucursal_id="SUC-01",
            nivel_minimo=5,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-100"),
                    caducidad=date(2027, 6, 1),
                    cantidad=Cantidad(20),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-01",
            sucursal_id="SUC-02",
            nivel_minimo=5,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-102"),
                    caducidad=hoy + timedelta(days=180),
                    cantidad=Cantidad(15),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-01",
            sucursal_id="SUC-03",
            nivel_minimo=5,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-103"),
                    caducidad=hoy + timedelta(days=240),
                    cantidad=Cantidad(12),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )

    # PROD-02 (Amoxicilina) en SUC-01: un lote próximo a caducar (en 12 días -> BR-11) y uno normal
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-02",
            sucursal_id="SUC-01",
            nivel_minimo=8,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-PROX-201"),
                    caducidad=hoy + timedelta(days=12),
                    cantidad=Cantidad(6),
                    estado=EstadoDelLote.DISPONIBLE,
                ),
                Lote(
                    numero=NumeroDeLote("LOTE-202"),
                    caducidad=hoy + timedelta(days=120),
                    cantidad=Cantidad(10),
                    estado=EstadoDelLote.DISPONIBLE,
                ),
            ],
        )
    )

    # PROD-03 (Azitromicina) en SUC-01: incluye un lote CADUCADO (BR-02) y un lote vigente con existencia baja (BR-09)
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-03",
            sucursal_id="SUC-01",
            nivel_minimo=10,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-CAD-301"),
                    caducidad=hoy - timedelta(days=15),
                    cantidad=Cantidad(8),
                    estado=EstadoDelLote.DISPONIBLE,
                ),
                Lote(
                    numero=NumeroDeLote("LOTE-302"),
                    caducidad=hoy + timedelta(days=90),
                    cantidad=Cantidad(3),
                    estado=EstadoDelLote.DISPONIBLE,
                ),
            ],
        )
    )

    # PROD-04 (Ibuprofeno - sustituto de PROD-01 y disponible cuando se agota otro analgésico)
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-04",
            sucursal_id="SUC-01",
            nivel_minimo=6,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-401"),
                    caducidad=hoy + timedelta(days=150),
                    cantidad=Cantidad(25),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-04",
            sucursal_id="SUC-02",
            nivel_minimo=6,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-402"),
                    caducidad=hoy + timedelta(days=200),
                    cantidad=Cantidad(18),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )

    # PROD-05 (Gel Dermolimpiador) en SUC-01: incluye un lote RETIRADO (BR-03, US-06, US-15) y un lote disponible
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-05",
            sucursal_id="SUC-01",
            nivel_minimo=5,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-RET-501"),
                    caducidad=hoy + timedelta(days=60),
                    cantidad=Cantidad(14),
                    estado=EstadoDelLote.RETIRADO,
                    motivo_retiro="Alerta de control de calidad del fabricante en empaque (BR-03)",
                    retirado_por="FARM-01",
                    fecha_retiro=hoy - timedelta(days=2),
                ),
                Lote(
                    numero=NumeroDeLote("LOTE-502"),
                    caducidad=hoy + timedelta(days=180),
                    cantidad=Cantidad(9),
                    estado=EstadoDelLote.DISPONIBLE,
                ),
            ],
        )
    )

    # PROD-06 (Protector Solar): SIN EXISTENCIA en SUC-01 (para demostrar BR-01, sustitución US-07 y consulta multisucursal US-13), pero CON STOCK en SUC-02 y SUC-03
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-06",
            sucursal_id="SUC-01",
            nivel_minimo=8,
            lotes=[],
        )
    )
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-06",
            sucursal_id="SUC-02",
            nivel_minimo=8,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-602"),
                    caducidad=hoy + timedelta(days=210),
                    cantidad=Cantidad(16),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-06",
            sucursal_id="SUC-03",
            nivel_minimo=8,
            lotes=[
                Lote(
                    numero=NumeroDeLote("LOTE-603"),
                    caducidad=hoy + timedelta(days=250),
                    cantidad=Cantidad(11),
                    estado=EstadoDelLote.DISPONIBLE,
                )
            ],
        )
    )

    # 3. Ventas iniciales de demostración
    # V-001: Venta en captura lista para cobrarse o agregar líneas (compatibilidad con tests originales)
    venta_1 = Venta(id="V-001", cajero_id="CAJ-01", sucursal_id="SUC-01")
    venta_1.agregar_linea(
        producto_id="PROD-01",
        numero_lote=NumeroDeLote("LOTE-100"),
        cantidad=Cantidad(2),
        precio_unitario=Dinero(Decimal("250.00")),
        requiere_validarcion=False,
        nombre_producto="Paracetamol 500mg (Caja con 20 tabletas)",
    )
    ventas_repo.guardar(venta_1)

    # V-002: Venta con medicamento sujeto a requisito especial PENDIENTE de validación por el Responsable de Farmacia (US-03, BR-04, BR-05)
    venta_2 = Venta(id="V-002", cajero_id="CAJ-01", sucursal_id="SUC-01")
    venta_2.agregar_linea(
        producto_id="PROD-02",
        numero_lote=NumeroDeLote("LOTE-202"),
        cantidad=Cantidad(1),
        precio_unitario=Dinero(Decimal("320.00")),
        requiere_validarcion=True,
        nombre_producto="Amoxicilina + Ácido Clavulánico 500mg (Antibiótico)",
        requisito_descripcion="Receta médica obligatoria con cédula profesional vigente (BR-04)",
    )
    ventas_repo.guardar(venta_2)

    # 4. Solicitud de sustitución inicial (US-07, US-08, BR-08)
    sust_1 = SolicitudDeSustitucion.registrar(
        id="SUST-001",
        venta_id="V-001",
        producto_original="PROD-06",
        cantidad=Cantidad(1),
        motivo="Cliente solicita alternativa para Protector Solar (sin existencia en SUC-01)",
    )
    sustituciones_repo.guardar(sust_1)

    # 5. Diferencia entre inventario físico y registrado reportada por Almacén (US-10, BR-13, RF-14)
    dif_1 = DiferenciaDeInventario(
        id="DIF-001",
        producto_id="PROD-04",
        sucursal_id="SUC-01",
        numero_lote=NumeroDeLote("LOTE-401"),
        cantidad_registrada=Cantidad(25),
        cantidad_fisica=Cantidad(23),
        motivo="Conteo cíclico matutino en estante B-2: se detectaron 2 cajas con blíster dañado separadas en merma",
        reportado_por="ALM-01",
        fecha_reporte=hoy,
    )
    diferencias_repo.guardar(dif_1)

    # 6. Necesidades de resurtido para análisis manual de Compras (US-11, US-12, BR-09, BR-10)
    resurtidos_repo.guardar(
        SolicitudDeResurtido(
            id="RES-001",
            producto_id="PROD-03",
            sucursal_id="SUC-01",
            existencia_actual=3,
            nivel_minimo=10,
            fecha_alerta=hoy,
        )
    )
    resurtidos_repo.guardar(
        SolicitudDeResurtido(
            id="RES-002",
            producto_id="PROD-06",
            sucursal_id="SUC-01",
            existencia_actual=0,
            nivel_minimo=8,
            fecha_alerta=hoy,
        )
    )


_inicializar_datos_mock()


# =====================================================================
# FUNCIONES DE APOYO Y MANEJO UNIFICADO DE EXCEPCIONES HTTP
# =====================================================================
def get_venta_or_404(venta_id: str) -> Venta:
    venta = ventas_repo.obtener_por_id(venta_id)
    if venta is None:
        raise HTTPException(
            status_code=404,
            detail="Lo sentimos, la venta solicitada no se encuentra registrada en el sistema.",
        )
    return venta


def ejecutar_operacion_negocio(fn):
    """Traduce las excepciones del dominio de FarmaExpress a códigos HTTP semánticos (403, 404, 409, 422)."""
    try:
        return fn()
    except UnauthorizedRoleAction as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permiso denegado por regla de negocio: {str(exc)}",
        )
    except InvalidOrderTransition as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Atención: No se pudo completar la operación debido al estado actual: {str(exc)}",
        )
    except (InvalidDomainData, DomainException, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Error de validación en las reglas de negocio farmacéutico: {str(exc)}",
        )


def run_action(venta: Venta, action):
    """Ejecuta una acción sobre una venta manteniendo el contrato de respuesta esperado."""
    def _wrapped():
        action()
        ventas_repo.guardar(venta)
        return {
            "mensaje_para_cliente": "Su orden ha sido procesada y confirmada exitosamente.",
            "venta_id": venta.id,
            "estado_actual": venta.estado.value,
            "total": str(venta.total.monto),
        }

    return ejecutar_operacion_negocio(_wrapped)


def _serializar_venta(venta: Venta) -> dict:
    productos_map = {p.id: p.nombre for p in productos_repo.listar()}
    return {
        "id": venta.id,
        "cajero_id": venta.cajero_id,
        "sucursal_id": venta.sucursal_id,
        "nombre_sucursal": SUCURSALES_FARMAEXPRESS.get(venta.sucursal_id, venta.sucursal_id),
        "estado": venta.estado.value,
        "motivo_de_rechazo": venta.motivo_de_rechazo,
        "requiere_validacion_responsable": venta.requiere_validacion_responsable,
        "total": str(venta.total.monto),
        "moneda": "MXN",
        "lineas": [
            {
                "id": l.id,
                "producto_id": l.producto_id,
                "nombre_producto": l.nombre_producto or productos_map.get(l.producto_id, l.producto_id),
                "lote": l.numero_lote.codigo,
                "cantidad": l.cantidad.valor,
                "precio_unitario": str(l.precio_unitario.monto),
                "subtotal": str(l.subtotal.monto),
                "validacion": l.validacion.value,
                "requisito_descripcion": l.requisito_descripcion,
                "responsable_validacion": l.responsable_validacion,
                "motivo_validacion": l.motivo_validacion,
            }
            for l in venta.lineas
        ],
        "eventos": [e.nombre for e in venta.eventos],
    }


# =====================================================================
# ESQUEMAS DE PETICIÓN (REQUEST BODIES CON EJEMPLOS PARA SWAGGER)
# =====================================================================
class IniciarVentaRequest(BaseModel):
    venta_id: str = Field(..., description="Folio único de la nueva venta", json_schema_extra={"example": "V-003"})
    cajero_id: str = Field(default="CAJ-01", description="Identificador del cajero que inicia la venta", json_schema_extra={"example": "CAJ-01"})
    sucursal_id: str = Field(default="SUC-01", description="Sucursal donde ocurre la venta (D-05)", json_schema_extra={"example": "SUC-01"})


class AgregarLineaRequest(BaseModel):
    producto_id: str = Field(..., description="ID del producto a registrar", json_schema_extra={"example": "PROD-01"})
    numero_lote: Optional[str] = Field(default=None, description="Código de lote (opcional; si se omite, el sistema asigna por FEFO)", json_schema_extra={"example": "LOTE-100"})
    cantidad: int = Field(..., description="Cantidad de unidades a vender (debe ser mayor a 0)", json_schema_extra={"example": 2})
    precio_unitario: Optional[float] = Field(default=None, description="Precio unitario en MXN (si se omite, toma el precio del catálogo)", json_schema_extra={"example": 250.0})
    requiere_validacion: Optional[bool] = Field(default=None, description="Indica si requiere validación especial (se detecta automáticamente del catálogo si se omite)")
    validar_en_inventario: bool = Field(default=False, description="Si es True, valida en vivo existencia, caducidad y retiro en el inventario antes de agregar")


class CompletarVentaRequest(BaseModel):
    simular_fallo_pago: bool = Field(
        default=False,
        description="Si es True, simula un rechazo del procesador de pagos para demostrar ADR-004 (la venta se rechaza sin descontar el inventario).",
    )


class ResolverValidacionRequest(BaseModel):
    linea_o_producto_id: str = Field(..., description="ID de la línea o del producto con requisito especial", json_schema_extra={"example": "PROD-02"})
    aprueba: bool = Field(..., description="True si el Responsable de Farmacia autoriza la venta; False si la rechaza", json_schema_extra={"example": True})
    responsable_id: str = Field(default="FARM-01", description="ID del Responsable de Farmacia que valida (BR-05)", json_schema_extra={"example": "FARM-01"})
    rol_usuario: str = Field(default="responsable_farmacia", description="Rol del usuario que ejecuta la acción (cajero será rechazado por BR-05)", json_schema_extra={"example": "responsable_farmacia"})
    motivo: str = Field(default="Receta médica verificada correctamente", description="Observación o número de receta verificada")


class SolicitarSustitucionRequest(BaseModel):
    solicitud_id: Optional[str] = Field(default=None, description="Folio de la solicitud (se genera automáticamente si se omite)", json_schema_extra={"example": "SUST-002"})
    venta_id: str = Field(..., description="ID de la venta en captura", json_schema_extra={"example": "V-001"})
    producto_original_id: str = Field(..., description="Producto solicitado que no cuenta con existencia", json_schema_extra={"example": "PROD-06"})
    cantidad: int = Field(default=1, description="Cantidad requerida por el cliente", json_schema_extra={"example": 1})
    motivo: str = Field(default="Producto sin existencia en la sucursal actual", description="Motivo de la solicitud de sustitución")


class ValidarSustitucionRequest(BaseModel):
    alternativa_id: str = Field(..., description="ID del producto alternativo propuesto", json_schema_extra={"example": "PROD-05"})
    aprueba: bool = Field(..., description="True si el Responsable de Farmacia aprueba la alternativa; False si no procede", json_schema_extra={"example": True})
    responsable_id: str = Field(default="FARM-01", description="ID del Responsable de Farmacia (BR-08)", json_schema_extra={"example": "FARM-01"})
    rol_usuario: str = Field(default="responsable_farmacia", description="Rol del usuario que valida (solo responsable_farmacia)", json_schema_extra={"example": "responsable_farmacia"})
    observacion: str = Field(default="Alternativa equivalente disponible y autorizada por farmacia", description="Justificación farmacéutica")


class DecisionClienteSustitucionRequest(BaseModel):
    acepta: bool = Field(..., description="True si el cliente acepta la alternativa explicada; False si decide cancelar el producto", json_schema_extra={"example": True})


class RecepcionMercanciaRequest(BaseModel):
    recepcion_id: Optional[str] = Field(default=None, description="Folio de recepción en almacén", json_schema_extra={"example": "REC-001"})
    sucursal_id: str = Field(default="SUC-01", description="Sucursal donde ingresa la mercancía", json_schema_extra={"example": "SUC-01"})
    producto_id: str = Field(..., description="ID del producto recibido", json_schema_extra={"example": "PROD-03"})
    numero_lote: str = Field(..., description="Código del lote recibido (D-03, BR-15)", json_schema_extra={"example": "LOTE-NUEVO-800"})
    caducidad: date = Field(..., description="Fecha de caducidad del lote recibido (D-04, BR-15)", json_schema_extra={"example": "2027-10-15"})
    cantidad: int = Field(..., description="Cantidad de unidades recibidas", json_schema_extra={"example": 25})
    responsable: str = Field(default="ALM-01", description="Personal de Almacén que registra la entrada", json_schema_extra={"example": "ALM-01"})
    rol_usuario: str = Field(default="almacen", description="Rol del usuario (cajero bloqueado por BR-14)", json_schema_extra={"example": "almacen"})


class RetirarLoteRequest(BaseModel):
    producto_id: str = Field(..., description="ID del producto", json_schema_extra={"example": "PROD-02"})
    sucursal_id: str = Field(default="SUC-01", description="ID de la sucursal", json_schema_extra={"example": "SUC-01"})
    numero_lote: str = Field(..., description="Código del lote a bloquear como RETIRADO (BR-03, US-06)", json_schema_extra={"example": "LOTE-PROX-201"})
    responsable: str = Field(default="FARM-01", description="Responsable de Farmacia que instruye el retiro", json_schema_extra={"example": "FARM-01"})
    rol_usuario: str = Field(default="responsable_farmacia", description="Rol del usuario (solo responsable_farmacia o administracion)", json_schema_extra={"example": "responsable_farmacia"})
    motivo: str = Field(..., description="Motivo sanitario u operativo del retiro del lote", json_schema_extra={"example": "Retiro preventivo por proximidad a caducidad / alerta sanitaria"})


class RegistrarDiferenciaRequest(BaseModel):
    diferencia_id: Optional[str] = Field(default=None, description="Folio del reporte de diferencia", json_schema_extra={"example": "DIF-002"})
    producto_id: str = Field(..., description="ID del producto auditado", json_schema_extra={"example": "PROD-01"})
    sucursal_id: str = Field(default="SUC-01", description="Sucursal donde se realizó el conteo físico", json_schema_extra={"example": "SUC-01"})
    numero_lote: str = Field(..., description="Número de lote revisado físicamente", json_schema_extra={"example": "LOTE-100"})
    cantidad_fisica: int = Field(..., description="Cantidad real contada en estante/almacén", json_schema_extra={"example": 18})
    motivo: str = Field(..., description="Descripción del hallazgo en el conteo físico (BR-13, US-10)", json_schema_extra={"example": "Diferencia detectada durante inventario físico quincenal"})
    reportado_por: str = Field(default="ALM-01", description="Personal de Almacén que reporta", json_schema_extra={"example": "ALM-01"})
    rol_usuario: str = Field(default="almacen", description="Rol del usuario (cajero restringido por BR-14)", json_schema_extra={"example": "almacen"})


class RevisarDiferenciaRequest(BaseModel):
    aprobar_ajuste: bool = Field(..., description="True para autorizar y aplicar el ajuste al inventario; False para rechazarlo", json_schema_extra={"example": True})
    revisado_por: str = Field(default="FARM-01", description="Responsable que revisa y autoriza el ajuste (RF-15, RNF-08)", json_schema_extra={"example": "FARM-01"})
    rol_usuario: str = Field(default="responsable_farmacia", description="Rol del autorizador (responsable_farmacia o administracion)", json_schema_extra={"example": "responsable_farmacia"})
    observacion: str = Field(..., description="Justificación obligatoria de la revisión (RNF-08)", json_schema_extra={"example": "Se verificó acta de merma física en almacén; procede ajuste"})


class AnalizarResurtidoRequest(BaseModel):
    solicitar_abastecimiento: bool = Field(..., description="True si Compras decide solicitar el resurtido tras el análisis; False si lo descarta", json_schema_extra={"example": True})
    analizado_por: str = Field(default="COMP-01", description="Analista de Compras responsable (BR-10)", json_schema_extra={"example": "COMP-01"})
    rol_usuario: str = Field(default="compras", description="Rol del usuario (compras o administracion)", json_schema_extra={"example": "compras"})
    cantidad_solicitada: int = Field(default=30, description="Cantidad de unidades a solicitar al proveedor", json_schema_extra={"example": 30})
    justificacion: str = Field(..., description="Justificación del análisis de Compras (BR-10)", json_schema_extra={"example": "Alta rotación en Sucursal Centro; se solicita reposición de 30 unidades"})


class ActualizarPoliticaRequest(BaseModel):
    dias_proximidad_caducidad: int = Field(..., description="Días de anticipación para considerar un lote próximo a caducar (BR-12)", json_schema_extra={"example": 30})
    rol_usuario: str = Field(default="administracion", description="Rol del usuario que valida la política", json_schema_extra={"example": "administracion"})


# =====================================================================
# ARCHIVOS ESTÁTICOS E INTERFAZ WEB HTML/CSS (ENTENDIBLE PARA EL USUARIO)
# =====================================================================
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def serve_web_interface():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"mensaje": "Bienvenido a FarmaExpress API. Visita /docs para Swagger UI."}


@app.get("/health", tags=["Sistema y Demostración"], summary="Verificar estado de salud del servicio")
def health_check():
    return {
        "status": "ok",
        "empresa": "FarmaExpress",
        "sucursales_activas": len(SUCURSALES_FARMAEXPRESS),
        "productos_en_catalogo": len(productos_repo.listar()),
    }


@app.get("/contexto-demo", tags=["Sistema y Demostración"], summary="Obtener roles, sucursales y catálogo para la interfaz de usuario")
def obtener_contexto_demo():
    return {
        "empresa": "FarmaExpress",
        "politica_dias_proximidad_caducidad": politica_actual["dias_proximidad_caducidad"],
        "sucursales": [{"id": k, "nombre": v} for k, v in SUCURSALES_FARMAEXPRESS.items()],
        "usuarios_demo": USUARIOS_DEMO,
        "productos": [
            {
                "id": p.id,
                "nombre": p.nombre,
                "tipo": p.tipo.value,
                "categoria": p.categoria,
                "precio": str(p.precio.monto),
                "requiere_validacion_especial": p.requiere_validacion_especial(),
                "requisito_especial": p.requisito.descripcion,
                "sustitutos_ids": p.sustitutos_ids,
            }
            for p in productos_repo.listar()
        ],
    }


@app.post("/demo/reiniciar", tags=["Sistema y Demostración"], summary="Reiniciar los datos de demostración al estado inicial")
def reiniciar_datos_demo():
    _inicializar_datos_mock()
    return {
        "mensaje": "Los datos de demostración de FarmaExpress se han restablecido correctamente.",
        "ventas_registradas": len(ventas_repo.listar()),
        "productos_catalogo": len(productos_repo.listar()),
    }


# =====================================================================
# ENDPOINTS 1: VENTAS Y OPERACIÓN DE CAJA (CU-01, CU-04, US-01, US-04, US-17)
# =====================================================================
@app.get(
    "/orders",
    tags=["Ventas y Caja"],
    summary="Listar todas las ventas registradas",
)
def listar_ventas():
    return [_serializar_venta(v) for v in ventas_repo.listar()]


@app.post(
    "/orders",
    tags=["Ventas y Caja"],
    summary="Iniciar una nueva venta en captura (RF-01, US-01)",
    status_code=201,
    responses={409: RESPUESTAS_ERROR_SWAGGER[409], 422: RESPUESTAS_ERROR_SWAGGER[422]},
)
def iniciar_venta_endpoint(body: IniciarVentaRequest):
    uow = MemoriaUnidadDeTrabajo()
    servicio = IniciarVentaService(ventas_repo=ventas_repo, uow=uow)
    venta = ejecutar_operacion_negocio(lambda: servicio.ejecutar(body.venta_id, body.cajero_id, body.sucursal_id))
    return {
        "mensaje_para_cliente": f"Nueva operación de venta {venta.id} iniciada en {SUCURSALES_FARMAEXPRESS.get(venta.sucursal_id, venta.sucursal_id)}.",
        "venta": _serializar_venta(venta),
    }


@app.get(
    "/orders/{venta_id}",
    tags=["Ventas y Caja"],
    summary="Consultar detalles de una venta",
    responses={404: RESPUESTAS_ERROR_SWAGGER[404]},
)
def get_order_details(venta_id: str):
    venta = get_venta_or_404(venta_id)
    return _serializar_venta(venta)


@app.post(
    "/orders/{venta_id}/lineas",
    tags=["Ventas y Caja"],
    summary="Agregar producto a la venta (US-01, US-04, BR-01 a BR-04)",
    responses={
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def agregar_linea_endpoint(venta_id: str, body: AgregarLineaRequest):
    venta = get_venta_or_404(venta_id)

    if body.validar_en_inventario or body.numero_lote is None or body.precio_unitario is None:
        uow = MemoriaUnidadDeTrabajo()
        servicio = RegistrarProductoEnVentaService(
            ventas_repo=ventas_repo,
            inventarios_repo=inventarios_repo,
            productos_repo=productos_repo,
            uow=uow,
        )
        ejecutar_operacion_negocio(
            lambda: servicio.ejecutar(
                venta_id=venta_id,
                producto_id=body.producto_id,
                cantidad=body.cantidad,
                hoy=date.today(),
                numero_lote=body.numero_lote,
                precio_unitario=Decimal(str(body.precio_unitario)) if body.precio_unitario is not None else None,
                requiere_validacion=body.requiere_validacion,
            )
        )
        return {
            "mensaje_para_cliente": "Producto validado y agregado a la venta exitosamente.",
            "venta_id": venta.id,
            "estado_actual": venta.estado.value,
            "total": str(venta.total.monto),
            "requiere_validacion_responsable": venta.requiere_validacion_responsable,
        }

    # Si viene con lote y precio explícitos, verificamos también si el lote está caducado o retirado en inventario cuando existe
    def _agregar_validado():
        cant_vo = Cantidad(body.cantidad)
        lote_vo = NumeroDeLote(body.numero_lote)
        precio_vo = Dinero(Decimal(str(body.precio_unitario)))

        inv = inventarios_repo.obtener_de(body.producto_id, venta.sucursal_id)
        if inv:
            lote_en_inv = inv.obtener_lote(lote_vo.codigo)
            if lote_en_inv:
                vendible, motivo = lote_en_inv.es_vendible(date.today())
                if not vendible:
                    raise InvalidDomainData(f"No se puede agregar a la venta: {motivo}")
                if lote_en_inv.cantidad.valor < cant_vo.valor:
                    raise InvalidDomainData(
                        f"Existencia insuficiente en el lote {lote_vo.codigo} (disponible: {lote_en_inv.cantidad.valor}, solicitado: {cant_vo.valor}) (BR-01)."
                    )

        prod_cat = productos_repo.obtener_por_id(body.producto_id)
        req_val = (
            body.requiere_validacion
            if body.requiere_validacion is not None
            else (prod_cat.requiere_validacion_especial() if prod_cat else False)
        )
        venta.agregar_linea(
            producto_id=body.producto_id,
            numero_lote=lote_vo,
            cantidad=cant_vo,
            precio_unitario=precio_vo,
            requiere_validarcion=req_val,
            nombre_producto=prod_cat.nombre if prod_cat else body.producto_id,
            requisito_descripcion=prod_cat.requisito.descripcion if prod_cat else "",
        )

    return run_action(venta, _agregar_validado)


@app.post(
    "/orders/{venta_id}/completar",
    tags=["Ventas y Caja"],
    summary="Completar y cobrar una venta de forma segura (CU-04, US-17, ADR-004)",
    responses={
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def completar_venta_endpoint(
    venta_id: str,
    simular_fallo_pago: bool = Query(
        default=False,
        description="Si es True, simula un rechazo de la pasarela de pagos para demostrar que la venta pasa a RECHAZADA sin descontar el inventario (ADR-004).",
    ),
):
    venta = get_venta_or_404(venta_id)

    procesador_pagos = SimuladorProcesadorDePagos(respuesta_exitosa=not simular_fallo_pago)
    uow = MemoriaUnidadDeTrabajo()

    servicio = CompletarVentaService(
        ventas_repo=ventas_repo,
        inventarios_repo=inventarios_repo,
        procesador_pagos=procesador_pagos,
        uow=uow,
        publicador_eventos=publicador_eventos,
        resurtidos_repo=resurtidos_repo,
    )

    return run_action(venta, lambda: servicio.ejecutar(venta_id, date.today()))


# =====================================================================
# ENDPOINTS 2: VALIDACIÓN DE REQUISITOS ESPECIALES POR FARMACIA (CU-02, US-03, BR-04, BR-05)
# =====================================================================
@app.get(
    "/validaciones-pendientes",
    tags=["Validación Farmacéutica (BR-04/BR-05)"],
    summary="Consultar medicamentos con requisitos especiales pendientes de autorización (US-03)",
)
def listar_validaciones_pendientes():
    pendientes = []
    for v in ventas_repo.listar():
        if v.esta_en_captura():
            for l in v.lineas:
                if l.validacion == EstadoValidacion.PENDIENTE:
                    pendientes.append(
                        {
                            "venta_id": v.id,
                            "sucursal_id": v.sucursal_id,
                            "cajero_id": v.cajero_id,
                            "linea_id": l.id,
                            "producto_id": l.producto_id,
                            "nombre_producto": l.nombre_producto,
                            "lote": l.numero_lote.codigo,
                            "cantidad": l.cantidad.valor,
                            "requisito_especial": l.requisito_descripcion,
                            "estado_validacion": l.validacion.value,
                        }
                    )
    return pendientes


@app.post(
    "/orders/{venta_id}/validaciones",
    tags=["Validación Farmacéutica (BR-04/BR-05)"],
    summary="Aprobar o rechazar requisito especial de un medicamento (CU-02, US-03, BR-04, BR-05)",
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def resolver_validacion_endpoint(venta_id: str, body: ResolverValidacionRequest):
    get_venta_or_404(venta_id)
    uow = MemoriaUnidadDeTrabajo()
    servicio = ResolverValidacionEspecialService(
        ventas_repo=ventas_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    venta = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            venta_id=venta_id,
            linea_o_producto_id=body.linea_o_producto_id,
            aprueba=body.aprueba,
            responsable_id=body.responsable_id,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
            motivo=body.motivo,
        )
    )
    accion_txt = "APROBADA" if body.aprueba else "RECHAZADA (venta bloqueada)"
    return {
        "mensaje": f"Validación especial {accion_txt} por el Responsable de Farmacia ({body.responsable_id}).",
        "venta": _serializar_venta(venta),
    }


# =====================================================================
# ENDPOINTS 3: ATENCIÓN Y VALIDACIÓN DE SUSTITUCIONES (CU-03, US-07, US-08, BR-08)
# =====================================================================
@app.get(
    "/sustituciones",
    tags=["Sustituciones (CU-03 / BR-08)"],
    summary="Listar todas las solicitudes de sustitución registradas",
)
def listar_sustituciones():
    productos_map = {p.id: p.nombre for p in productos_repo.listar()}
    return [
        {
            "id": s.id,
            "venta_id": s.venta_id,
            "producto_original": s.producto_original,
            "nombre_original": productos_map.get(s.producto_original, s.producto_original),
            "alternativa": s.alternativa,
            "nombre_alternativa": productos_map.get(s.alternativa, s.alternativa) if s.alternativa else None,
            "cantidad": s.cantidad.valor,
            "estado": s.estado.value,
            "motivo": s.motivo,
            "decision_farmacia": (
                {
                    "aprobada": s.decision_farmacia.aprobada,
                    "responsable": s.decision_farmacia.responsable,
                    "fecha": str(s.decision_farmacia.fecha),
                    "observacion": s.decision_farmacia.observacion,
                }
                if s.decision_farmacia
                else None
            ),
            "decision_cliente": (
                {
                    "acepta": s.decision_cliente.acepta,
                    "fecha": str(s.decision_cliente.fecha),
                }
                if s.decision_cliente
                else None
            ),
        }
        for s in sustituciones_repo.listar()
    ]


@app.get(
    "/productos/{producto_id}/alternativas/{sucursal_id}",
    tags=["Sustituciones (CU-03 / BR-08)"],
    summary="Consultar productos alternativos con existencia vendible en la sucursal (US-07)",
)
def consultar_alternativas_endpoint(producto_id: str, sucursal_id: str):
    query = ConsultarAlternativasDisponiblesQuery(productos_repo, inventarios_repo)
    return {
        "producto_original_id": producto_id,
        "sucursal_id": sucursal_id,
        "alternativas_disponibles": query.ejecutar(producto_id, sucursal_id, date.today()),
    }


@app.post(
    "/sustituciones",
    tags=["Sustituciones (CU-03 / BR-08)"],
    summary="Registrar solicitud de sustitución por falta de existencia (CU-03 paso 1, US-07)",
    status_code=201,
    responses={
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def crear_solicitud_sustitucion_endpoint(body: SolicitarSustitucionRequest):
    get_venta_or_404(body.venta_id)
    uow = MemoriaUnidadDeTrabajo()
    servicio = SolicitarSustitucionService(
        ventas_repo=ventas_repo,
        sustituciones_repo=sustituciones_repo,
        uow=uow,
    )
    sol_id = body.solicitud_id or f"SUST-{len(sustituciones_repo.listar()) + 1:03d}"
    sol = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            solicitud_id=sol_id,
            venta_id=body.venta_id,
            producto_original_id=body.producto_original_id,
            cantidad=body.cantidad,
            motivo=body.motivo,
        )
    )
    return {
        "mensaje": "Solicitud de sustitución registrada. Pendiente de revisión por el Responsable de Farmacia (BR-08).",
        "solicitud_id": sol.id,
        "estado": sol.estado.value,
    }


@app.post(
    "/sustituciones/{solicitud_id}/validar",
    tags=["Sustituciones (CU-03 / BR-08)"],
    summary="Validar solicitud de sustitución por el Responsable de Farmacia (CU-03 paso 2, US-08, BR-08)",
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def validar_sustitucion_endpoint(solicitud_id: str, body: ValidarSustitucionRequest):
    if not sustituciones_repo.obtener_por_id(solicitud_id):
        raise HTTPException(status_code=404, detail="La solicitud de sustitución no existe.")
    uow = MemoriaUnidadDeTrabajo()
    servicio = ValidarSustitucionService(
        sustituciones_repo=sustituciones_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    sol = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            solicitud_id=solicitud_id,
            alternativa_id=body.alternativa_id,
            aprueba=body.aprueba,
            responsable_id=body.responsable_id,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
            observacion=body.observacion,
        )
    )
    return {
        "mensaje": "Decisión del Responsable de Farmacia registrada exitosamente.",
        "solicitud_id": sol.id,
        "estado": sol.estado.value,
        "alternativa": sol.alternativa,
    }


@app.post(
    "/sustituciones/{solicitud_id}/decision-cliente",
    tags=["Sustituciones (CU-03 / BR-08)"],
    summary="Registrar si el cliente acepta la alternativa y agregarla a la venta (CU-03 paso 3, Secuencia 2)",
    responses={
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def decision_cliente_sustitucion_endpoint(solicitud_id: str, body: DecisionClienteSustitucionRequest):
    if not sustituciones_repo.obtener_por_id(solicitud_id):
        raise HTTPException(status_code=404, detail="La solicitud de sustitución no existe.")
    uow = MemoriaUnidadDeTrabajo()
    servicio = RegistrarDecisionDelClienteService(
        sustituciones_repo=sustituciones_repo,
        ventas_repo=ventas_repo,
        inventarios_repo=inventarios_repo,
        productos_repo=productos_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    sol = ejecutar_operacion_negocio(lambda: servicio.ejecutar(solicitud_id, body.acepta, date.today()))
    return {
        "mensaje": (
            "El cliente aceptó la alternativa. El producto sustituto se agregó automáticamente a la venta con lote asignado."
            if body.acepta
            else "El cliente rechazó la alternativa. Se canceló el ítem sin afectar la venta."
        ),
        "solicitud_id": sol.id,
        "estado": sol.estado.value,
        "venta_id": sol.venta_id,
    }


# =====================================================================
# ENDPOINTS 4: INVENTARIO, LOTES, CADUCIDADES Y MULTISUCURSAL (US-02, US-05, US-06, US-09, US-13, US-15)
# =====================================================================
@app.get(
    "/inventarios/{producto_id}/{sucursal_id}",
    tags=["Inventario, Lotes y Caducidades"],
    summary="Consultar disponibilidad y lotes de un producto en una sucursal (US-02, US-09)",
)
def consultar_inventario_endpoint(producto_id: str, sucursal_id: str):
    query = ConsultarDisponibilidadQuery(
        inventarios_repo,
        dias_proximidad=politica_actual["dias_proximidad_caducidad"],
    )
    resultado = query.ejecutar(producto_id, sucursal_id, date.today())
    return {
        "mensaje": "Consulta realizada correctamente.",
        "informacion": resultado,
    }


@app.get(
    "/disponibilidad-sucursales/{producto_id}",
    tags=["Inventario, Lotes y Caducidades"],
    summary="Consultar disponibilidad de un producto en todas las sucursales de FarmaExpress (US-13, BR-16, REP-05)",
)
def consultar_disponibilidad_multisucursal_endpoint(producto_id: str):
    query = ConsultarDisponibilidadPorSucursalQuery(inventarios_repo, SUCURSALES_FARMAEXPRESS)
    return query.ejecutar(producto_id, date.today())


@app.get(
    "/inventarios-sucursal/{sucursal_id}",
    tags=["Inventario, Lotes y Caducidades"],
    summary="Listar el inventario completo de todos los productos en una sucursal (US-09)",
)
def listar_inventario_completo_sucursal(sucursal_id: str):
    query = ConsultarDisponibilidadQuery(
        inventarios_repo,
        dias_proximidad=politica_actual["dias_proximidad_caducidad"],
    )
    resultado = []
    for p in productos_repo.listar():
        info = query.ejecutar(p.id, sucursal_id, date.today())
        resultado.append(
            {
                **info,
                "nombre_producto": p.nombre,
                "tipo": p.tipo.value,
                "categoria": p.categoria,
                "precio": str(p.precio.monto),
                "requiere_validacion_especial": p.requiere_validacion_especial(),
                "requisito_especial": p.requisito.descripcion,
            }
        )
    return resultado


@app.post(
    "/lotes/retirar",
    tags=["Inventario, Lotes y Caducidades"],
    summary="Bloquear y retirar un lote de la operación (US-06, BR-03, RF-04)",
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def retirar_lote_endpoint(body: RetirarLoteRequest):
    if not inventarios_repo.obtener_de(body.producto_id, body.sucursal_id):
        raise HTTPException(status_code=404, detail="No existe inventario para el producto y sucursal indicados.")
    uow = MemoriaUnidadDeTrabajo()
    servicio = RetirarLoteService(
        inventarios_repo=inventarios_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            producto_id=body.producto_id,
            sucursal_id=body.sucursal_id,
            numero_lote=body.numero_lote,
            responsable=body.responsable,
            motivo=body.motivo,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
        )
    )
    return {
        "mensaje": f"El lote {body.numero_lote} ha sido marcado como RETIRADO y bloqueado para futuras ventas (BR-03).",
        "producto_id": body.producto_id,
        "sucursal_id": body.sucursal_id,
        "lote": body.numero_lote,
        "estado": EstadoDelLote.RETIRADO.value,
    }


# =====================================================================
# ENDPOINTS 5: ALMACÉN, RECEPCIÓN DE MERCANCÍA Y DIFERENCIAS (CU-05, US-10, US-14, BR-13..15)
# =====================================================================
@app.get(
    "/recepciones",
    tags=["Almacén y Diferencias (CU-05 / BR-13)"],
    summary="Listar recepciones de mercancía registradas en Almacén (US-14)",
)
def listar_recepciones():
    productos_map = {p.id: p.nombre for p in productos_repo.listar()}
    return [
        {
            "id": r.id,
            "sucursal_id": r.sucursal_id,
            "responsable": r.responsable,
            "fecha": str(r.fecha),
            "lineas": [
                {
                    "producto_id": l.producto_id,
                    "nombre_producto": productos_map.get(l.producto_id, l.producto_id),
                    "lote": l.lote.codigo,
                    "caducidad": str(l.caducidad.fecha),
                    "cantidad": l.cantidad.valor,
                }
                for l in r.lineas
            ],
        }
        for r in recepciones_repo.listar()
    ]


@app.post(
    "/recepciones",
    tags=["Almacén y Diferencias (CU-05 / BR-13)"],
    summary="Registrar recepción de productos en Almacén con lote y caducidad (CU-05, US-14, BR-06, BR-15)",
    status_code=201,
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def registrar_recepcion_endpoint(body: RecepcionMercanciaRequest):
    uow = MemoriaUnidadDeTrabajo()
    servicio = RegistrarRecepcionDeMercanciaService(
        recepciones_repo=recepciones_repo,
        inventarios_repo=inventarios_repo,
        uow=uow,
        publicador=publicador_eventos,
        resurtidos_repo=resurtidos_repo,
    )
    rec_id = body.recepcion_id or f"REC-{len(recepciones_repo.listar()) + 1:03d}"
    rec = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            recepcion_id=rec_id,
            sucursal_id=body.sucursal_id,
            producto_id=body.producto_id,
            numero_lote=body.numero_lote,
            caducidad=body.caducidad,
            cantidad=body.cantidad,
            responsable=body.responsable,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
        )
    )
    return {
        "mensaje": f"Recepción {rec.id} registrada exitosamente. Se actualizó la existencia del lote {body.numero_lote} en {body.sucursal_id}.",
        "recepcion_id": rec.id,
        "sucursal_id": rec.sucursal_id,
    }


@app.get(
    "/diferencias-inventario",
    tags=["Almacén y Diferencias (CU-05 / BR-13)"],
    summary="Consultar diferencias registradas entre inventario físico y sistema (US-10, REP-06)",
)
def listar_diferencias_endpoint():
    productos_map = {p.id: p.nombre for p in productos_repo.listar()}
    return [
        {
            "id": d.id,
            "producto_id": d.producto_id,
            "nombre_producto": productos_map.get(d.producto_id, d.producto_id),
            "sucursal_id": d.sucursal_id,
            "lote": d.numero_lote.codigo,
            "cantidad_registrada": d.cantidad_registrada.valor,
            "cantidad_fisica": d.cantidad_fisica.valor,
            "diferencia": d.diferencia,
            "motivo": d.motivo,
            "reportado_por": d.reportado_por,
            "fecha_reporte": str(d.fecha_reporte),
            "estado": d.estado.value,
            "revisado_por": d.revisado_por,
            "observacion_revision": d.observacion_revision,
        }
        for d in diferencias_repo.listar()
    ]


@app.post(
    "/diferencias-inventario",
    tags=["Almacén y Diferencias (CU-05 / BR-13)"],
    summary="Registrar una diferencia entre conteo físico e inventario registrado (US-10, BR-13, BR-14, RF-14)",
    status_code=201,
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        404: RESPUESTAS_ERROR_SWAGGER[404],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def registrar_diferencia_endpoint(body: RegistrarDiferenciaRequest):
    if not inventarios_repo.obtener_de(body.producto_id, body.sucursal_id):
        raise HTTPException(status_code=404, detail="No existe inventario para el producto y sucursal especificados.")
    uow = MemoriaUnidadDeTrabajo()
    servicio = RegistrarDiferenciaInventarioService(
        inventarios_repo=inventarios_repo,
        diferencias_repo=diferencias_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    dif_id = body.diferencia_id or f"DIF-{len(diferencias_repo.listar()) + 1:03d}"
    dif = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            diferencia_id=dif_id,
            producto_id=body.producto_id,
            sucursal_id=body.sucursal_id,
            numero_lote=body.numero_lote,
            cantidad_fisica=body.cantidad_fisica,
            motivo=body.motivo,
            reportado_por=body.reportado_por,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
        )
    )
    return {
        "mensaje": "Diferencia de inventario registrada para revisión. El inventario no se modifica hasta ser autorizado (BR-13, RF-15).",
        "diferencia_id": dif.id,
        "diferencia": dif.diferencia,
        "estado": dif.estado.value,
    }


@app.post(
    "/diferencias-inventario/{diferencia_id}/revisar",
    tags=["Almacén y Diferencias (CU-05 / BR-13)"],
    summary="Revisar y autorizar/rechazar ajuste de diferencia de inventario (BR-13, BR-14, RF-15, RNF-08)",
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def revisar_diferencia_endpoint(diferencia_id: str, body: RevisarDiferenciaRequest):
    if not diferencias_repo.obtener_por_id(diferencia_id):
        raise HTTPException(status_code=404, detail="El registro de diferencia de inventario no existe.")
    uow = MemoriaUnidadDeTrabajo()
    servicio = RevisarDiferenciaInventarioService(
        diferencias_repo=diferencias_repo,
        inventarios_repo=inventarios_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    dif = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            diferencia_id=diferencia_id,
            aprobar_ajuste=body.aprobar_ajuste,
            revisado_por=body.revisado_por,
            observacion=body.observacion,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
        )
    )
    return {
        "mensaje": (
            f"Ajuste autorizado por {dif.revisado_por}. El lote {dif.numero_lote.codigo} se actualizó a {dif.cantidad_fisica.valor} unidades con registro de auditoría."
            if body.aprobar_ajuste
            else f"Ajuste rechazado por {dif.revisado_por}. El inventario registrado se mantiene sin cambios."
        ),
        "diferencia_id": dif.id,
        "estado": dif.estado.value,
    }


# =====================================================================
# ENDPOINTS 6: COMPRAS Y ANÁLISIS MANUAL DE RESURTIDO (US-11, US-12, BR-09, BR-10, RF-11, RF-12)
# =====================================================================
@app.get(
    "/resurtidos",
    tags=["Compras y Resurtido (BR-09 / BR-10)"],
    summary="Consultar productos con existencia baja y solicitudes de resurtido para Compras (US-11, US-12, REP-01, REP-07)",
)
def listar_resurtidos_endpoint():
    productos_map = {p.id: p.nombre for p in productos_repo.listar()}
    return [
        {
            "id": r.id,
            "producto_id": r.producto_id,
            "nombre_producto": productos_map.get(r.producto_id, r.producto_id),
            "sucursal_id": r.sucursal_id,
            "nombre_sucursal": SUCURSALES_FARMAEXPRESS.get(r.sucursal_id, r.sucursal_id),
            "existencia_actual": r.existencia_actual,
            "nivel_minimo": r.nivel_minimo,
            "estado": r.estado.value,
            "fecha_alerta": str(r.fecha_alerta),
            "analizado_por": r.analizado_por,
            "cantidad_solicitada": r.cantidad_solicitada,
            "justificacion": r.justificacion,
        }
        for r in resurtidos_repo.listar()
    ]


@app.post(
    "/resurtidos/{resurtido_id}/analizar",
    tags=["Compras y Resurtido (BR-09 / BR-10)"],
    summary="Registrar decisión de abastecimiento tras análisis del área de Compras (US-12, BR-10, RF-12)",
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        404: RESPUESTAS_ERROR_SWAGGER[404],
        409: RESPUESTAS_ERROR_SWAGGER[409],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def analizar_resurtido_endpoint(resurtido_id: str, body: AnalizarResurtidoRequest):
    if not resurtidos_repo.obtener_por_id(resurtido_id):
        raise HTTPException(status_code=404, detail="La alerta o solicitud de resurtido no existe.")
    uow = MemoriaUnidadDeTrabajo()
    servicio = AnalizarResurtidoService(
        resurtidos_repo=resurtidos_repo,
        uow=uow,
        publicador=publicador_eventos,
    )
    res = ejecutar_operacion_negocio(
        lambda: servicio.ejecutar(
            resurtido_id=resurtido_id,
            solicitar_abastecimiento=body.solicitar_abastecimiento,
            analizado_por=body.analizado_por,
            cantidad_solicitada=body.cantidad_solicitada,
            justificacion=body.justificacion,
            rol_usuario=body.rol_usuario,
            hoy=date.today(),
        )
    )
    return {
        "mensaje": (
            f"Análisis de Compras registrado (BR-10): Se solicitó resurtido de {res.cantidad_solicitada} unidades para {res.producto_id}."
            if body.solicitar_abastecimiento
            else "Análisis de Compras registrado (BR-10): Se descartó la solicitud de resurtido con justificación."
        ),
        "resurtido_id": res.id,
        "estado": res.estado.value,
        "cantidad_solicitada": res.cantidad_solicitada,
    }


# =====================================================================
# ENDPOINTS 7: ADMINISTRACIÓN, INDICADORES (IND-01..05), REPORTES (REP-01..07) Y POLÍTICAS (US-16, BR-12)
# =====================================================================
@app.get(
    "/indicadores",
    tags=["Administración, Indicadores y Trazabilidad"],
    summary="Consultar indicadores consolidados (IND-01 a IND-05) y reportes de negocio (REP-01 a REP-07) (US-16)",
)
def consultar_indicadores_endpoint():
    query = ConsultarIndicadoresConsolidadosQuery(
        inventarios_repo=inventarios_repo,
        productos_repo=productos_repo,
        diferencias_repo=diferencias_repo,
        resurtidos_repo=resurtidos_repo,
        ventas_repo=ventas_repo,
        dias_proximidad=politica_actual["dias_proximidad_caducidad"],
    )
    return query.ejecutar(date.today())


@app.post(
    "/politicas/caducidad",
    tags=["Administración, Indicadores y Trazabilidad"],
    summary="Configurar el periodo de proximidad a caducidad de FarmaExpress (BR-12, US-05)",
    responses={
        403: RESPUESTAS_ERROR_SWAGGER[403],
        422: RESPUESTAS_ERROR_SWAGGER[422],
    },
)
def actualizar_politica_caducidad(body: ActualizarPoliticaRequest):
    def _actualizar():
        if body.rol_usuario not in (RolUsuario.ADMINISTRACION.value, RolUsuario.RESPONSABLE_FARMACIA.value):
            raise UnauthorizedRoleAction("Solo Administración o el Responsable de Farmacia pueden definir la política de proximidad a caducidad (BR-12).")
        pol = PoliticaFarmaExpress(dias_proximidad_caducidad=body.dias_proximidad_caducidad)
        politica_actual["dias_proximidad_caducidad"] = pol.dias_proximidad_caducidad
        return {
            "mensaje": f"Política actualizada (BR-12): Se identificarán como próximos a caducar los lotes dentro de {pol.dias_proximidad_caducidad} días.",
            "dias_proximidad_caducidad": pol.dias_proximidad_caducidad,
        }

    return ejecutar_operacion_negocio(_actualizar)


@app.get(
    "/bitacora-eventos",
    tags=["Administración, Indicadores y Trazabilidad"],
    summary="Consultar historial de eventos de dominio y alertas emitidas (RNF-03, RNF-08)",
)
def consultar_bitacora_eventos():
    return {
        "total_eventos": len(publicador_eventos.eventos_publicados),
        "alertas_a_compras": publicador_eventos.alertas_compras,
        "historial": publicador_eventos.listar_historial(),
    }
