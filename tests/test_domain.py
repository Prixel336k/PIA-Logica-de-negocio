from datetime import date, timedelta
from decimal import Decimal
import pytest

from src.domain import (
    Dinero,
    Cantidad,
    NumeroDeLote,
    FechaDeCaducidad,
    NivelMinimo,
    RequisitoEspecial,
    ResultadoDeOperacion,
    PoliticaFarmaExpress,
    EstadoDelLote,
    EstadoVenta,
    EstadoValidacion,
    EstadoDeSustitucion,
    EstadoDiferenciaInventario,
    EstadoResurtido,
    TipoDeProducto,
    RolUsuario,
    Lote,
    InventarioDeProducto,
    Producto,
    Venta,
    SolicitudDeSustitucion,
    RecepcionDeMercancia,
    DiferenciaDeInventario,
    SolicitudDeResurtido,
    LoteNoCaducado,
    LoteNoRetirado,
    LoteConExistenciaSuficiente,
    LoteProximoACaducarSpec,
    InventarioBajoMinimoSpec,
    VentaListaParaCobroSpec,
    InvalidDomainData,
    InvalidOrderTransition,
    UnauthorizedRoleAction,
)


def test_dinero_invalido_negativo():
    # Verifica que no se puedan crear montos de dinero negativos.
    with pytest.raises(InvalidDomainData):
        Dinero(Decimal("-50.00"))


def test_dinero_operaciones_y_moneda():
    d1 = Dinero(Decimal("100.00"), "MXN")
    d2 = Dinero(Decimal("50.00"), "MXN")
    assert d1.sumar(d2).monto == Decimal("150.00")
    assert d1.por(Cantidad(3)).monto == Decimal("300.00")

    with pytest.raises(InvalidDomainData):
        d1.sumar(Dinero(Decimal("10.00"), "USD"))


def test_cantidad_y_lote_validaciones():
    with pytest.raises(InvalidDomainData):
        Cantidad(-1)
    with pytest.raises(InvalidDomainData):
        Cantidad(2).restar(Cantidad(5))
    with pytest.raises(InvalidDomainData):
        NumeroDeLote("   ")

    c1 = Cantidad(10)
    assert c1.sumar(Cantidad(5)).valor == 15
    assert c1.alcanza_para(Cantidad(10)) is True
    assert c1.alcanza_para(Cantidad(11)) is False


def test_lote_caducado_no_es_vendible():
    # Valida la regla de negocio BR-02: Un lote con fecha vencida no se puede vender.
    hoy = date(2026, 11, 5)
    ayer = hoy - timedelta(days=1)

    lote = Lote(
        numero=NumeroDeLote("LOTE-001"),
        caducidad=ayer,
        cantidad=Cantidad(10),
        estado=EstadoDelLote.DISPONIBLE,
    )

    vendible, motivo = lote.es_vendible(hoy)
    assert vendible is False
    assert "caducado" in motivo.lower()


def test_lote_retirado_no_es_vendible():
    # Valida la regla de negocio BR-03: Un lote marcado como retirado no se puede vender.
    hoy = date(2026, 11, 5)
    mañana = hoy + timedelta(days=1)

    lote = Lote(
        numero=NumeroDeLote("LOTE-002"),
        caducidad=mañana,
        cantidad=Cantidad(10),
        estado=EstadoDelLote.RETIRADO,
    )

    vendible, motivo = lote.es_vendible(hoy)
    assert vendible is False
    assert "retirado" in motivo.lower()


def test_specifications_componibles_y_proximidad_caducidad():
    # Valida el patrón Specification componible (&, |, ~) y BR-11 / BR-12
    hoy = date(2026, 11, 5)
    lote = Lote(
        numero=NumeroDeLote("LOTE-SPEC"),
        caducidad=hoy + timedelta(days=15),
        cantidad=Cantidad(8),
        estado=EstadoDelLote.DISPONIBLE,
    )

    spec_vendible = LoteNoCaducado() & LoteNoRetirado() & LoteConExistenciaSuficiente(5)
    assert spec_vendible.is_satisfied_by(lote, hoy) is True

    spec_proximo = LoteProximoACaducarSpec(dias_alerta=30)
    assert spec_proximo.is_satisfied_by(lote, hoy) is True
    assert (~spec_proximo).is_satisfied_by(lote, hoy) is False

    spec_or = LoteConExistenciaSuficiente(100) | LoteNoRetirado()
    assert spec_or.is_satisfied_by(lote, hoy) is True


def test_inventario_descuenta_correctamente_y_detecta_minimo():
    # Verifica que el inventario controle existencias, descuente y emita ExistenciaBajaDetectada (BR-09).
    hoy = date(2026, 11, 5)
    mañana = hoy + timedelta(days=1)

    lote = Lote(
        numero=NumeroDeLote("LOTE-003"),
        caducidad=mañana,
        cantidad=Cantidad(20),
        estado=EstadoDelLote.DISPONIBLE,
    )

    inventario = InventarioDeProducto(
        producto_id="PROD-01",
        sucursal_id="SUC-01",
        nivel_minimo=5,
        lotes=[lote],
    )

    assert inventario.existencia_total == 20
    assert inventario.esta_por_debajo_del_minimo() is False

    # Descontar 5 unidades (quedan 15)
    inventario.verificar_y_descontar("LOTE-003", 5, hoy)
    assert inventario.existencia_total == 15

    # Descontar 12 unidades (quedan 3, por debajo del mínimo de 5 -> emite evento BR-09)
    inventario.verificar_y_descontar("LOTE-003", 12, hoy)
    assert inventario.existencia_total == 3
    assert InventarioBajoMinimoSpec().is_satisfied_by(inventario, hoy) is True
    assert any(ev.nombre == "ExistenciaBajaDetectada" for ev in inventario.eventos)


