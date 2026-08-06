import io
import re
import unicodedata
import hashlib

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="RCN Informe Ejecutivo V8",
    page_icon="📊",
    layout="wide",
)

AZUL = "#003B75"
AZUL_MEDIO = "#0B4F8C"
ROJO = "#D43D3D"
NARANJA = "#F58220"
VERDE = "#008A3D"
GRIS = "#667085"
TEXTO = "#1F1F1F"

st.markdown("""
<style>
html,body,[class*="css"]{font-family:"Segoe UI",Arial,sans-serif;color:#1F1F1F!important}
.block-container{padding-top:1rem;padding-left:1.2rem;padding-right:1.2rem}
h1,h2,h3{color:#003B75!important;font-weight:800!important}
.kpi{background:#fff;border:1px solid #DDE3EE;border-radius:12px;padding:10px 12px;
min-height:88px;box-shadow:0 1px 6px rgba(0,0,0,.06);margin-bottom:8px}
.kpi-title{color:#003B75;font-size:.70rem;font-weight:800;text-transform:uppercase}
.kpi-value{color:#101828;font-size:1.08rem;font-weight:800;line-height:1.2;margin-top:4px}
.kpi-note{font-size:.70rem;color:#667085;margin-top:4px}
[data-testid="stDataFrame"] div[role="columnheader"]{
background-color:#003B75!important;color:#fff!important;font-weight:800!important;
justify-content:center!important;text-align:center!important}
[data-testid="stDataFrame"] div[role="gridcell"]{
justify-content:center!important;text-align:center!important;color:#1F1F1F!important}
</style>
""", unsafe_allow_html=True)


# ============================================================
# UTILIDADES
# ============================================================
def sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(texto))
        if not unicodedata.combining(c)
    )


def normalizar_columna(valor) -> str:
    texto = sin_acentos(str(valor)).upper().strip()
    texto = re.sub(r"[^A-Z0-9]+", "_", texto)
    return texto.strip("_")


def normalizar_texto(valor) -> str:
    if pd.isna(valor):
        return ""
    return sin_acentos(str(valor)).upper().strip()


def buscar_columna(df: pd.DataFrame, candidatos):
    mapa = {normalizar_columna(c): c for c in df.columns}
    for candidato in candidatos:
        clave = normalizar_columna(candidato)
        if clave in mapa:
            return mapa[clave]
    return None


def convertir_fecha(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, errors="coerce", dayfirst=True)


