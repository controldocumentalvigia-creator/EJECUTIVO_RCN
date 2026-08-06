# RCN Informe Ejecutivo V8

## Fuente operativa
Hoja `CRUCE_DATA_PAT`.

Campo principal:
- `PAT_ESTADO`

Agrupación:
- Programado por Proveedor → PROGRAMADO
- Cancelada por Solicitante → CANCELADO
- Re-Programado → PROGRAMADO
- Cancelado → CANCELADO
- Programado → PROGRAMADO
- Programado RCN → PROGRAMADO

## Fuente financiera
Hoja `BASE_MAESTRA_RCN`.

La aplicación también acepta `CONSOLIDADO_ASTRANS` como nombre alternativo.

## Incluye
- Operativo desagrupado.
- Operativo agrupado.
- Cancelaciones.
- Producción mensual, bimestral, trimestral y semestral.
- Facturación.
- Costos.
- Margen.
- Rentabilidad.
- Centro de costo.
- Tipo de vehículo.
- Modalidad.
- Origen y destino.
- Trazabilidad.
- Exportación a Excel.

## Streamlit Cloud
- Main file: `app.py`
- Python: `3.11`
