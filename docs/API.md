Documentación del Contrato API - FarmaExpress

Esta documentación especifica los contratos de interfaz HTTP, esquemas de entrada/salida y códigos de estado implementados en el servicio web FarmaExpress API.

Estándar de Errores y Excepciones

La API utiliza un patrón unificado de manejo de excepciones (run_action y get_venta_or_404) para devolver respuestas claras y estructuradas según las reglas del negocio farmacéutico:

404 Not Found: El recurso (Venta) no existe en el sistema.

409 Conflict: Conflicto de estado en la transacción (ej. intentar modificar o cobrar una venta que ya fue completada).

422 Unprocessable Content: Violación de reglas del dominio o datos inválidos (ej. cantidades negativas, lotes caducados o precios menores a cero).

Especificación de Endpoints

1. Consultar detalles de una venta

Ruta: GET /orders/{venta_id}

Descripción: Devuelve la información detallada de una venta registrada, sus líneas de producto y eventos emitidos.

Respuestas

200 OK

{
  "id": "V-001",
  "cajero_id": "CAJ-01",
  "sucursal_id": "SUC-01",
  "estado": "EN_CAPTURA",
  "total": "500.00",
  "moneda": "MXN",
  "lineas": [
    {
      "producto_id": "PROD-01",
      "lote": "LOTE-100",
      "cantidad": 2,
      "precio_unitario": "250.00",
      "subtotal": "500.00",
      "validacion": "VALIDADA"
    }
  ],
  "eventos": [
    "LineaAgregada"
  ]
}


404 Not Found

{
  "detail": "Lo sentimos, la venta solicitada no se encuentra registrada en el sistema."
}


2. Agregar producto a la venta

Ruta: POST /orders/{venta_id}/lineas

Descripción: Agrega un nuevo ítem a la venta validando reglas de dominio (precios y cantidades positivas).

Cuerpo de la Petición (Request Body)

{
  "producto_id": "PROD-01",
  "numero_lote": "LOTE-100",
  "cantidad": 2,
  "precio_unitario": 250.00
}


Respuestas

200 OK

{
  "mensaje_para_cliente": "Su orden ha sido procesada y confirmada exitosamente.",
  "venta_id": "V-001",
  "estado_actual": "EN_CAPTURA",
  "total": "500.00"
}


422 Unprocessable Content (Cantidad negativa o datos inválidos)

{
  "detail": "Error de validación en las reglas de negocio farmacéutico -> La cantidad debe ser un entero estrictamente positivo (mayor a 0)."
}


404 Not Found

{
  "detail": "Lo sentimos, la venta solicitada no se encuentra registrada en el sistema."
}


3. Completar y cobrar una venta de forma segura

Ruta: POST /orders/{venta_id}/completar

Descripción: Ejecuta el caso de uso CU-04. Procesa el pago simulado, descuenta el inventario del lote correspondiente y marca la venta como completada.

Respuestas

200 OK

{
  "mensaje_para_cliente": "Su orden ha sido procesada y confirmada exitosamente.",
  "venta_id": "V-001",
  "estado_actual": "COMPLETADA",
  "total": "500.00"
}


409 Conflict (Re-ejecución sobre una orden completada)

{
  "detail": "Atención: No se pudo completar la operación debido al estado actual de la venta -> La venta V-001 ya ha sido completada y no admite más cambios de estado."
}


404 Not Found

{
  "detail": "Lo sentimos, la venta solicitada no se encuentra registrada en el sistema."
}


4. Consultar disponibilidad por sucursal

Ruta: GET /inventarios/{producto_id}/{sucursal_id}

Descripción: Permite consultar los lotes disponibles y stock total de un producto en una sucursal específica.

Respuestas

200 OK

{
  "mensaje": "Consulta realizada correctamente.",
  "informacion": {
    "producto_id": "PROD-01",
    "sucursal_id": "SUC-01",
    "stock_total": 20,
    "lotes_disponibles": [
      {
        "lote": "LOTE-100",
        "caducidad": "2027-06-01",
        "cantidad": 20
      }
    ]
  }
}