def convertir_numero(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce").fillna(0)

    texto = serie.astype(str).str.upper().str.strip()
    texto = texto.str.replace("COP", "", regex=False)
    texto = texto.str.replace("$", "", regex=False)
    texto = texto.str.replace(" ", "", regex=False)

    tiene_coma = texto.str.contains(",", regex=False)
    texto.loc[tiene_coma] = (
        texto.loc[tiene_coma]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    texto.loc[~tiene_coma] = texto.loc[~tiene_coma].str.replace(",", "", regex=False)
    return pd.to_numeric(texto, errors="coerce").fillna(0)


def moneda(valor) -> str:
    try:
        return "$ " + f"{float(valor):,.0f}".replace(",", ".") + " COP"
    except Exception:
        return "$ 0 COP"


def porcentaje(valor) -> str:
    try:
        return f"{float(valor):.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"


def entero(valor) -> str:
    try:
        return f"{int(round(float(valor))):,}".replace(",", ".")
    except Exception:
        return "0"


def kpi(titulo, valor, nota=""):
    st.markdown(
        f'<div class="kpi"><div class="kpi-title">{titulo}</div>'
        f'<div class="kpi-value">{valor}</div>'
        f'<div class="kpi-note">{nota}</div></div>',
        unsafe_allow_html=True,
    )


def aplicar_estilo(fig, titulo, alto=450):
    fig.update_layout(
        title=titulo,
        height=alto,
        font=dict(color=TEXTO, family="Segoe UI"),
        title_font=dict(color=AZUL, size=18),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=35, r=35, t=65, b=55),
        xaxis=dict(tickfont=dict(color=TEXTO), title_font=dict(color=TEXTO)),
        yaxis=dict(tickfont=dict(color=TEXTO), title_font=dict(color=TEXTO)),
        legend=dict(font=dict(color=TEXTO)),
    )
    return fig


def agregar_periodos(df, fecha_col):
    temp = df.copy()
    fecha = convertir_fecha(temp[fecha_col])
    temp["AÑO"] = fecha.dt.year
    temp["MES_NUM"] = fecha.dt.month
    temp["AÑO_MES"] = fecha.dt.to_period("M").astype(str)
    temp["AÑO_BIMESTRE"] = (
        temp["AÑO"].astype("Int64").astype(str)
        + "-B"
        + (((temp["MES_NUM"] - 1) // 2) + 1).astype("Int64").astype(str)
    )
    temp["AÑO_TRIMESTRE"] = (
        temp["AÑO"].astype("Int64").astype(str)
        + "-T"
        + (((temp["MES_NUM"] - 1) // 3) + 1).astype("Int64").astype(str)
    )
    temp["AÑO_SEMESTRE"] = (
        temp["AÑO"].astype("Int64").astype(str)
        + "-S"
        + (((temp["MES_NUM"] - 1) // 6) + 1).astype("Int64").astype(str)
    )
    return temp


def resumen_categoria(df, columna):
    if not columna or columna not in df.columns or df.empty:
        return pd.DataFrame(columns=[columna or "CATEGORIA", "CANTIDAD", "PARTICIPACION_%"])

    out = (
        df.groupby(columna, dropna=False)
        .size()
        .reset_index(name="CANTIDAD")
        .sort_values("CANTIDAD", ascending=False)
    )
    total = out["CANTIDAD"].sum()
    out["PARTICIPACION_%"] = out["CANTIDAD"] / total * 100 if total else 0
    return out


def agrupar_estado_pat(valor):
    estado = normalizar_texto(valor).replace("-", " ")

    mapa = {
        "PROGRAMADO POR PROVEEDOR": "PROGRAMADO",
        "CANCELADA POR SOLICITANTE": "CANCELADO",
        "RE PROGRAMADO": "PROGRAMADO",
        "REPROGRAMADO": "PROGRAMADO",
        "CANCELADO": "CANCELADO",
        "PROGRAMADO": "PROGRAMADO",
        "PROGRAMADO RCN": "PROGRAMADO",
        "LIQUIDADO": "PROGRAMADO",
        "PRELIQUIDADO": "PROGRAMADO",
    }

    if estado in mapa:
        return mapa[estado]
    if "CANCEL" in estado:
        return "CANCELADO"

    # Todo estado no cancelado representa una solicitud programada
    # dentro del histórico operativo de DATA.
    return "PROGRAMADO"


def etiqueta_variacion(actual, anterior, tipo="numero"):
    if pd.isna(anterior) or anterior == 0:
        var_txt = "Base"
    else:
        variacion = (actual / anterior - 1) * 100
        flecha = "▲" if variacion > 0 else "▼" if variacion < 0 else "▬"
        var_txt = f"{flecha} {porcentaje(variacion)}"

    valor_txt = moneda(actual) if tipo == "moneda" else entero(actual)
    return f"{valor_txt}<br>{var_txt}"


def barras_variacion(df, periodo_col, valor_col, titulo, tipo="numero", color=AZUL):
    data = df.copy()
    data["ETIQUETA"] = [
        etiqueta_variacion(a, b, tipo)
        for a, b in zip(data[valor_col], data[valor_col].shift(1))
    ]
    fig = px.bar(data, x=periodo_col, y=valor_col, text="ETIQUETA")
    fig.update_traces(
        marker_color=color,
        textposition="outside",
        textfont=dict(color=TEXTO, size=10),
    )
    return aplicar_estilo(fig, titulo, 480)


def dona(df, columna, titulo, top_n=10):
    data = resumen_categoria(df, columna).head(top_n)
    fig = px.pie(data, names=columna, values="CANTIDAD", hole=0.48)
    fig.update_traces(textinfo="percent+label")
    return aplicar_estilo(fig, titulo)


def pareto(df, columna, titulo, top_n=20):
    data = resumen_categoria(df, columna).head(top_n).copy()
    data["ACUMULADO_%"] = data["PARTICIPACION_%"].cumsum()

    fig = go.Figure()
    fig.add_bar(
        x=data[columna],
        y=data["CANTIDAD"],
        text=data["CANTIDAD"],
        textposition="auto",
        marker_color=AZUL,
        name="Cantidad",
    )
    fig.add_trace(
        go.Scatter(
            x=data[columna],
            y=data["ACUMULADO_%"],
            yaxis="y2",
            mode="lines+markers+text",
            text=[porcentaje(v) for v in data["ACUMULADO_%"]],
            textposition="top center",
            line=dict(color=NARANJA, width=3),
            name="% acumulado",
        )
    )
    fig.add_hline(y=80, yref="y2", line_dash="dash", line_color=ROJO)
    fig.update_layout(
        yaxis2=dict(
            overlaying="y",
            side="right",
            range=[0, 110],
            title="% acumulado",
        )
    )
    return aplicar_estilo(fig, titulo, 520)


def exportar_excel(hojas: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter", datetime_format="dd/mm/yyyy hh:mm") as writer:
        formato_header = writer.book.add_format({
            "bold": True,
            "font_color": "white",
            "bg_color": AZUL,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })

        for nombre, df in hojas.items():
            hoja = nombre[:31]
            df.to_excel(writer, index=False, sheet_name=hoja)
            ws = writer.sheets[hoja]
            ws.freeze_panes(1, 0)
            if len(df.columns):
                ws.autofilter(0, 0, len(df), len(df.columns) - 1)
                for col_idx, col in enumerate(df.columns):
                    ws.write(0, col_idx, col, formato_header)
                    ancho = min(max(len(str(col)) + 3, 14), 32)
                    ws.set_column(col_idx, col_idx, ancho)
    return buffer.getvalue()


# ============================================================
# CARGA DEL LIBRO
# ============================================================
st.title("📊 RCN Informe Ejecutivo V8")
st.caption(
    "Operativo histórico desde DATA en CRUCE_DATA_PAT · "
    "Financiero desde BASE_MAESTRA_RCN"
)

archivo = st.file_uploader(
    "Cargar BASE_MAESTRA_RCN.xlsx generada por RCN Data Factory",
    type=["xlsx"],
)

if not archivo:
    st.warning("Carga la Base Maestra para generar el informe.")
    st.stop()

try:
    archivo_bytes = archivo.getvalue()
    firma_archivo = hashlib.md5(archivo_bytes).hexdigest()[:10]

    xls = pd.ExcelFile(io.BytesIO(archivo_bytes))

    if "CRUCE_DATA_PAT" not in xls.sheet_names:
        raise ValueError("El archivo no contiene la hoja CRUCE_DATA_PAT.")

    hoja_financiera = (
        "BASE_MAESTRA_RCN"
        if "BASE_MAESTRA_RCN" in xls.sheet_names
        else "CONSOLIDADO_ASTRANS"
        if "CONSOLIDADO_ASTRANS" in xls.sheet_names
        else None
    )

    if hoja_financiera is None:
        raise ValueError(
            "El archivo debe contener BASE_MAESTRA_RCN o CONSOLIDADO_ASTRANS."
        )

    operativo = pd.read_excel(io.BytesIO(archivo_bytes), sheet_name="CRUCE_DATA_PAT")
    financiero = pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=hoja_financiera)

except Exception as exc:
    st.error(f"No fue posible leer el libro: {exc}")
    st.stop()


# ============================================================
# PREPARACIÓN OPERATIVA
# ============================================================
operativo_fecha_col = buscar_columna(
    operativo,
    ["DATA_FECHA_SERVICIO", "PAT_FECHA_SERVICIO"],
)
operativo_estado_col = buscar_columna(
    operativo,
    ["DATA_ESTADO_SERVICIO", "PAT_ESTADO"],
)

if not operativo_fecha_col or not operativo_estado_col:
    st.error(
        "CRUCE_DATA_PAT debe contener DATA_FECHA_SERVICIO y "
        "DATA_ESTADO_SERVICIO, o sus equivalentes PAT."
    )
    st.stop()

operativo = agregar_periodos(
    operativo,
    operativo_fecha_col,
)
operativo["ESTADO_OPERATIVO_DETALLE"] = (
    operativo[operativo_estado_col]
    .fillna("Sin dato")
    .astype(str)
)
operativo["ESTADO_OPERATIVO_AGRUPADO"] = (
    operativo[operativo_estado_col]
    .apply(agrupar_estado_pat)
)

# Alias de compatibilidad para las gráficas existentes.
pat_fecha_col = operativo_fecha_col
pat_estado_col = operativo_estado_col
operativo["PAT_ESTADO_DETALLE"] = operativo["ESTADO_OPERATIVO_DETALLE"]
operativo["PAT_ESTADO_AGRUPADO"] = operativo["ESTADO_OPERATIVO_AGRUPADO"]

op_centro_col = buscar_columna(
    operativo,
    ["PAT_CENTRO_ORDEN_COSTO", "DATA_CENTRO_ORDEN_COSTO"],
)
op_modalidad_col = buscar_columna(
    operativo,
    ["PAT_MODALIDAD", "DATA_MODALIDAD"],
)
op_vehiculo_col = buscar_columna(
    operativo,
    ["DATA_TIPO_VEHICULO"],
)
op_origen_col = buscar_columna(
    operativo,
    ["PAT_ORIGEN", "DATA_ORIGEN"],
)
op_destino_col = buscar_columna(
    operativo,
    ["PAT_DESTINO", "DATA_DESTINO"],
)


# ============================================================
# PREPARACIÓN FINANCIERA
# ============================================================
fin_fecha_col = buscar_columna(
    financiero,
    ["ASTRANS_CARGA_FECHA", "CARGA"],
)
if not fin_fecha_col:
    st.error("BASE_MAESTRA_RCN no contiene ASTRANS_CARGA_FECHA ni CARGA.")
    st.stop()

financiero = agregar_periodos(financiero, fin_fecha_col)

vcliente_col = buscar_columna(
    financiero,
    ["V_CLIENTE_NUM", "V.CLIENTE", "V CLIENTE"],
)
vconduct_col = buscar_columna(
    financiero,
    ["V_CONDUCT_NUM", "V.CONDUCT", "V CONDUCT"],
)

financiero["FACTURACION_NUM"] = (
    convertir_numero(financiero[vcliente_col])
    if vcliente_col
    else 0
)
financiero["COSTO_NUM"] = (
    convertir_numero(financiero[vconduct_col])
    if vconduct_col
    else 0
)
financiero["MARGEN_NUM"] = (
    financiero["FACTURACION_NUM"] - financiero["COSTO_NUM"]
)

fin_centro_col = buscar_columna(
    financiero,
    ["DATA_CENTRO_ORDEN_COSTO", "PAT_CENTRO_ORDEN_COSTO", "LINEA NEG"],
)
fin_vehiculo_col = buscar_columna(
    financiero,
    ["DATA_TIPO_VEHICULO", "T. VEHICULO", "T VEHICULO"],
)
fin_modalidad_col = buscar_columna(
    financiero,
    ["DATA_MODALIDAD", "PAT_MODALIDAD"],
)
fin_origen_col = buscar_columna(
    financiero,
    ["DATA_ORIGEN", "PAT_ORIGEN", "ORIGEN"],
)
fin_destino_col = buscar_columna(
    financiero,
    ["DATA_DESTINO", "PAT_DESTINO", "DESTINO"],
)
trazabilidad_col = buscar_columna(
    financiero,
    ["ESTADO_TRAZABILIDAD"],
)
resultado_col = buscar_columna(
    financiero,
    ["RESULTADO_SERVICIO"],
)


# ============================================================
# FILTROS
# ============================================================
with st.sidebar:
    st.header("🔎 Filtros del informe")

    if st.button(
        "Restablecer filtros",
        key=f"reset_{firma_archivo}",
        use_container_width=True,
    ):
        claves_eliminar = [
            clave
            for clave in list(st.session_state.keys())
            if clave.startswith(f"v8_{firma_archivo}_")
        ]
        for clave in claves_eliminar:
            del st.session_state[clave]
        st.rerun()

    meses_operativos = sorted(
        operativo["AÑO_MES"]
        .dropna()
        .astype(str)
        .loc[lambda s: s.ne("NaT")]
        .unique()
    )

    meses_financieros = sorted(
        financiero["AÑO_MES"]
        .dropna()
        .astype(str)
        .loc[lambda s: s.ne("NaT")]
        .unique()
    )

    meses_disponibles = meses_operativos

    meses = st.multiselect(
        "Meses",
        meses_disponibles,
        default=meses_disponibles,
        key=f"v8_{firma_archivo}_meses",
        help=(
            "El análisis operativo toma todos los meses disponibles "
            "en DATA dentro de CRUCE_DATA_PAT."
        ),
    )

    # Si el usuario elimina accidentalmente todos los meses,
    # se restablece el histórico completo para evitar resultados en cero.
    if not meses:
        meses = meses_disponibles
        st.info("Se aplicaron nuevamente todos los meses disponibles.")

    periodicidades = {
        "Mensual": "AÑO_MES",
        "Bimestral": "AÑO_BIMESTRE",
        "Trimestral": "AÑO_TRIMESTRE",
        "Semestral": "AÑO_SEMESTRE",
    }
    periodicidad_nombre = st.selectbox(
        "Periodicidad",
        list(periodicidades.keys()),
        key=f"v8_{firma_archivo}_periodicidad",
    )
    periodo_col = periodicidades[periodicidad_nombre]

    estados_detalle_opciones = sorted(
        x
        for x in operativo["PAT_ESTADO_DETALLE"]
        .dropna()
        .astype(str)
        .unique()
        if x and x.lower() != "nan"
    )
    estados_detalle = st.multiselect(
        "Estado operativo detallado",
        estados_detalle_opciones,
        key=f"v8_{firma_archivo}_estado_detalle",
    )

    estados_agrupados_opciones = sorted(
        operativo["PAT_ESTADO_AGRUPADO"]
        .dropna()
        .astype(str)
        .unique()
    )
    estados_agrupados = st.multiselect(
        "Estado operativo agrupado",
        estados_agrupados_opciones,
        key=f"v8_{firma_archivo}_estado_agrupado",
    )

    centros = []
    if op_centro_col:
        centros_opciones = sorted(
            x
            for x in operativo[op_centro_col]
            .dropna()
            .astype(str)
            .unique()
            if x and x.lower() != "nan"
        )
        centros = st.multiselect(
            "Centro / Orden Costo",
            centros_opciones,
            key=f"v8_{firma_archivo}_centros",
        )

    vehiculos = []
    if op_vehiculo_col:
        vehiculos_opciones = sorted(
            x
            for x in operativo[op_vehiculo_col]
            .dropna()
            .astype(str)
            .unique()
            if x and x.lower() != "nan"
        )
        vehiculos = st.multiselect(
            "Tipo de vehículo",
            vehiculos_opciones,
            key=f"v8_{firma_archivo}_vehiculos",
        )

    modalidades = []
    if op_modalidad_col:
        modalidades_opciones = sorted(
            x
            for x in operativo[op_modalidad_col]
            .dropna()
            .astype(str)
            .unique()
            if x and x.lower() != "nan"
        )
        modalidades = st.multiselect(
            "Modalidad",
            modalidades_opciones,
            key=f"v8_{firma_archivo}_modalidades",
        )

    st.caption(
        f"Meses DATA: {len(meses_operativos)} · "
        f"Meses financieros: {len(meses_financieros)}"
    )


operativo_f = operativo[operativo["AÑO_MES"].isin(meses)].copy()
financiero_f = financiero[financiero["AÑO_MES"].isin(meses)].copy()

if estados_detalle:
    operativo_f = operativo_f[
        operativo_f["PAT_ESTADO_DETALLE"].isin(estados_detalle)
    ]
if estados_agrupados:
    operativo_f = operativo_f[
        operativo_f["PAT_ESTADO_AGRUPADO"].isin(estados_agrupados)
    ]
if centros and op_centro_col:
    operativo_f = operativo_f[
        operativo_f[op_centro_col].astype(str).isin(centros)
    ]
if vehiculos and op_vehiculo_col:
    operativo_f = operativo_f[
        operativo_f[op_vehiculo_col].astype(str).isin(vehiculos)
    ]
if modalidades and op_modalidad_col:
    operativo_f = operativo_f[
        operativo_f[op_modalidad_col].astype(str).isin(modalidades)
    ]

if operativo_f.empty:
    st.error(
        "Los filtros dejaron el análisis operativo sin registros. "
        "Pulsa 'Restablecer filtros' en la barra lateral."
    )
    st.stop()

if financiero_f.empty:
    st.warning(
        "No existen registros financieros para los meses seleccionados. "
        "El análisis operativo continuará mostrando los datos de DATA."
    )


# ============================================================
# RESÚMENES
# ============================================================
operativo_periodo = (
    operativo_f.groupby(periodo_col, as_index=False)
    .size()
    .rename(columns={"size": "SERVICIOS"})
    .sort_values(periodo_col)
)
operativo_periodo["VAR_%"] = operativo_periodo["SERVICIOS"].pct_change() * 100
operativo_periodo["ACUMULADO"] = operativo_periodo["SERVICIOS"].cumsum()

detalle_res = resumen_categoria(operativo_f, "PAT_ESTADO_DETALLE")
agrupado_res = resumen_categoria(operativo_f, "PAT_ESTADO_AGRUPADO")

total_servicios = int(len(operativo_f))

total_programados = int(
    (operativo_f["PAT_ESTADO_AGRUPADO"] == "PROGRAMADO").sum()
)
total_cancelados = int(
    (operativo_f["PAT_ESTADO_AGRUPADO"] == "CANCELADO").sum()
)
total_otros = int(
    total_servicios - total_programados - total_cancelados
)

pct_programados = (
    total_programados / total_servicios * 100
    if total_servicios
    else 0
)
pct_cancelados = (
    total_cancelados / total_servicios * 100
    if total_servicios
    else 0
)

# Promedio diario calculado con los días únicos del periodo operativo filtrado.
dias_operativos = int(
    operativo_f[pat_fecha_col]
    .dropna()
    .dt.normalize()
    .nunique()
)
promedio_diario = (
    total_servicios / dias_operativos
    if dias_operativos
    else 0
)

# Alias internos para conservar compatibilidad con el resto del dashboard.
programados = total_programados
cancelados = total_cancelados
otros = total_otros
total_operativo = total_servicios
pct_programado = pct_programados
pct_cancelado = pct_cancelados

fin_periodo = (
    financiero_f.groupby(periodo_col, as_index=False)
    .agg(
        SERVICIOS=(fin_fecha_col, "count"),
        FACTURACION=("FACTURACION_NUM", "sum"),
        COSTOS=("COSTO_NUM", "sum"),
        MARGEN=("MARGEN_NUM", "sum"),
    )
    .sort_values(periodo_col)
)
fin_periodo["RENTABILIDAD_%"] = np.where(
    fin_periodo["FACTURACION"] != 0,
    fin_periodo["MARGEN"] / fin_periodo["FACTURACION"] * 100,
    0,
)
fin_periodo["VAR_FACTURACION_%"] = fin_periodo["FACTURACION"].pct_change() * 100
fin_periodo["VAR_SERVICIOS_%"] = fin_periodo["SERVICIOS"].pct_change() * 100

facturacion = float(financiero_f["FACTURACION_NUM"].sum())
costos = float(financiero_f["COSTO_NUM"].sum())
margen = facturacion - costos
rentabilidad = margen / facturacion * 100 if facturacion else 0

remesa_col = buscar_columna(
    financiero_f,
    ["ASTRANS_REMESA_NORM", "REMESA"],
)
if remesa_col:
    servicios_ejecutados = int(
        financiero_f[remesa_col]
        .replace("", np.nan)
        .dropna()
        .astype(str)
        .nunique()
    )
else:
    servicios_ejecutados = int(len(financiero_f))

ticket = (
    facturacion / servicios_ejecutados
    if servicios_ejecutados
    else 0
)


# ============================================================
# DASHBOARD
# ============================================================
tabs = st.tabs([
    "🏢 Resumen Ejecutivo",
    "📋 Operativo Desagrupado",
    "📊 Operativo Agrupado",
    "❌ Cancelaciones",
    "📈 Producción",
    "💰 Financiero",
    "🎬 Centro de costo",
    "🚙 Vehículo y modalidad",
    "🗺 Origen y destino",
    "🔗 Trazabilidad",
    "📥 Exportar informe",
])


with tabs[0]:
    st.subheader("Resumen Ejecutivo RCN")

    st.caption(
        f"Periodo operativo seleccionado: {', '.join(meses)} · "
        f"Registros CRUCE_DATA_PAT: {entero(len(operativo_f))} · "
        f"Registros BASE_MAESTRA_RCN: {entero(len(financiero_f))}"
    )

    st.markdown("### Resumen operativo")
    cols = st.columns(6)
    with cols[0]:
        kpi("Total servicios", entero(total_servicios), "CRUCE_DATA_PAT")
    with cols[1]:
        kpi("Total programados", entero(total_programados), porcentaje(pct_programados))
    with cols[2]:
        kpi("Total cancelados", entero(total_cancelados), porcentaje(pct_cancelados))
    with cols[3]:
        kpi("% programados", porcentaje(pct_programados))
    with cols[4]:
        kpi("% cancelados", porcentaje(pct_cancelados))
    with cols[5]:
        kpi("Promedio diario", f"{promedio_diario:.1f}")

    st.markdown("### Resumen financiero")
    cols2 = st.columns(6)
    with cols2[0]:
        kpi("Servicios ejecutados", entero(servicios_ejecutados), "Remesas únicas")
    with cols2[1]:
        kpi("Facturación", moneda(facturacion))
    with cols2[2]:
        kpi("Costos", moneda(costos))
    with cols2[3]:
        kpi("Margen", moneda(margen))
    with cols2[4]:
        kpi("Rentabilidad", porcentaje(rentabilidad))
    with cols2[5]:
        kpi("Ticket promedio", moneda(ticket))

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            barras_variacion(
                operativo_periodo,
                periodo_col,
                "SERVICIOS",
                f"Producción operativa {periodicidad_nombre.lower()}",
            ),
            use_container_width=True,
        )
    with c2:
        fig = go.Figure()
        fig.add_bar(
            x=fin_periodo[periodo_col],
            y=fin_periodo["SERVICIOS"],
            text=fin_periodo["SERVICIOS"],
            textposition="outside",
            marker_color=AZUL,
            name="Servicios ejecutados",
        )
        fig.add_trace(
            go.Scatter(
                x=fin_periodo[periodo_col],
                y=fin_periodo["FACTURACION"],
                yaxis="y2",
                mode="lines+markers",
                line=dict(color=NARANJA, width=4),
                name="Facturación",
            )
        )
        fig.update_layout(
            yaxis2=dict(
                overlaying="y",
                side="right",
                title="Facturación",
            )
        )
        st.plotly_chart(
            aplicar_estilo(fig, "Producción ejecutada vs facturación", 500),
            use_container_width=True,
        )

    st.markdown("### Lectura ejecutiva")
    if not operativo_periodo.empty:
        mayor = operativo_periodo.loc[
            operativo_periodo["SERVICIOS"].idxmax()
        ]
        ultima_var = operativo_periodo["VAR_%"].iloc[-1]
        st.write(
            f"Durante el periodo analizado se registraron **{entero(total_operativo)} solicitudes operativas**. "
            f"El **{porcentaje(pct_programado)}** quedó clasificado como programado y el "
            f"**{porcentaje(pct_cancelado)}** como cancelado. El mayor volumen se presentó en "
            f"**{mayor[periodo_col]}**, con **{entero(mayor['SERVICIOS'])} servicios**. "
            f"La variación del último periodo fue **{porcentaje(ultima_var) if pd.notna(ultima_var) else 'Base'}**."
        )

    st.write(
        f"La base financiera registra **{entero(servicios_ejecutados)} remesas únicas ejecutadas**, "
        f"una facturación de **{moneda(facturacion)}**, costos por **{moneda(costos)}** y un margen de "
        f"**{moneda(margen)}**, equivalente a una rentabilidad de **{porcentaje(rentabilidad)}**. "
        f"Esta separación permite analizar la programación desde CRUCE_DATA_PAT y el resultado económico "
        f"exclusivamente desde BASE_MAESTRA_RCN."
    )


with tabs[1]:
    st.subheader("Análisis operativo desagrupado")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            detalle_res,
            x="PAT_ESTADO_DETALLE",
            y="CANTIDAD",
            text="CANTIDAD",
        )
        fig.update_traces(
            marker_color=AZUL,
            textposition="outside",
        )
        st.plotly_chart(
            aplicar_estilo(fig, "Estado operativo detallado", 500),
            use_container_width=True,
        )

    with c2:
        fig = px.pie(
            detalle_res,
            names="PAT_ESTADO_DETALLE",
            values="CANTIDAD",
            hole=0.45,
        )
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(
            aplicar_estilo(fig, "Participación por estado detallado"),
            use_container_width=True,
        )

    detalle_mes = (
        operativo_f.groupby(
            ["AÑO_MES", "PAT_ESTADO_DETALLE"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "SERVICIOS"})
    )
    fig = px.bar(
        detalle_mes,
        x="AÑO_MES",
        y="SERVICIOS",
        color="PAT_ESTADO_DETALLE",
        barmode="group",
        text="SERVICIOS",
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(
        aplicar_estilo(fig, "Evolución mensual del estado operativo detallado", 540),
        use_container_width=True,
    )

    detalle_show = detalle_res.copy()
    detalle_show["PARTICIPACION_%"] = detalle_show["PARTICIPACION_%"].apply(porcentaje)
    st.dataframe(detalle_show, use_container_width=True, hide_index=True)


with tabs[2]:
    st.subheader("Análisis operativo agrupado")

    cols = st.columns(3)
    with cols[0]:
        kpi("PROGRAMADO", entero(programados), porcentaje(pct_programado))
    with cols[1]:
        kpi("CANCELADO", entero(cancelados), porcentaje(pct_cancelado))
    with cols[2]:
        kpi("OTRO", entero(otros))

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            agrupado_res,
            x="PAT_ESTADO_AGRUPADO",
            y="CANTIDAD",
            text="CANTIDAD",
            color="PAT_ESTADO_AGRUPADO",
            color_discrete_map={
                "PROGRAMADO": VERDE,
                "CANCELADO": ROJO,
                "OTRO": GRIS,
            },
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(
            aplicar_estilo(fig, "Estado operativo agrupado"),
            use_container_width=True,
        )

    with c2:
        fig = px.pie(
            agrupado_res,
            names="PAT_ESTADO_AGRUPADO",
            values="CANTIDAD",
            hole=0.45,
            color="PAT_ESTADO_AGRUPADO",
            color_discrete_map={
                "PROGRAMADO": VERDE,
                "CANCELADO": ROJO,
                "OTRO": GRIS,
            },
        )
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(
            aplicar_estilo(fig, "Participación agrupada"),
            use_container_width=True,
        )

    agrupado_periodo = (
        operativo_f.groupby(
            [periodo_col, "PAT_ESTADO_AGRUPADO"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "SERVICIOS"})
    )

    fig = px.bar(
        agrupado_periodo,
        x=periodo_col,
        y="SERVICIOS",
        color="PAT_ESTADO_AGRUPADO",
        barmode="group",
        text="SERVICIOS",
        color_discrete_map={
            "PROGRAMADO": VERDE,
            "CANCELADO": ROJO,
            "OTRO": GRIS,
        },
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(
        aplicar_estilo(
            fig,
            f"Evolución {periodicidad_nombre.lower()} del estado agrupado",
            520,
        ),
        use_container_width=True,
    )


with tabs[3]:
    st.subheader("Análisis de cancelaciones")

    cancel_df = operativo_f[
        operativo_f["PAT_ESTADO_AGRUPADO"] == "CANCELADO"
    ].copy()

    cancel_res = resumen_categoria(cancel_df, "PAT_ESTADO_DETALLE")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            cancel_res,
            x="PAT_ESTADO_DETALLE",
            y="CANTIDAD",
            text="CANTIDAD",
        )
        fig.update_traces(
            marker_color=ROJO,
            textposition="outside",
        )
        st.plotly_chart(
            aplicar_estilo(fig, "Cancelaciones por estado detallado"),
            use_container_width=True,
        )

    with c2:
        cancel_periodo = (
            operativo_f.groupby(periodo_col, as_index=False)
            .agg(
                TOTAL=("PAT_ESTADO_AGRUPADO", "count"),
                CANCELADOS=(
                    "PAT_ESTADO_AGRUPADO",
                    lambda s: (s == "CANCELADO").sum(),
                ),
            )
            .sort_values(periodo_col)
        )
        cancel_periodo["%_CANCELACION"] = np.where(
            cancel_periodo["TOTAL"] != 0,
            cancel_periodo["CANCELADOS"] / cancel_periodo["TOTAL"] * 100,
            0,
        )

        fig = go.Figure()
        fig.add_bar(
            x=cancel_periodo[periodo_col],
            y=cancel_periodo["CANCELADOS"],
            text=cancel_periodo["CANCELADOS"],
            textposition="outside",
            marker_color=ROJO,
            name="Cancelados",
        )
        fig.add_trace(
            go.Scatter(
                x=cancel_periodo[periodo_col],
                y=cancel_periodo["%_CANCELACION"],
                yaxis="y2",
                mode="lines+markers+text",
                text=[
                    porcentaje(v)
                    for v in cancel_periodo["%_CANCELACION"]
                ],
                textposition="top center",
                line=dict(color=NARANJA, width=4),
                name="% cancelación",
            )
        )
        fig.update_layout(
            yaxis2=dict(
                overlaying="y",
                side="right",
                title="% cancelación",
            )
        )
        st.plotly_chart(
            aplicar_estilo(fig, "Pérdidas operativas y % cancelación", 500),
            use_container_width=True,
        )

    if op_centro_col and not cancel_df.empty:
        st.plotly_chart(
            pareto(
                cancel_df,
                op_centro_col,
                "Pareto de cancelaciones por Centro / Orden Costo",
            ),
            use_container_width=True,
        )

    st.write(
        f"Se identificaron **{entero(cancelados)} servicios cancelados**, equivalentes al "
        f"**{porcentaje(pct_cancelado)}** de las solicitudes operativas filtradas. "
        f"El análisis desagregado permite distinguir entre cancelaciones directas y cancelaciones "
        f"originadas por el solicitante. El Pareto por centro de costo permite concentrar los planes "
        f"de mejora en las producciones con mayor recurrencia."
    )


with tabs[4]:
    st.subheader("Producción ejecutada")

    fin_prod = fin_periodo[[
        periodo_col,
        "SERVICIOS",
        "VAR_SERVICIOS_%",
    ]].copy()

    st.plotly_chart(
        barras_variacion(
            fin_prod,
            periodo_col,
            "SERVICIOS",
            f"Producción ejecutada {periodicidad_nombre.lower()}",
        ),
        use_container_width=True,
    )

    fin_prod_mostrar = fin_prod.copy()
    fin_prod_mostrar["VAR_SERVICIOS_%"] = (
        fin_prod_mostrar["VAR_SERVICIOS_%"].apply(porcentaje)
    )
    st.dataframe(
        fin_prod_mostrar,
        use_container_width=True,
        hide_index=True,
    )


with tabs[5]:
    st.subheader("Análisis financiero")

    cols = st.columns(5)
    with cols[0]:
        kpi("Facturación", moneda(facturacion))
    with cols[1]:
        kpi("Costos", moneda(costos))
    with cols[2]:
        kpi("Margen", moneda(margen))
    with cols[3]:
        kpi("Rentabilidad", porcentaje(rentabilidad))
    with cols[4]:
        kpi("Ticket promedio", moneda(ticket))

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            barras_variacion(
                fin_periodo,
                periodo_col,
                "FACTURACION",
                f"Facturación {periodicidad_nombre.lower()}",
                tipo="moneda",
            ),
            use_container_width=True,
        )

    with c2:
        st.plotly_chart(
            barras_variacion(
                fin_periodo,
                periodo_col,
                "MARGEN",
                f"Margen {periodicidad_nombre.lower()}",
                tipo="moneda",
                color=VERDE,
            ),
            use_container_width=True,
        )

    st.dataframe(fin_periodo, use_container_width=True, hide_index=True)


with tabs[6]:
    st.subheader("Centro / Orden de Costo")

    centro_col = fin_centro_col or op_centro_col

    if centro_col:
        fuente_centro = (
            financiero_f
            if centro_col in financiero_f.columns
            else operativo_f
        )

        st.plotly_chart(
            pareto(
                fuente_centro,
                centro_col,
                "Pareto Centro / Orden Costo",
            ),
            use_container_width=True,
        )

        top_centros = (
            resumen_categoria(fuente_centro, centro_col)
            .head(5)[centro_col]
            .tolist()
        )

        if centro_col in financiero_f.columns:
            evol = (
                financiero_f[
                    financiero_f[centro_col].isin(top_centros)
                ]
                .groupby(
                    ["AÑO_MES", centro_col],
                    as_index=False,
                )
                .size()
                .rename(columns={"size": "SERVICIOS"})
            )
        else:
            evol = (
                operativo_f[
                    operativo_f[centro_col].isin(top_centros)
                ]
                .groupby(
                    ["AÑO_MES", centro_col],
                    as_index=False,
                )
                .size()
                .rename(columns={"size": "SERVICIOS"})
            )

        fig = px.line(
            evol,
            x="AÑO_MES",
            y="SERVICIOS",
            color=centro_col,
            markers=True,
            text="SERVICIOS",
        )
        fig.update_traces(textposition="top center")
        st.plotly_chart(
            aplicar_estilo(
                fig,
                "Evolución mensual top eventos / centros de costo",
                520,
            ),
            use_container_width=True,
        )


with tabs[7]:
    st.subheader("Tipo de vehículo y modalidad")

    c1, c2 = st.columns(2)
    with c1:
        if fin_vehiculo_col:
            st.plotly_chart(
                dona(
                    financiero_f,
                    fin_vehiculo_col,
                    "Participación por tipo de vehículo",
                ),
                use_container_width=True,
            )
        elif op_vehiculo_col:
            st.plotly_chart(
                dona(
                    operativo_f,
                    op_vehiculo_col,
                    "Participación por tipo de vehículo",
                ),
                use_container_width=True,
            )

    with c2:
        if fin_modalidad_col:
            st.plotly_chart(
                dona(
                    financiero_f,
                    fin_modalidad_col,
                    "Participación por modalidad",
                ),
                use_container_width=True,
            )
        elif op_modalidad_col:
            st.plotly_chart(
                dona(
                    operativo_f,
                    op_modalidad_col,
                    "Participación por modalidad",
                ),
                use_container_width=True,
            )


with tabs[8]:
    st.subheader("Origen y destino")

    origen_col = fin_origen_col or op_origen_col
    destino_col = fin_destino_col or op_destino_col
    fuente_od = (
        financiero_f
        if origen_col in financiero_f.columns
        else operativo_f
    )

    if origen_col and destino_col:
        od = (
            fuente_od.groupby(
                [origen_col, destino_col],
                as_index=False,
            )
            .size()
            .rename(columns={"size": "SERVICIOS"})
        )

        top_o = (
            od.groupby(origen_col)["SERVICIOS"]
            .sum()
            .nlargest(10)
            .index
        )
        top_d = (
            od.groupby(destino_col)["SERVICIOS"]
            .sum()
            .nlargest(10)
            .index
        )

        od = od[
            od[origen_col].isin(top_o)
            & od[destino_col].isin(top_d)
        ]

        pivot = od.pivot_table(
            index=origen_col,
            columns=destino_col,
            values="SERVICIOS",
            fill_value=0,
        )

        fig = px.imshow(
            pivot,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="Blues",
        )
        st.plotly_chart(
            aplicar_estilo(
                fig,
                "Mapa de calor Origen → Destino",
                520,
            ),
            use_container_width=True,
        )


with tabs[9]:
    st.subheader("Calidad y trazabilidad")

    if trazabilidad_col:
        traz_res = resumen_categoria(
            financiero_f,
            trazabilidad_col,
        )

        fig = px.pie(
            traz_res,
            names=trazabilidad_col,
            values="CANTIDAD",
            hole=0.45,
        )
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(
            aplicar_estilo(fig, "Estado de trazabilidad"),
            use_container_width=True,
        )

    columnas_traza = [
        c
        for c in [
            "REMESA",
            "ASTRANS_CARGA_FECHA",
            "PAT_REMESA",
            "PAT_ESTADO",
            "DATA_ESTADO_SERVICIO",
            "ESTADO_TRAZABILIDAD",
            "RESULTADO_SERVICIO",
        ]
        if c in financiero_f.columns
    ]

    if columnas_traza:
        st.dataframe(
            financiero_f[columnas_traza],
            use_container_width=True,
            hide_index=True,
        )


with tabs[10]:
    st.subheader("Exportar informe")

    detalle_export = detalle_res.copy()
    agrupado_export = agrupado_res.copy()

    hojas = {
        "OPERATIVO_FILTRADO": operativo_f,
        "FINANCIERO_FILTRADO": financiero_f,
        "ESTADO_DETALLE": detalle_export,
        "ESTADO_AGRUPADO": agrupado_export,
        "OPERATIVO_PERIODOS": operativo_periodo,
        "FINANCIERO_PERIODOS": fin_periodo,
    }

    excel_bytes = exportar_excel(hojas)

    st.download_button(
        "📥 Descargar informe ejecutivo en Excel",
        data=excel_bytes,
        file_name="RCN_INFORME_EJECUTIVO_V8.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### Resumen listo para la presentación")
    st.write(
        f"El análisis operativo se construyó sobre **CRUCE_DATA_PAT**, con "
        f"**{entero(total_operativo)} solicitudes**, de las cuales "
        f"**{entero(programados)} fueron programadas ({porcentaje(pct_programado)})** y "
        f"**{entero(cancelados)} canceladas ({porcentaje(pct_cancelado)})**. "
        f"El análisis financiero se construyó sobre **{hoja_financiera}**, con "
        f"**{entero(servicios_ejecutados)} remesas únicas ejecutadas**, facturación de "
        f"**{moneda(facturacion)}**, margen de **{moneda(margen)}** y rentabilidad de "
        f"**{porcentaje(rentabilidad)}**."
    )