def test_venta_calcula_total_y_valida_requisitos_especiales():
    """Verifica el cálculo del total y las reglas BR-04 y BR-05 sobre medicamentos con requisito especial."""
    hoy = date(2026, 11, 5)
    venta = Venta(
        id="V-001",
        cajero_id="CAJ-01",
        sucursal_id="SUC-01",
    )

    prod_antibiotico = Producto(
        id="PROD-02",
        nombre="Amoxicilina 500mg",
        tipo=TipoDeProducto.MEDICAMENTO,
        precio=Dinero(Decimal("100.00")),
        requisito=RequisitoEspecial("Receta médica retenida"),
    )

    venta.agregar_producto(prod_antibiotico, NumeroDeLote("LOTE-003"), Cantidad(2))
    assert venta.total.monto == Decimal("200.00")
    assert venta.estado == EstadoVenta.EN_CAPTURA
    assert VentaListaParaCobroSpec().is_satisfied_by(venta) is False

    # No puede cobrarse mientras esté pendiente (BR-04)
    with pytest.raises(InvalidDomainData):
        venta.puede_cobrarse()

    # El cajero NO está autorizado para aprobar el requisito especial (BR-05)
    with pytest.raises(UnauthorizedRoleAction):
        venta.resolver_validacion("PROD-02", True, "CAJ-01", hoy, rol_usuario=RolUsuario.CAJERO.value)

    # El Responsable de Farmacia aprueba la validación (BR-05, US-03)
    venta.resolver_validacion("PROD-02", True, "FARM-01", hoy, rol_usuario=RolUsuario.RESPONSABLE_FARMACIA.value)
    assert VentaListaParaCobroSpec().is_satisfied_by(venta) is True
    venta.completar(hoy)
    assert venta.estado == EstadoVenta.COMPLETADA

    # State Machine: no se puede volver a completar una venta ya completada
    with pytest.raises(InvalidOrderTransition):
        venta.completar(hoy)


def test_solicitud_sustitucion_y_recepcion_mercancia():
    # Verifica los aggregates SolicitudDeSustitucion (CU-03 / BR-08) y RecepcionDeMercancia (CU-05 / BR-15)
    hoy = date(2026, 11, 5)
    sust = SolicitudDeSustitucion.registrar("SUST-01", "V-01", "PROD-01", Cantidad(1))
    assert sust.estado == EstadoDeSustitucion.REGISTRADA

    with pytest.raises(UnauthorizedRoleAction):
        sust.validar("PROD-04", True, "CAJ-01", hoy, rol_usuario=RolUsuario.CAJERO.value)

    sust.validar("PROD-04", True, "FARM-01", hoy, rol_usuario=RolUsuario.RESPONSABLE_FARMACIA.value)
    assert sust.estado == EstadoDeSustitucion.APROBADA_POR_FARMACIA

    sust.registrar_decision_del_cliente(True, hoy)
    assert sust.esta_aceptada() is True

    # Recepción en almacén rechaza lotes caducados (BR-15)
    rec = RecepcionDeMercancia("REC-01", "SUC-01", "ALM-01", hoy)
    with pytest.raises(InvalidDomainData):
        rec.agregar_linea("PROD-01", NumeroDeLote("LOTE-VENC"), FechaDeCaducidad(hoy - timedelta(days=1)), Cantidad(10), hoy)

    res = rec.agregar_linea("PROD-01", NumeroDeLote("LOTE-OK"), FechaDeCaducidad(hoy + timedelta(days=90)), Cantidad(10), hoy)
    assert res.aceptada is True


def test_diferencia_inventario_y_resurtido_sin_compra_automatica():
    # Verifica BR-13, BR-14 (diferencias y prohibición al cajero) y BR-10 (análisis de Compras)
    hoy = date(2026, 11, 5)
    dif = DiferenciaDeInventario(
        id="DIF-01",
        producto_id="PROD-01",
        sucursal_id="SUC-01",
        numero_lote=NumeroDeLote("LOTE-100"),
        cantidad_registrada=Cantidad(20),
        cantidad_fisica=Cantidad(18),
        motivo="Merma en anaquel",
        reportado_por="ALM-01",
        fecha_reporte=hoy,
    )
    assert dif.diferencia == -2

    # Cajero bloqueado por BR-14
    with pytest.raises(UnauthorizedRoleAction):
        dif.revisar_y_resolver(True, "CAJ-01", "Intento no autorizado", hoy, rol_usuario=RolUsuario.CAJERO.value)

    dif.revisar_y_resolver(True, "FARM-01", "Autorizado por merma documentada", hoy, rol_usuario=RolUsuario.RESPONSABLE_FARMACIA.value)
    assert dif.estado == EstadoDiferenciaInventario.AJUSTE_APROBADO

    # Solicitud de resurtido (BR-09, BR-10)
    resurtido = SolicitudDeResurtido("RES-01", "PROD-01", "SUC-01", existencia_actual=2, nivel_minimo=5)
    resurtido.registrar_decision_compras(
        solicitar_abastecimiento=True,
        analizado_por="COMP-01",
        cantidad_a_solicitar=25,
        justificacion="Reposición necesaria en sucursal centro",
        hoy=hoy,
        rol_usuario=RolUsuario.COMPRAS.value,
    )
    assert resurtido.estado == EstadoResurtido.SOLICITADO_A_PROVEEDOR
    resurtido.marcar_surtido(hoy)
    assert resurtido.estado == EstadoResurtido.SURTIDO
