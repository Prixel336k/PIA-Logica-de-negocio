from datetime import date, timedelta
from decimal import Decimal
import pytest

from src.domain import (
    Dinero,
    Cantidad,
    NumeroDeLote,
    EstadoDelLote,
    Lote,
    InventarioDeProducto,
    Producto,
    TipoDeProducto,
    RequisitoEspecial,
    Venta,
    EstadoVenta,
    EstadoDeSustitucion,
    EstadoResurtido,
    EstadoDiferenciaInventario,
    RolUsuario,
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
)


def test_completar_venta_exitososa():
    # Valida el flujo completo del caso de uso CU-04: venta cobrada, inventario descontado y venta completada.
    hoy = date(2026, 11, 5)
    mañana = hoy + timedelta(days=1)

    ventas_repo = MemoriaRepositorioDeVentas()
    inventarios_repo = MemoriaRepositorioDeInventarios()
    procesador_pagos = SimuladorProcesadorDePagos(respuesta_exitosa=True)
    uow = MemoriaUnidadDeTrabajo()

    lote = Lote(
        numero=NumeroDeLote("LOTE-100"),
        caducidad=mañana,
        cantidad=Cantidad(10),
        estado=EstadoDelLote.DISPONIBLE,
    )
    inventario = InventarioDeProducto(
        producto_id="PROD-99",
        sucursal_id="SUC-01",
        nivel_minimo=2,
        lotes=[lote],
    )
    inventarios_repo.guardar(inventario)

    venta = Venta(
        id="V-100",
        cajero_id="CAJ-01",
        sucursal_id="SUC-01",
    )
    venta.agregar_linea(
        producto_id="PROD-99",
        numero_lote=NumeroDeLote("LOTE-100"),
        cantidad=Cantidad(2),
        precio_unitario=Dinero(Decimal("150.00")),
    )
    ventas_repo.guardar(venta)

    servicio = CompletarVentaService(
        ventas_repo=ventas_repo,
        inventarios_repo=inventarios_repo,
        procesador_pagos=procesador_pagos,
        uow=uow,
    )

    resultado = servicio.ejecutar("V-100", hoy)

    assert "exitosamente" in resultado
    assert venta.estado == EstadoVenta.COMPLETADA
    assert inventario.existencia_total == 8
    assert uow.cometido is True


def test_completar_venta_pago_rechazado_no_descuenta_inventario():
    # Valida ADR-004 (Secuencia 1): Si el procesador de pagos rechaza el cobro, la venta pasa a RECHAZADA y el inventario queda intacto.
    hoy = date(2026, 11, 5)
    ventas_repo = MemoriaRepositorioDeVentas()
    inventarios_repo = MemoriaRepositorioDeInventarios()
    procesador_fallido = SimuladorProcesadorDePagos(respuesta_exitosa=False)
    uow = MemoriaUnidadDeTrabajo()
    publicador = MemoriaPublicadorDeEventos()

    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-01",
            sucursal_id="SUC-01",
            nivel_minimo=5,
            lotes=[Lote(NumeroDeLote("LOTE-01"), hoy + timedelta(days=30), Cantidad(10))],
        )
    )
    venta = Venta(id="V-FALLO", cajero_id="CAJ-01", sucursal_id="SUC-01")
    venta.agregar_linea("PROD-01", NumeroDeLote("LOTE-01"), Cantidad(4), Dinero(Decimal("100.00")))
    ventas_repo.guardar(venta)

    servicio = CompletarVentaService(
        ventas_repo=ventas_repo,
        inventarios_repo=inventarios_repo,
        procesador_pagos=procesador_fallido,
        uow=uow,
        publicador_eventos=publicador,
    )

    with pytest.raises(RuntimeError):
        servicio.ejecutar("V-FALLO", hoy)

    assert venta.estado == EstadoVenta.RECHAZADA
    assert inventarios_repo.obtener_de("PROD-01", "SUC-01").existencia_total == 10
    assert any(ev.nombre == "VentaRechazada" for ev in publicador.eventos_publicados)


def test_flujo_completo_sustitucion_cu03_y_recepcion_cu05():
    # Valida Secuencia 2 (CU-03: SolicitarSustitucion -> ValidarSustitucion -> RegistrarDecisionDelCliente) y CU-05
    hoy = date(2026, 11, 5)
    ventas_repo = MemoriaRepositorioDeVentas()
    inventarios_repo = MemoriaRepositorioDeInventarios()
    productos_repo = MemoriaRepositorioDeProductos()
    sust_repo = MemoriaRepositorioDeSustituciones()
    rec_repo = MemoriaRepositorioDeRecepciones()
    resurt_repo = MemoriaRepositorioDeResurtidos()
    uow = MemoriaUnidadDeTrabajo()
    publicador = MemoriaPublicadorDeEventos()

    prod_orig = Producto("PROD-ORIG", "Original Agotado", TipoDeProducto.MEDICAMENTO, Dinero(Decimal("200.00")), sustitutos_ids=["PROD-ALT"])
    prod_alt = Producto("PROD-ALT", "Alternativa Equivalente", TipoDeProducto.MEDICAMENTO, Dinero(Decimal("180.00")))
    productos_repo.guardar(prod_orig)
    productos_repo.guardar(prod_alt)

    # Ingresar mercancía del producto alternativo por Almacén (CU-05)
    rec_service = RegistrarRecepcionDeMercanciaService(rec_repo, inventarios_repo, uow, publicador, resurt_repo)
    rec_service.ejecutar(
        recepcion_id="REC-10",
        sucursal_id="SUC-01",
        producto_id="PROD-ALT",
        numero_lote="LOTE-ALT-1",
        caducidad=hoy + timedelta(days=90),
        cantidad=15,
        responsable="ALM-01",
        rol_usuario=RolUsuario.ALMACEN.value,
        hoy=hoy,
    )

    # Iniciar venta (CU-01)
    IniciarVentaService(ventas_repo, uow).ejecutar("V-SUST", "CAJ-01", "SUC-01")

    # Consultar alternativas disponibles
    alternativas = ConsultarAlternativasDisponiblesQuery(productos_repo, inventarios_repo).ejecutar("PROD-ORIG", "SUC-01", hoy)
    assert len(alternativas) == 1
    assert alternativas[0]["producto_id"] == "PROD-ALT"

    # Paso 1: Solicitar sustitución
    SolicitarSustitucionService(ventas_repo, sust_repo, uow).ejecutar("SUST-10", "V-SUST", "PROD-ORIG", 2)

    # Paso 2: Validar sustitución por Responsable de Farmacia
    ValidarSustitucionService(sust_repo, uow, publicador).ejecutar(
        solicitud_id="SUST-10",
        alternativa_id="PROD-ALT",
        aprueba=True,
        responsable_id="FARM-01",
        rol_usuario=RolUsuario.RESPONSABLE_FARMACIA.value,
        hoy=hoy,
    )

    # Paso 3: Cliente acepta la alternativa -> se agrega automáticamente a la venta V-SUST
    sol = RegistrarDecisionDelClienteService(
        sust_repo, ventas_repo, inventarios_repo, productos_repo, uow, publicador
    ).ejecutar("SUST-10", True, hoy)

    assert sol.estado == EstadoDeSustitucion.ACEPTADA_POR_CLIENTE
    venta_actualizada = ventas_repo.obtener_por_id("V-SUST")
    assert len(venta_actualizada.lineas) == 1
    assert venta_actualizada.lineas[0].producto_id == "PROD-ALT"
    assert venta_actualizada.total.monto == Decimal("360.00")


def test_diferencias_retiro_resurtido_e_indicadores():
    hoy = date(2026, 11, 5)
    ventas_repo = MemoriaRepositorioDeVentas()
    inventarios_repo = MemoriaRepositorioDeInventarios()
    productos_repo = MemoriaRepositorioDeProductos()
    dif_repo = MemoriaRepositorioDeDiferencias()
    resurt_repo = MemoriaRepositorioDeResurtidos()
    uow = MemoriaUnidadDeTrabajo()
    publicador = MemoriaPublicadorDeEventos()

    productos_repo.guardar(Producto("PROD-01", "Paracetamol", TipoDeProducto.MEDICAMENTO, Dinero(Decimal("100.00"))))
    inventarios_repo.guardar(
        InventarioDeProducto(
            producto_id="PROD-01",
            sucursal_id="SUC-01",
            nivel_minimo=10,
            lotes=[
                Lote(NumeroDeLote("L1"), hoy + timedelta(days=10), Cantidad(5)),
                Lote(NumeroDeLote("L2"), hoy + timedelta(days=100), Cantidad(8)),
            ],
        )
    )

    # Retirar lote L1 por Responsable de Farmacia (US-06) -> la existencia vendible cae a 8 (<10 nivel mínimo)
    RetirarLoteService(inventarios_repo, uow, publicador).ejecutar(
        "PROD-01", "SUC-01", "L1", "FARM-01", "Empaque dañado", RolUsuario.RESPONSABLE_FARMACIA.value, hoy
    )

    # Registrar y autorizar diferencia de inventario en L2 (US-10, BR-13, RF-15)
    RegistrarDiferenciaInventarioService(inventarios_repo, dif_repo, uow, publicador).ejecutar(
        "DIF-10", "PROD-01", "SUC-01", "L2", 6, "Faltante en conteo", "ALM-01", RolUsuario.ALMACEN.value, hoy
    )
    RevisarDiferenciaInventarioService(dif_repo, inventarios_repo, uow, publicador).ejecutar(
        "DIF-10", True, "FARM-01", "Ajuste verificado", RolUsuario.RESPONSABLE_FARMACIA.value, hoy
    )
    assert inventarios_repo.obtener_de("PROD-01", "SUC-01").obtener_lote("L2").cantidad.valor == 6

    # Consultar indicadores consolidados (US-16)
    ind = ConsultarIndicadoresConsolidadosQuery(
        inventarios_repo, productos_repo, dif_repo, resurt_repo, ventas_repo, dias_proximidad=30
    ).ejecutar(hoy)
    assert ind["indicadores"]["IND_01_productos_bajo_nivel_minimo"] == 1
    assert ind["indicadores"]["IND_04_lotes_retirados_bloqueados"] == 1
    assert ind["indicadores"]["IND_05_diferencias_de_inventario"] == 1
