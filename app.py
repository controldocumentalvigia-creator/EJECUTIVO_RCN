"""RCN Informe Ejecutivo V11.2. Ejecutar: streamlit run app.py"""
import io, re, unicodedata
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

def norm(x):
    if pd.isna(x): return ''
    return ''.join(c for c in unicodedata.normalize('NFKD', str(x).upper().strip()) if not unicodedata.combining(c))


def col(df, *names):
    lookup = {re.sub('[^A-Z0-9]', '', norm(c)): c for c in df.columns}
    for n in names:
        k = re.sub('[^A-Z0-9]', '', norm(n))
        if k in lookup: return lookup[k]
    return None


def values(df, *names):
    c = col(df, *names)
    return df[c] if c is not None else pd.Series([''] * len(df), index=df.index)


def dates(s): return pd.to_datetime(s, errors='coerce', dayfirst=True)


def money(s):
    if pd.api.types.is_numeric_dtype(s): return pd.to_numeric(s, errors='coerce').fillna(0)
    v = s.fillna('').astype(str).str.replace(r'[^0-9,.-]', '', regex=True)
    comma = v.str.contains(',', regex=False)
    v.loc[comma] = v.loc[comma].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(v, errors='coerce').fillna(0)


def order(s):
    # Mantener sufijo -000: distintas subórdenes NO deben fusionarse.
    return s.map(lambda x: re.sub(r'\.0$', '', re.sub(r'\s+', '', norm(x))) if pd.notna(x) else '')


def remesas(x):
    # Acepta SEV006... y múltiples remesas en una misma celda.
    return list(dict.fromkeys(re.findall(r'SEV\s*[-_]?\s*\d+', norm(x).replace(' ', ''))))


def key(fecha, orden):
    return fecha.dt.strftime('%Y-%m-%d').fillna('') + '|' + order(orden)


def estado_data(x):
    t = norm(x)
    if 'CANCEL' in t: return 'CANCELADO_INICIAL'
    if 'RE' in t and 'PROGRAM' in t: return 'REPROGRAMADO_INICIAL'
    if 'PROGRAM' in t or t in ('LIQUIDADO', 'PRELIQUIDADO', 'CONCILIADO'): return 'GESTIONADO_INICIAL'
    return 'OTRO_ESTADO_DATA'


def leer_excel(archivo, preferred, must):
    book = pd.ExcelFile(io.BytesIO(archivo))
    best = None
    for sh in preferred:
        if sh not in book.sheet_names: continue
        d = pd.read_excel(book, sheet_name=sh)
        if all(col(d, *variants) is not None for variants in must): return sh, d
    for sh in book.sheet_names:
        d = pd.read_excel(book, sheet_name=sh)
        if all(col(d, *variants) is not None for variants in must): return sh, d
    raise ValueError('No se encontró hoja con las columnas requeridas: ' + str(must))


def preparar_data(raw):
    d = pd.DataFrame(index=raw.index)
    d['DATA_FECHA_SERVICIO'] = dates(values(raw, 'Fecha Servicio'))
    d['DATA_ORDEN_SERVICIO'] = values(raw, 'No.OrdenServicio', 'No. Orden Servicio').astype(str).str.strip()
    d['DATA_ESTADO_SERVICIO'] = values(raw, 'Estado Servicio').astype(str).str.strip()
    for new, names in {'CENTRO_ORDEN_COSTO':['Centro / Orden Costo'], 'MODALIDAD':['Modalidad'], 'TIPO_VEHICULO':['Tipo de vehículo'], 'ORIGEN':['Origen'], 'DESTINO':['Destino'], 'SOLICITANTE':['Usuario Solicitante'], 'PROVEEDOR':['Proveedor']}.items():
        d['DATA_'+new] = values(raw, *names).fillna('').astype(str).str.strip()
    d = d[d.DATA_FECHA_SERVICIO.notna()].copy()
    d['DATA_ID'] = np.arange(1, len(d)+1)
    d['LLAVE_DATA_PAT'] = key(d.DATA_FECHA_SERVICIO, d.DATA_ORDEN_SERVICIO)
    d['CLASE_INICIAL'] = d.DATA_ESTADO_SERVICIO.map(estado_data)
    d['DATA_CANCELADO'] = d.CLASE_INICIAL.eq('CANCELADO_INICIAL')
    d['ANO_MES'] = d.DATA_FECHA_SERVICIO.dt.strftime('%Y-%m')
    return d


def preparar_pat(raw, hoja):
    p = pd.DataFrame(index=raw.index)
    p['PAT_FECHA_SERVICIO'] = dates(values(raw, 'Fecha Servicio'))
    p['PAT_ORDEN_SERVICIO'] = values(raw, 'No. Orden Servicio', 'SERVICIO', 'No.OrdenServicio').astype(str).str.strip()
    p['PAT_REMESAS_ORIGINAL'] = values(raw, 'REMESAS', 'REMESA').fillna('').astype(str).str.strip()
    p['PAT_ESTADO'] = values(raw, 'Estado').fillna('').astype(str).str.strip()
    p['PAT_CENTRO_ORDEN_COSTO'] = values(raw, 'Centro / Orden Costo').fillna('').astype(str).str.strip()
    p['PAT_ORIGEN'] = values(raw, 'ORIGEN').fillna('').astype(str).str.strip()
    p['PAT_DESTINO'] = values(raw, 'DESTINO').fillna('').astype(str).str.strip()
    p['PAT_HOJA_ORIGEN'] = hoja
    p = p[p.PAT_FECHA_SERVICIO.notna()].copy()
    p['PAT_ID'] = np.arange(1, len(p)+1)
    p['LLAVE_DATA_PAT'] = key(p.PAT_FECHA_SERVICIO, p.PAT_ORDEN_SERVICIO)
    p['LISTA_SEV'] = p.PAT_REMESAS_ORIGINAL.map(remesas)
    p['PAT_TIENE_SEV'] = p.LISTA_SEV.map(bool)
    p['PAT_CANCELADO'] = p.PAT_ESTADO.map(lambda x:'CANCEL' in norm(x)) | p.PAT_REMESAS_ORIGINAL.map(lambda x:'CANCEL' in norm(x))
    p['ALERTA_PAT'] = np.where(p.PAT_TIENE_SEV & p.PAT_CANCELADO, 'SEV CON ESTADO CANCELADO - REVISAR COORDINADOR', '')
    p['RESULTADO_PAT'] = np.select([p.PAT_TIENE_SEV, p.PAT_CANCELADO], ['PRESTADO_CON_REMESA', 'CANCELADO_PAT'], default='PENDIENTE_VALIDACION')
    return p


def preparar_tray(raw):
    t = raw.copy()
    t['ASTRANS_TRAYECTO'] = values(t, 'TRAYECTO', 'REMESA').fillna('').astype(str).str.strip()
    t['ASTRANS_REMESA_NORM'] = t.ASTRANS_TRAYECTO.map(lambda x: remesas(x)[0] if remesas(x) else '')
    t['ASTRANS_FECHA_SERVICIO'] = dates(values(t, 'FECHA R', 'FECHA SERVICIO'))
    t['ASTRANS_FECHA_CARGA'] = dates(values(t, 'CARGA'))
    t['ASTRANS_ESTADO_OPER'] = values(t, 'ESTADO OPER', 'ESTADO OP').fillna('').astype(str).str.strip()
    t['V_CLIENTE_NUM'] = money(values(t, 'V.CLIENTE', 'V CLIENTE'))
    t['V_CONDUCT_NUM'] = money(values(t, 'V.CONDUCTOR', 'V.CONDUCT', 'V CONDUCTOR'))
    t['MARGEN_CALCULADO'] = t.V_CLIENTE_NUM - t.V_CONDUCT_NUM
    t['ASTRANS_ID'] = np.arange(1, len(t)+1)
    t['ANO_MES_SERVICIO'] = t.ASTRANS_FECHA_SERVICIO.dt.strftime('%Y-%m')
    t['ANO_MES_CARGA'] = t.ASTRANS_FECHA_CARGA.dt.strftime('%Y-%m')
    estado = t.ASTRANS_ESTADO_OPER.map(norm)
    t['ES_EJECUCION_VALIDA'] = estado.isin(['CUMPLIDO', 'CUMPLIDO OPERATIVO'])
    t['ES_ANULADO'] = estado.eq('ANULADO')
    t['ES_CIERRE_PENDIENTE'] = estado.isin(['EN PROGRAMACION','EN TRANSITO','CUMPLIDO OPERATIVO'])
    return t


def conciliar(data, pat, tray):
    # Resumen PAT por solicitud, preservando detalle en otra hoja.
    p = pat.groupby('LLAVE_DATA_PAT', as_index=False).agg(
        PAT_REGISTROS=('PAT_ID','size'), PAT_ESTADOS=('PAT_ESTADO',lambda x:' | '.join(dict.fromkeys(map(str,x)))),
        PAT_REMESAS=('PAT_REMESAS_ORIGINAL',lambda x:' | '.join(dict.fromkeys(map(str,x)))),
        PAT_TIENE_SEV=('PAT_TIENE_SEV','max'), PAT_CANCELADO=('PAT_CANCELADO','max'),
        PAT_ALERTA=('ALERTA_PAT',lambda x:' | '.join(v for v in x if v)),
        PAT_CENTRO_ORDEN_COSTO=('PAT_CENTRO_ORDEN_COSTO','first'))
    # La remesa prevalece si un mismo servicio tiene simultáneamente estados contradictorios.
    p['RESULTADO_PAT'] = np.select([p.PAT_TIENE_SEV,p.PAT_CANCELADO],['PRESTADO_CON_REMESA','CANCELADO_PAT'],default='PENDIENTE_VALIDACION')
    solicitudes = data.merge(p,on='LLAVE_DATA_PAT',how='left',validate='many_to_one')
    solicitudes['COINCIDE_PAT'] = solicitudes.PAT_REGISTROS.notna()
    solicitudes['RESULTADO_PAT'] = solicitudes.RESULTADO_PAT.fillna('SIN_REGISTRO_PAT')
    solicitudes['ESTADO_FINAL_SOLICITUD'] = np.select([
        solicitudes.RESULTADO_PAT.eq('PRESTADO_CON_REMESA'),
        solicitudes.RESULTADO_PAT.eq('CANCELADO_PAT'),
        solicitudes.RESULTADO_PAT.eq('SIN_REGISTRO_PAT') & solicitudes.DATA_CANCELADO,
    ], ['PRESTADO_CON_REMESA','CANCELADO_CONFIRMADO_PAT','CANCELADO_DATA_SIN_PAT'], default='PENDIENTE_CONCILIACION')
    # Tabla puente por remesa individual; no sumar importes a partir de esta tabla.
    puente = pat.explode('LISTA_SEV').rename(columns={'LISTA_SEV':'REMESA_NORM'})
    puente = puente[puente.REMESA_NORM.notna() & puente.REMESA_NORM.ne('')].copy()
    puente['COINCIDE_DATA'] = puente.LLAVE_DATA_PAT.isin(set(data.LLAVE_DATA_PAT))
    puente['ALERTA_MULTIPLE_PAT'] = puente.duplicated('REMESA_NORM',keep=False)
    # Cada remesa puede tener más de una fila PAT; no duplicar TRAYECTOS.
    bridge = puente.groupby('REMESA_NORM',as_index=False).agg(
        PAT_FILAS_REMESA=('PAT_ID','size'), PAT_ORDEN_SERVICIO=('PAT_ORDEN_SERVICIO',lambda x:' | '.join(dict.fromkeys(map(str,x)))),
        PAT_ESTADO=('PAT_ESTADO',lambda x:' | '.join(dict.fromkeys(map(str,x)))),
        PAT_CENTRO_ORDEN_COSTO=('PAT_CENTRO_ORDEN_COSTO',lambda x:next((v for v in x if v),'')),
        DATA_COINCIDE=('COINCIDE_DATA','max'),
        PAT_ALERTA=('ALERTA_PAT',lambda x:' | '.join(v for v in x if v)),
        LLAVE_DATA_PAT=('LLAVE_DATA_PAT',lambda x:' | '.join(dict.fromkeys(map(str,x)))))
    # Enriquecer remesa con DATA solo cuando existe una única llave DATA por remesa.
    data_c = data.groupby('LLAVE_DATA_PAT',as_index=False).agg(
        DATA_CENTRO_ORDEN_COSTO=('DATA_CENTRO_ORDEN_COSTO',lambda x:next((v for v in x if v),'')),
        DATA_ESTADO_SERVICIO=('DATA_ESTADO_SERVICIO',lambda x:' | '.join(dict.fromkeys(map(str,x)))),
        DATA_ORDEN_SERVICIO=('DATA_ORDEN_SERVICIO','first'),
        DATA_FECHA_SERVICIO=('DATA_FECHA_SERVICIO','min'),
        DATA_CANCELADO=('DATA_CANCELADO','max'))
    bridge['LLAVE_UNICA'] = bridge.LLAVE_DATA_PAT.map(lambda x: x if ' | ' not in x else '')
    bridge = bridge.merge(data_c,left_on='LLAVE_UNICA',right_on='LLAVE_DATA_PAT',how='left',suffixes=('','_DATA'))
    base = tray.merge(bridge,left_on='ASTRANS_REMESA_NORM',right_on='REMESA_NORM',how='left',validate='many_to_one')
    base['COINCIDE_PAT'] = base.REMESA_NORM.notna()
    base['COINCIDE_DATA'] = base.DATA_ORDEN_SERVICIO.notna()
    base['ESTADO_TRAZABILIDAD'] = np.select([
        base.COINCIDE_DATA,base.COINCIDE_PAT],
        ['CONCILIADO DATA + PAT + ASTRANS','CONCILIADO PAT + ASTRANS / SIN DATA'],
        default='ASTRANS SIN PAT')
    base['ALERTA_CONCILIACION'] = base.PAT_ALERTA.fillna('')
    base.loc[base.ASTRANS_REMESA_NORM.eq(''),'ALERTA_CONCILIACION'] = 'TRAYECTO SIN REMESA SEV'
    base.loc[base.ASTRANS_REMESA_NORM.duplicated(keep=False) & base.ASTRANS_REMESA_NORM.ne(''),'ALERTA_CONCILIACION'] += ' | REMESA DUPLICADA ASTRANS'
    base['RESULTADO_SERVICIO'] = np.select([
        base.ES_ANULADO, base.ES_EJECUCION_VALIDA,
        base.ES_CIERRE_PENDIENTE],['ANULADO','EJECUTADO_REGISTRADO','PENDIENTE_CIERRE'],default='REVISAR_ESTADO_ASTRANS')
    base['CENTRO_COSTO_CONCILIADO'] = base.DATA_CENTRO_ORDEN_COSTO.fillna('')
    mask = base.CENTRO_COSTO_CONCILIADO.eq('')
    base.loc[mask,'CENTRO_COSTO_CONCILIADO'] = base.loc[mask,'PAT_CENTRO_ORDEN_COSTO'].fillna('')
    base['FUENTE_CENTRO_COSTO'] = np.select([base.DATA_CENTRO_ORDEN_COSTO.fillna('').ne(''),base.PAT_CENTRO_ORDEN_COSTO.fillna('').ne('')],['DATA','PAT'],default='SIN_CONCILIAR')
    # Actualizar solicitudes con existencia en ASTRANS, incluso cuando DATA inicial fue cancelada.
    remesas_validas = set(base.loc[base.ES_EJECUCION_VALIDA,'ASTRANS_REMESA_NORM']) - {''}
    puente['EXISTE_ASTRANS_EJECUTADO'] = puente.REMESA_NORM.isin(remesas_validas)
    comprobadas = puente.groupby('LLAVE_DATA_PAT')['EXISTE_ASTRANS_EJECUTADO'].max()
    solicitudes['EJECUCION_CONFIRMADA_ASTRANS'] = solicitudes.LLAVE_DATA_PAT.map(comprobadas).fillna(False).astype(bool)
    solicitudes.loc[solicitudes.EJECUCION_CONFIRMADA_ASTRANS,'ESTADO_FINAL_SOLICITUD'] = 'EJECUTADO_CONCILIADO'
    solicitudes['ALERTA_CONCILIACION'] = solicitudes.PAT_ALERTA.fillna('')
    solicitudes.loc[solicitudes.DATA_CANCELADO & solicitudes.EJECUCION_CONFIRMADA_ASTRANS,'ALERTA_CONCILIACION'] += ' | CANCELADO EN DATA PERO EJECUTADO'
    solicitudes.loc[solicitudes.RESULTADO_PAT.eq('PRESTADO_CON_REMESA') & ~solicitudes.EJECUCION_CONFIRMADA_ASTRANS,'ALERTA_CONCILIACION'] += ' | SEV SIN EJECUCION CONFIRMADA EN ASTRANS'
    revision = pd.concat([
        solicitudes.loc[solicitudes.ALERTA_CONCILIACION.str.strip(' |').ne(''),['DATA_FECHA_SERVICIO','DATA_ORDEN_SERVICIO','DATA_CENTRO_ORDEN_COSTO','DATA_ESTADO_SERVICIO','PAT_REMESAS','PAT_ESTADOS','ESTADO_FINAL_SOLICITUD','ALERTA_CONCILIACION']].rename(columns={'DATA_FECHA_SERVICIO':'FECHA','DATA_ORDEN_SERVICIO':'ORDEN','DATA_CENTRO_ORDEN_COSTO':'CENTRO','DATA_ESTADO_SERVICIO':'ESTADO_DATA','PAT_REMESAS':'REMESAS','PAT_ESTADOS':'ESTADO_PAT','ESTADO_FINAL_SOLICITUD':'RESULTADO'}),
    ],ignore_index=True)
    revision['ESTADO_GESTION'] = 'PENDIENTE COORDINADOR'
    revision['OBSERVACIONES_COORDINADOR'] = ''
    sin_pat = solicitudes[~solicitudes.COINCIDE_PAT].copy()
    pat_sin_data = pat[~pat.LLAVE_DATA_PAT.isin(set(data.LLAVE_DATA_PAT))].copy()
    pat_sin_astrans = puente[~puente.REMESA_NORM.isin(set(tray.ASTRANS_REMESA_NORM))].copy()
    dup_data = data[data.duplicated('LLAVE_DATA_PAT',keep=False)].copy()
    dup_pat = pat[pat.duplicated('LLAVE_DATA_PAT',keep=False)].copy()
    dup_tray = tray[tray.ASTRANS_REMESA_NORM.ne('') & tray.duplicated('ASTRANS_REMESA_NORM',keep=False)].copy()
    return {'BASE_SOLICITUDES':solicitudes,'CRUCE_DATA_PAT':solicitudes,'BASE_MAESTRA_RCN':base,
        'DETALLE_PAT':pat.drop(columns=['LISTA_SEV']), 'PUENTE_REMESAS':puente.drop(columns=['LISTA_SEV'],errors='ignore'),
        'REVISION_COORDINADOR':revision,'DATA_SIN_PAT':sin_pat,'PAT_SIN_DATA':pat_sin_data.drop(columns=['LISTA_SEV']),
        'PAT_SIN_ASTRANS':pat_sin_astrans.drop(columns=['LISTA_SEV'],errors='ignore'),
        'DUPLICADOS_DATA':dup_data,'DUPLICADOS_PAT':dup_pat.drop(columns=['LISTA_SEV']),
        'DUPLICADOS_ASTRANS':dup_tray}


def exportar(hojas):
    bio=io.BytesIO()
    with pd.ExcelWriter(bio,engine='xlsxwriter',datetime_format='dd/mm/yyyy') as writer:
        for name,df in hojas.items():
            d=df.copy()
            for c in d.columns:
                if d[c].map(lambda x:isinstance(x,list)).any(): d[c]=d[c].map(str)
            d.to_excel(writer,sheet_name=name[:31],index=False)
            ws=writer.sheets[name[:31]]
            ws.freeze_panes(1,0)
            if len(d.columns):
                ws.autofilter(0,0,len(d),len(d.columns)-1)
                fmt=writer.book.add_format({'bold':True,'font_color':'white','bg_color':'#003B75','align':'center'})
                for j,c in enumerate(d.columns):
                    ws.write(0,j,c,fmt);ws.set_column(j,j,min(38,max(15,len(c)+2)))
    return bio.getvalue()

# ================================================================
# INFORME EJECUTIVO V10: lectura flexible, sin bloqueo por versión.
# ================================================================
from datetime import datetime
st.set_page_config(page_title='RCN Informe Ejecutivo V11.2',page_icon='📊',layout='wide')
st.markdown('''<style>.block-container{padding-top:1rem}h1,h2,h3{color:#003B75!important}div[data-testid="stMetric"]{border:1px solid #dce3ef;border-radius:10px;padding:9px}div[data-testid="stDataFrame"]{font-size:12px}</style>''',unsafe_allow_html=True)
st.title('📊 RCN | Informe Ejecutivo Operativo y Financiero V11.2')
st.caption('Demanda DATA · Resultado PAT · Ejecución TRAYECTOS · Variaciones · Rentabilidad · Calidad de datos')

def fmt(x):
    try:return f'{float(x):,.0f}'.replace(',','.')
    except:return '0'
def cop(x):return '$ '+fmt(x)+' COP'
def pct(x):
    if pd.isna(x):return '—'
    return f'{float(x):+.2f}%'.replace('.',',')

def pct_plain(x):
    if pd.isna(x):return '—'
    return f'{float(x):.2f}%'.replace('.',',')
def periodo(d,fecha):
    d=d.copy();dt=pd.to_datetime(d[fecha],errors='coerce',dayfirst=True)
    d['MES']=dt.dt.strftime('%Y-%m');d['AÑO']=dt.dt.year
    d['BIMESTRE']=dt.dt.year.astype('Int64').astype(str)+'-B'+(((dt.dt.month-1)//2)+1).astype('Int64').astype(str)
    d['TRIMESTRE']=dt.dt.year.astype('Int64').astype(str)+'-T'+(((dt.dt.month-1)//3)+1).astype('Int64').astype(str)
    d['SEMESTRE']=dt.dt.year.astype('Int64').astype(str)+'-S'+(((dt.dt.month-1)//6)+1).astype('Int64').astype(str)
    return d

def variacion(d,col):
    d=d.sort_values('PERIODO').copy()
    d['VAR_'+col+'_%']=d[col].pct_change(fill_method=None)*100
    return d

MESES_ES={1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'}

def etiqueta_periodo(x):
    x=str(x)
    if re.fullmatch(r'\d{4}-\d{2}',x):
        return MESES_ES.get(int(x[-2:]),x)+' '+x[:4]
    return x

def estilo(fig, titulo=None, alto=480, porcentaje_eje=False):
    if titulo:fig.update_layout(title=dict(text=titulo,font=dict(size=19,color='#003B75')))
    fig.update_layout(height=alto,template='plotly_white',paper_bgcolor='#FFFFFF',plot_bgcolor='#FFFFFF',
        font=dict(family='Arial, sans-serif',color='#172B4D',size=13),
        margin=dict(l=55,r=35,t=78,b=90),
        legend=dict(font=dict(size=12,color='#172B4D'),bgcolor='rgba(255,255,255,.9)'),
        xaxis=dict(tickfont=dict(size=13,color='#172B4D'),title_font=dict(color='#172B4D'),
                   showline=True,linecolor='#9BA9BB',type='category'),
        yaxis=dict(tickfont=dict(size=12,color='#172B4D'),title_font=dict(color='#172B4D'),gridcolor='#E7EDF4'))
    if porcentaje_eje:fig.update_yaxes(ticksuffix=' %',tickformat='.1f')
    return fig

def ejes_meses(fig, d, x):
    if x in d and not d.empty:
        vals=sorted(d[x].dropna().astype(str).unique())
        fig.update_xaxes(tickmode='array',tickvals=vals,ticktext=[etiqueta_periodo(v) for v in vals],tickangle=0)
    return fig

def barras(d,x,y,titulo,moneda=False,color='#003B75'):
    d=d.sort_values(x).copy()
    if d.empty:return estilo(go.Figure(),titulo)
    v=d[y].pct_change(fill_method=None)*100
    d['_TEXTO']=[(cop(a) if moneda else fmt(a))+'<br>'+('Base' if pd.isna(b) else ('▲ ' if b>0 else '▼ ' if b<0 else '▬ ')+pct_plain(abs(b))) for a,b in zip(d[y],v)]
    fig=px.bar(d,x=x,y=y,text='_TEXTO',title=titulo)
    fig.update_traces(marker_color=color,textposition='outside',textfont=dict(size=11,color='#172B4D'),cliponaxis=False)
    estilo(fig,titulo,510);ejes_meses(fig,d,x)
    fig.update_yaxes(rangemode='tozero')
    return fig

def linea(d,x,cols,titulo,porcentaje=False):
    d=d.sort_values(x).copy()
    if d.empty:return estilo(go.Figure(),titulo)
    fig=px.line(d,x=x,y=cols,markers=True,title=titulo)
    for trace in fig.data:
        trace.update(line=dict(width=3),marker=dict(size=8))
        if porcentaje:
            trace.update(mode='lines+markers+text',text=[pct_plain(z) if pd.notna(z) else '' for z in trace.y],textposition='top center',textfont=dict(size=11,color='#172B4D'))
    estilo(fig,titulo,480,porcentaje);ejes_meses(fig,d,x)
    return fig

def donut(d,col,titulo,top=12):
    t=d.groupby(col,dropna=False).size().nlargest(top).reset_index(name='CANTIDAD')
    fig=px.pie(t,names=col,values='CANTIDAD',hole=.45,title=titulo)
    fig.update_traces(textinfo='percent+label')
    return estilo(fig,titulo,470)

def pareto(d,col,titulo,top=20):
    t=d.groupby(col,dropna=False).size().nlargest(top).reset_index(name='CANTIDAD')
    if t.empty:return estilo(go.Figure(),titulo)
    t['ACUM_%']=t.CANTIDAD.cumsum()/t.CANTIDAD.sum()*100
    fig=go.Figure()
    fig.add_bar(x=t[col],y=t.CANTIDAD,text=t.CANTIDAD,textposition='outside',name='Cantidad',marker_color='#003B75')
    fig.add_scatter(x=t[col],y=t['ACUM_%'],yaxis='y2',mode='lines+markers',name='% acumulado',line=dict(color='#F58220',width=3),text=[pct_plain(x) for x in t['ACUM_%']])
    estilo(fig,titulo,530)
    fig.update_layout(yaxis2=dict(overlaying='y',side='right',range=[0,110],title='% acumulado',ticksuffix=' %',tickfont=dict(color='#172B4D')))
    fig.update_xaxes(tickangle=-30)
    return fig

def normalizar_lugar(x):
    z=norm(x)
    z=re.sub(r'\s+',' ',z).strip(' -.,')
    return z if z else 'SIN DATO'

def mapa_calor(d,origen,destino,titulo):
    if not origen or not destino or d.empty:return None
    sub=d[[origen,destino]].copy()
    sub['ORIGEN_N']=sub[origen].map(normalizar_lugar)
    sub['DESTINO_N']=sub[destino].map(normalizar_lugar)
    sub=sub[(sub.ORIGEN_N!='SIN DATO')&(sub.DESTINO_N!='SIN DATO')]
    if sub.empty:return None
    top_o=sub.ORIGEN_N.value_counts().head(12).index
    top_d=sub.DESTINO_N.value_counts().head(12).index
    sub=sub[sub.ORIGEN_N.isin(top_o)&sub.DESTINO_N.isin(top_d)]
    pivot=pd.crosstab(sub.ORIGEN_N,sub.DESTINO_N)
    if pivot.empty:return None
    # Escala logarítmica para que una ruta muy frecuente no oculte el resto.
    import plotly.graph_objects as go
    z=np.log1p(pivot.to_numpy(dtype=float))
    etiquetas=pivot.to_numpy(dtype=int)
    fig=go.Figure(go.Heatmap(x=pivot.columns.tolist(),y=pivot.index.tolist(),z=z,
        text=etiquetas,texttemplate='%{text}',textfont=dict(size=11),
        colorscale='YlOrRd',colorbar=dict(title='Intensidad<br>log(1+n)',tickfont=dict(color='#172B4D')),
        customdata=etiquetas,hovertemplate='Origen: %{y}<br>Destino: %{x}<br>Servicios: %{customdata:,.0f}<extra></extra>',
        xgap=2,ygap=2))
    estilo(fig,titulo,630)
    fig.update_xaxes(tickangle=-35)
    fig.update_yaxes(autorange='reversed')
    return fig

def comparativo_barras(d,series,titulo):
    if d.empty:return estilo(go.Figure(),titulo)
    fig=go.Figure()
    colores=['#003B75','#D43D3D','#008A3D','#F58220']
    for i,(columna,nombre) in enumerate(series):
        if columna in d:
            fig.add_bar(x=d.PERIODO,y=d[columna],name=nombre,marker_color=colores[i%len(colores)],text=d[columna],textposition='outside',cliponaxis=False)
    fig.update_layout(barmode='group')
    estilo(fig,titulo,520);ejes_meses(fig,d,'PERIODO')
    return fig

def barras_comparativas_con_variacion(d, series, titulo):
    """Barras DATA/PAT y variación mensual calculada dentro de cada serie."""
    if d.empty:return estilo(go.Figure(),titulo)
    colores=['#003B75','#D43D3D','#008A3D','#F58220']
    fig=go.Figure()
    for i,(campo,nombre) in enumerate(series):
        if campo not in d:continue
        vals=pd.to_numeric(d[campo],errors='coerce')
        var=vals.pct_change(fill_method=None)*100
        texto=[];custom=[]
        for n,v in zip(vals,var):
            if pd.isna(n):texto.append('');custom.append('Sin dato PAT');continue
            cambio='Base' if pd.isna(v) else ('▲ ' if v>0 else '▼ ' if v<0 else '▬ ')+pct_plain(abs(v))
            texto.append(f'{fmt(n)}<br>{cambio}')
            custom.append(cambio)
        fig.add_bar(x=d.PERIODO,y=vals,name=nombre,marker_color=colores[i%len(colores)],
                    text=texto,textposition='outside',textfont=dict(size=10,color='#172B4D'),
                    customdata=custom,hovertemplate='%{x}<br>%{fullData.name}: %{y:,.0f}<br>Variación: %{customdata}<extra></extra>',cliponaxis=False)
    fig.update_layout(barmode='group',uniformtext_minsize=9,uniformtext_mode='hide')
    estilo(fig,titulo,565);ejes_meses(fig,d,'PERIODO')
    fig.update_yaxes(rangemode='tozero')
    return fig


def tabla_mensual_completa(d,indice,grupo,valor,meses,top=12):
    """Malla explícita: cero significa que hay cobertura y no hubo registros."""
    t=d.groupby([indice,grupo],dropna=False).size().reset_index(name=valor)
    principales=d[grupo].value_counts().head(top).index.tolist()
    tabla=t[t[grupo].isin(principales)].pivot(index=grupo,columns=indice,values=valor)
    tabla=tabla.reindex(index=principales,columns=meses).fillna(0).astype(int)
    tabla['TOTAL']=tabla.sum(axis=1)
    return tabla.reset_index()


def ranking_vehiculos(d,campo,titulo):
    if d.empty:return estilo(go.Figure(),titulo),pd.DataFrame()
    t=d.copy();t['_TIPO']=t[campo].fillna('SIN DATO').astype(str).str.strip().str.upper()
    t['_TIPO']=t['_TIPO'].replace({'':'SIN DATO','NAN':'SIN DATO'})
    res=t.groupby('_TIPO').size().reset_index(name='SERVICIOS').sort_values('SERVICIOS',ascending=False)
    res['PARTICIPACION_%']=res.SERVICIOS/res.SERVICIOS.sum()*100
    graf=res.head(12).sort_values('SERVICIOS')
    fig=go.Figure(go.Bar(x=graf.SERVICIOS,y=graf._TIPO,orientation='h',marker_color='#003B75',
        text=[f'{fmt(n)}  |  {pct_plain(p)}' for n,p in zip(graf.SERVICIOS,graf['PARTICIPACION_%'])],
        textposition='outside',cliponaxis=False,
        hovertemplate='%{y}: %{x:,.0f} servicios<extra></extra>'))
    estilo(fig,titulo,max(410,75+len(graf)*42))
    fig.update_layout(margin=dict(l=185,r=150,t=80,b=55),showlegend=False)
    fig.update_xaxes(title='Servicios',rangemode='tozero')
    fig.update_yaxes(title='',tickfont=dict(size=12,color='#172B4D'))
    return fig,res


def tabla_rutas_iniciales_vs_reales(op,fin):
    """Comparación descriptiva por par origen/destino, sin afirmar conciliación uno a uno."""
    inicial=op.copy();ejec=fin.copy()
    oi=first(inicial,['DATA_ORIGEN']);di=first(inicial,['DATA_DESTINO'])
    oe=first(ejec,['ORIGEN','ASTRANS_ORIGEN']);de=first(ejec,['DESTINO','ASTRANS_DESTINO'])
    if not all([oi,di,oe,de]):return pd.DataFrame()
    for d,o,decol in [(inicial,oi,di),(ejec,oe,de)]:
        d['_RUTA']=d[o].map(normalizar_lugar)+' → '+d[decol].map(normalizar_lugar)
    a=inicial.groupby('_RUTA').size().rename('SOLICITADOS_DATA')
    b=ejec.groupby('_RUTA').size().rename('EJECUTADOS_ASTRANS')
    res=pd.concat([a,b],axis=1).fillna(0).astype(int).reset_index().rename(columns={'_RUTA':'RUTA'})
    res['DIFERENCIA']=res.EJECUTADOS_ASTRANS-res.SOLICITADOS_DATA
    return res.sort_values(['SOLICITADOS_DATA','EJECUTADOS_ASTRANS'],ascending=False)

def first(d,names):
    for name in names:
        if name in d.columns:return name
    return None

def boolean(s):
    if pd.api.types.is_bool_dtype(s):return s.fillna(False)
    return s.fillna('').astype(str).str.upper().isin(['TRUE','VERDADERO','1','SI'])

st.info('Compatible con Base Maestra V9/V10. Si cargas una base antigua, puedes reconstruirla aquí mismo desde las tres fuentes originales; no se bloqueará la aplicación.')
f=st.file_uploader('Cargar BASE_MAESTRA_RCN_ACTUALIZADA.xlsx o BASE_MAESTRA_RCN.xlsx',type='xlsx',key='maestra')
with st.expander('🔧 Reconstruir la Base Maestra directamente con DATA + PAT + TRAYECTOS (sin usar Data Factory)',expanded=False):
    c1,c2,c3=st.columns(3)
    with c1: fd=st.file_uploader('DATA RCN original',type='xlsx',key='origen_data')
    with c2: fp=st.file_uploader('SERVICIO PAT original',type='xlsx',key='origen_pat')
    with c3: ft=st.file_uploader('TRAYECTOS TODOS original',type='xlsx',key='origen_tray')
    st.caption('Si cargas los tres originales, se recalculan las 12 hojas y prevalece esta conciliación sobre cualquier Base Maestra antigua.')

if not f and not all([fd,fp,ft]):
    st.info('Carga una Base Maestra o los tres archivos originales para comenzar.')
    st.stop()
try:
    if all([fd,fp,ft]):
        _,rd=leer_excel(fd.getvalue(),['Sheet1'],[('Fecha Servicio',),('Estado Servicio',),('No.OrdenServicio','No. Orden Servicio')])
        _,rp=leer_excel(fp.getvalue(),['ACTUALIZADO','BASE'],[('Fecha Servicio',),('REMESAS',),('Estado',),('No. Orden Servicio','SERVICIO')])
        _,rt=leer_excel(ft.getvalue(),['ORDPLA_L01 (75)','Sheet1'],[('TRAYECTO','REMESA'),('ESTADO OPER','ESTADO OP'),('V.CLIENTE',)])
        hojas=conciliar(preparar_data(rd),preparar_pat(rp,'ACTUALIZADO'),preparar_tray(rt))
        op=hojas['BASE_SOLICITUDES'].copy();fin=hojas['BASE_MAESTRA_RCN'].copy();rev=hojas['REVISION_COORDINADOR'].copy();pat_detalle=hojas['DETALLE_PAT'].copy()
        st.success('Se reconstruyó la Base Maestra directamente desde las tres fuentes.')
        st.download_button('📥 Descargar Base Maestra reconstruida',exportar(hojas),file_name='BASE_MAESTRA_RCN_ACTUALIZADA.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        legacy=False
    else:
        raw=f.getvalue();book=pd.ExcelFile(io.BytesIO(raw));legacy='BASE_SOLICITUDES' not in book.sheet_names
        if not legacy:
            op=pd.read_excel(io.BytesIO(raw),sheet_name='BASE_SOLICITUDES')
            fin=pd.read_excel(io.BytesIO(raw),sheet_name='BASE_MAESTRA_RCN')
            rev=pd.read_excel(io.BytesIO(raw),sheet_name='REVISION_COORDINADOR') if 'REVISION_COORDINADOR' in book.sheet_names else pd.DataFrame();pat_detalle=pd.read_excel(io.BytesIO(raw),sheet_name='DETALLE_PAT') if 'DETALLE_PAT' in book.sheet_names else pd.DataFrame()
        else:
            if not {'CRUCE_DATA_PAT','BASE_MAESTRA_RCN'}.issubset(book.sheet_names):
                st.error('El libro no contiene CRUCE_DATA_PAT y BASE_MAESTRA_RCN. Carga los tres originales para reconstruirlo.')
                st.stop()
            op=pd.read_excel(io.BytesIO(raw),sheet_name='CRUCE_DATA_PAT')
            fin=pd.read_excel(io.BytesIO(raw),sheet_name='BASE_MAESTRA_RCN')
            rev=pd.DataFrame()
            st.warning('MODO HISTÓRICO: se muestran las gráficas disponibles, pero el archivo antiguo NO permite validar resultados finales PAT ni conflictos SEV. Para cifras finales carga los tres originales en el recuadro de reconstrucción.')
except Exception as exc:
    st.error('Error al leer o conciliar los archivos.');st.exception(exc);st.stop()

# Normalizar estructuras antiguas sin atribuir estados finales no verificables.
if legacy:
    if 'DATA_FECHA_SERVICIO' not in op.columns:st.error('No se encontró DATA_FECHA_SERVICIO.');st.stop()
    op['DATA_CANCELADO']=op['DATA_ESTADO_SERVICIO'].fillna('').astype(str).str.upper().str.contains('CANCEL',na=False)
    op['CLASE_INICIAL']=np.where(op.DATA_CANCELADO,'CANCELADO_INICIAL','GESTIONADO_INICIAL')
    op['ESTADO_FINAL_SOLICITUD']='NO_CONCILIADO_HISTORICO'
    op['EJECUCION_CONFIRMADA_ASTRANS']=False
    op['PAT_TIENE_SEV']=False
    op['ALERTA_CONCILIACION']=''
    fin['ASTRANS_FECHA_SERVICIO']=pd.to_datetime(fin[first(fin,['ASTRANS_CARGA_FECHA','CARGA'])],errors='coerce',dayfirst=True)
    fin['ASTRANS_FECHA_CARGA']=fin.ASTRANS_FECHA_SERVICIO
    fin['V_CLIENTE_NUM']=pd.to_numeric(fin[first(fin,['V_CLIENTE_NUM','V.CLIENTE'])],errors='coerce').fillna(0)
    fin['V_CONDUCT_NUM']=pd.to_numeric(fin[first(fin,['V_CONDUCT_NUM','V.CONDUCT'])],errors='coerce').fillna(0)
    fin['MARGEN_CALCULADO']=fin.V_CLIENTE_NUM-fin.V_CONDUCT_NUM
    fin['ASTRANS_REMESA_NORM']=fin[first(fin,['ASTRANS_REMESA_NORM','REMESA'])].fillna('').astype(str) if first(fin,['ASTRANS_REMESA_NORM','REMESA']) else ''
    fin['ES_ANULADO']=fin[first(fin,['ASTRANS_ESTADO_OP_NORM','ESTADO OP'])].fillna('').astype(str).str.upper().eq('ANULADO') if first(fin,['ASTRANS_ESTADO_OP_NORM','ESTADO OP']) else False
    fin['ES_EJECUCION_VALIDA']=~fin.ES_ANULADO
    fin['ES_CIERRE_PENDIENTE']=False
    fin['CENTRO_COSTO_CONCILIADO']=fin.get('DATA_CENTRO_ORDEN_COSTO',pd.Series('',index=fin.index)).fillna('')
    fin['FUENTE_CENTRO_COSTO']='NO_CONCILIADO_HISTORICO'
    fin['RESULTADO_SERVICIO']='HISTORICO_SIN_VALIDAR'
    fin['ESTADO_TRAZABILIDAD']='NO_VALIDADO'
if legacy:pat_detalle=pd.DataFrame()
for c in ['DATA_CANCELADO','EJECUCION_CONFIRMADA_ASTRANS','PAT_TIENE_SEV']:
    op[c]=boolean(op[c]) if c in op else False
for c in ['ES_ANULADO','ES_EJECUCION_VALIDA','ES_CIERRE_PENDIENTE']:
    fin[c]=boolean(fin[c]) if c in fin else False
for c in ['V_CLIENTE_NUM','V_CONDUCT_NUM','MARGEN_CALCULADO']:
    fin[c]=pd.to_numeric(fin[c],errors='coerce').fillna(0)
for c in ['DATA_CENTRO_ORDEN_COSTO','DATA_TIPO_VEHICULO','DATA_MODALIDAD','DATA_ORIGEN','DATA_DESTINO','DATA_ESTADO_SERVICIO','ESTADO_FINAL_SOLICITUD','ALERTA_CONCILIACION']:
    if c not in op:op[c]=''
for c in ['CENTRO_COSTO_CONCILIADO','FUENTE_CENTRO_COSTO','RESULTADO_SERVICIO','ESTADO_TRAZABILIDAD','ASTRANS_REMESA_NORM']:
    if c not in fin:fin[c]=''

op=periodo(op,'DATA_FECHA_SERVICIO');fin=periodo(fin,'ASTRANS_FECHA_SERVICIO')
fin['MES_CARGA']=pd.to_datetime(fin.ASTRANS_FECHA_CARGA,errors='coerce',dayfirst=True).dt.strftime('%Y-%m')
# PAT se mide con sus registros originales, NO con el estado inicial de DATA.
# Una solicitud con varias filas PAT cuenta una sola vez por fecha + orden.
# La remesa SEV prevalece ante un estado cancelado contradictorio.
if not pat_detalle.empty:
    pat_detalle['PAT_FECHA_SERVICIO']=pd.to_datetime(pat_detalle['PAT_FECHA_SERVICIO'],errors='coerce',dayfirst=True)
    if 'LLAVE_DATA_PAT' not in pat_detalle:
        pat_detalle['LLAVE_DATA_PAT']=key(pat_detalle['PAT_FECHA_SERVICIO'],pat_detalle['PAT_ORDEN_SERVICIO'])
    if 'PAT_TIENE_SEV' not in pat_detalle:
        pat_detalle['PAT_TIENE_SEV']=pat_detalle['PAT_REMESAS_ORIGINAL'].fillna('').map(lambda x:bool(remesas(x)))
    else:pat_detalle['PAT_TIENE_SEV']=boolean(pat_detalle['PAT_TIENE_SEV'])
    if 'PAT_CANCELADO' not in pat_detalle:
        pat_detalle['PAT_CANCELADO']=pat_detalle['PAT_ESTADO'].fillna('').map(lambda x:'CANCEL' in norm(x)) | pat_detalle['PAT_REMESAS_ORIGINAL'].fillna('').map(lambda x:'CANCEL' in norm(x))
    else:pat_detalle['PAT_CANCELADO']=boolean(pat_detalle['PAT_CANCELADO'])
    pat_detalle['PAT_CENTRO_ORDEN_COSTO']=pat_detalle.get('PAT_CENTRO_ORDEN_COSTO',pd.Series('',index=pat_detalle.index)).fillna('').astype(str)
    pat_detalle=pat_detalle[pat_detalle.PAT_FECHA_SERVICIO.notna()].copy()
    pat_detalle=periodo(pat_detalle,'PAT_FECHA_SERVICIO')
else:
    pat_detalle=pd.DataFrame(columns=['MES','LLAVE_DATA_PAT','PAT_TIENE_SEV','PAT_CANCELADO','PAT_CENTRO_ORDEN_COSTO'])

with st.sidebar:
    st.header('🔎 Filtros del informe')
    meses=sorted(set(op.MES.dropna().astype(str))|set(fin.MES.dropna().astype(str)))
    sel_mes=st.multiselect('Meses',meses,default=meses)
    if not sel_mes:sel_mes=meses
    periodicidad=st.selectbox('Periodicidad',['Mensual','Bimestral','Trimestral','Semestral'])
    pcol={'Mensual':'MES','Bimestral':'BIMESTRE','Trimestral':'TRIMESTRE','Semestral':'SEMESTRE'}[periodicidad]
    centros=sorted((set(op.DATA_CENTRO_ORDEN_COSTO.dropna().astype(str))|set(fin.CENTRO_COSTO_CONCILIADO.dropna().astype(str)))-{'','nan','None'})
    sel_centro=st.multiselect('Centro de costo (selección múltiple)',centros)
    sel_veh=st.multiselect('Tipo de vehículo DATA',sorted(set(op.DATA_TIPO_VEHICULO.dropna().astype(str)) - {'','nan'}))
    sel_modal=st.multiselect('Modalidad DATA',sorted(set(op.DATA_MODALIDAD.dropna().astype(str)) - {'','nan'}))
    fecha_fin=st.selectbox('Periodo financiero',['Fecha del servicio','Fecha de carga'])
    solo_conciliado=st.checkbox('Solo centros financieros conciliados',value=False)

op=op[op.MES.isin(sel_mes)].copy()
fin=fin[fin[('MES' if fecha_fin=='Fecha del servicio' else 'MES_CARGA')].isin(sel_mes)].copy()
if sel_centro:
    op=op[op.DATA_CENTRO_ORDEN_COSTO.astype(str).isin(sel_centro)].copy()
    fin=fin[fin.CENTRO_COSTO_CONCILIADO.astype(str).isin(sel_centro)].copy()
if sel_veh:op=op[op.DATA_TIPO_VEHICULO.astype(str).isin(sel_veh)].copy()
if sel_modal:op=op[op.DATA_MODALIDAD.astype(str).isin(sel_modal)].copy()
if sel_centro and not pat_detalle.empty:
    pat_detalle=pat_detalle[pat_detalle.PAT_CENTRO_ORDEN_COSTO.astype(str).isin(sel_centro)].copy()
if sel_veh or sel_modal:
    # PAT no tiene la misma granularidad de vehículo/modalidad; restringir a órdenes DATA filtradas.
    pat_detalle=pat_detalle[pat_detalle.LLAVE_DATA_PAT.isin(set(op.LLAVE_DATA_PAT))].copy()
pat_detalle=pat_detalle[pat_detalle.MES.isin(sel_mes)].copy()
if solo_conciliado:fin=fin[fin.FUENTE_CENTRO_COSTO.astype(str).isin(['DATA','PAT'])].copy()
if fecha_fin=='Fecha de carga':fin=periodo(fin,'ASTRANS_FECHA_CARGA')

# KPI financiero: una remesa por código, sin contar duplicados ni anulados.
valid=fin[fin.ES_EJECUCION_VALIDA & ~fin.ES_ANULADO].copy()
valid['ASTRANS_REMESA_NORM']=valid.ASTRANS_REMESA_NORM.fillna('').astype(str)
con_remesa=valid[valid.ASTRANS_REMESA_NORM.str.startswith('SEV')].copy()
duplicados=con_remesa[con_remesa.duplicated('ASTRANS_REMESA_NORM',keep=False)].copy()
fin_unico=con_remesa.drop_duplicates('ASTRANS_REMESA_NORM').copy()
# Registros sin remesa se muestran en control, no se mezclan en el monto verificado.
fin_sin_sev=valid[~valid.ASTRANS_REMESA_NORM.str.startswith('SEV')].copy()
importe=fin_unico.V_CLIENTE_NUM.sum();costo=fin_unico.V_CONDUCT_NUM.sum();margen=importe-costo
sol=len(op);inic_cancel=int(op.DATA_CANCELADO.sum());inic_gest=sol-inic_cancel
fin_cancel=int(op.ESTADO_FINAL_SOLICITUD.isin(['CANCELADO_CONFIRMADO_PAT','CANCELADO_DATA_SIN_PAT']).sum()) if not legacy else None
confirm=int(op.EJECUCION_CONFIRMADA_ASTRANS.sum()) if not legacy else None
sev_pat=int(op.PAT_TIENE_SEV.sum()) if not legacy else None
st.subheader('Indicadores gerenciales')
for cols,items in [(st.columns(6),[('Solicitudes DATA',fmt(sol)),('Gestionadas iniciales',fmt(inic_gest)),('Canceladas DATA',fmt(inic_cancel)),('Canceladas finales',fmt(fin_cancel) if fin_cancel is not None else 'N/D'),('Con SEV en PAT',fmt(sev_pat) if sev_pat is not None else 'N/D'),('Ejecutadas conciliadas',fmt(confirm) if confirm is not None else 'N/D')]),(st.columns(6),[('Remesas únicas ASTRANS',fmt(len(fin_unico))),('Facturación',cop(importe)),('Costos',cop(costo)),('Margen',cop(margen)),('Rentabilidad',pct(margen/importe*100 if importe else 0)),('Ticket promedio',cop(importe/len(fin_unico) if len(fin_unico) else 0))])]:
    for c,(k,v) in zip(cols,items):c.metric(k,v)
st.caption('El volumen DATA representa solicitudes; PAT registra resultado; TRAYECTOS aporta remesas y valores. Las cifras financieras mostradas excluyen anulados y duplicados de remesa, sujetos a revisión.')

op['ES_CANCELACION_FINAL']=op.ESTADO_FINAL_SOLICITUD.isin(['CANCELADO_CONFIRMADO_PAT','CANCELADO_DATA_SIN_PAT'])
op['CON_SEV_PAT']=op.PAT_TIENE_SEV
op_mes=op.groupby(pcol,as_index=False).agg(SOLICITUDES=('DATA_CANCELADO','size'),GESTIONADAS=('DATA_CANCELADO',lambda s:(~s).sum()),CANCELADAS_DATA=('DATA_CANCELADO','sum'),CANCELADAS_FINALES=('ES_CANCELACION_FINAL','sum'),CON_SEV_PAT=('CON_SEV_PAT','sum'),EJECUTADAS_CONCILIADAS=('EJECUCION_CONFIRMADA_ASTRANS','sum')).rename(columns={pcol:'PERIODO'}).sort_values('PERIODO')
for m in ['SOLICITUDES','GESTIONADAS','CANCELADAS_DATA','CANCELADAS_FINALES','CON_SEV_PAT','EJECUTADAS_CONCILIADAS']:
    op_mes['VAR_'+m+'_%']=op_mes[m].pct_change(fill_method=None)*100
op_mes['TASA_CANCEL_DATA_%']=np.where(op_mes.SOLICITUDES>0,op_mes.CANCELADAS_DATA/op_mes.SOLICITUDES*100,0)
op_mes['TASA_CANCEL_FINAL_%']=np.where(op_mes.SOLICITUDES>0,op_mes.CANCELADAS_FINALES/op_mes.SOLICITUDES*100,0)
# Resumen PAT con deduplicación por solicitud. Estados contradictorios: gana SEV.
if not pat_detalle.empty:
    pat_solicitudes=(pat_detalle.groupby('LLAVE_DATA_PAT',as_index=False)
        .agg(PAT_FECHA_SERVICIO=('PAT_FECHA_SERVICIO','min'),
             PAT_TIENE_SEV=('PAT_TIENE_SEV','max'),
             PAT_CANCELADO=('PAT_CANCELADO','max'),
             PAT_FILAS=('LLAVE_DATA_PAT','size')))
    pat_solicitudes=periodo(pat_solicitudes,'PAT_FECHA_SERVICIO')
    pat_solicitudes['PAT_CANCELADO_FINAL']=pat_solicitudes.PAT_CANCELADO & ~pat_solicitudes.PAT_TIENE_SEV
    pat_solicitudes['PAT_GESTIONADO']=~pat_solicitudes.PAT_CANCELADO_FINAL
    pat_mes=(pat_solicitudes.groupby(pcol,as_index=False)
        .agg(GESTIONADOS_PAT=('PAT_GESTIONADO','sum'),CANCELADOS_PAT=('PAT_CANCELADO_FINAL','sum'),
             TOTAL_PAT=('LLAVE_DATA_PAT','size'),CON_SEV_PAT=('PAT_TIENE_SEV','sum'))
        .rename(columns={pcol:'PERIODO'}))
else:
    pat_mes=pd.DataFrame(columns=['PERIODO','GESTIONADOS_PAT','CANCELADOS_PAT','TOTAL_PAT','CON_SEV_PAT'])
comparativo_pat=op_mes[['PERIODO','SOLICITUDES','CANCELADAS_DATA']].merge(pat_mes,on='PERIODO',how='outer').sort_values('PERIODO')
comparativo_pat['TASA_CANCELACION_PAT_%']=np.where(comparativo_pat.SOLICITUDES.gt(0),comparativo_pat.CANCELADOS_PAT/comparativo_pat.SOLICITUDES*100,np.nan)
comparativo_pat['COBERTURA_PAT_%']=np.where(comparativo_pat.SOLICITUDES.gt(0),comparativo_pat.TOTAL_PAT/comparativo_pat.SOLICITUDES*100,np.nan)
fin_mes=fin_unico.groupby(pcol,as_index=False).agg(REMESAS=('ASTRANS_REMESA_NORM','nunique'),FACTURACION=('V_CLIENTE_NUM','sum'),COSTOS=('V_CONDUCT_NUM','sum')).rename(columns={pcol:'PERIODO'}).sort_values('PERIODO')
fin_mes['MARGEN']=fin_mes.FACTURACION-fin_mes.COSTOS
fin_mes['MARGEN_%']=np.where(fin_mes.FACTURACION.ne(0),fin_mes.MARGEN/fin_mes.FACTURACION*100,0)
fin_mes['TICKET_PROMEDIO']=np.where(fin_mes.REMESAS.ne(0),fin_mes.FACTURACION/fin_mes.REMESAS,0)
for m in ['REMESAS','FACTURACION','COSTOS','MARGEN','TICKET_PROMEDIO']:
    fin_mes['VAR_'+m+'_%']=fin_mes[m].pct_change(fill_method=None)*100

names=['🏢 Resumen ejecutivo','📋 DATA estados','📊 Estados detallados','🔗 PAT y conciliación','❌ Cancelaciones','🚦 Realizados vs cancelados','📈 Producción y variaciones','💰 Financiero','🎬 Centros de costo','🚙 Vehículo y modalidad','🗺 Mapas de calor','⚠️ Trazabilidad','📥 Exportar']
tabs=st.tabs(names)
with tabs[0]:
    c1,c2=st.columns(2)
    with c1:st.plotly_chart(barras(op_mes,'PERIODO','SOLICITUDES','Solicitudes iniciales y variación'),use_container_width=True)
    with c2:st.plotly_chart(barras(fin_mes,'PERIODO','FACTURACION','Facturación y variación',moneda=True,color='#F58220'),use_container_width=True)
    st.plotly_chart(linea(op_mes,'PERIODO',['SOLICITUDES','GESTIONADAS','CANCELADAS_DATA'],'Demanda, gestión y cancelaciones iniciales'),use_container_width=True)
    st.dataframe(op_mes.merge(fin_mes,on='PERIODO',how='outer'),hide_index=True,use_container_width=True)
    st.info('Una reducción de solicitudes por producción puede corresponder al cierre natural del proyecto audiovisual. No se considera cancelación sin evidencia del estado. Los montos por centro solo se atribuyen cuando hay conciliación.')
with tabs[1]:
    c1,c2=st.columns(2)
    with c1:st.plotly_chart(donut(op,'DATA_ESTADO_SERVICIO','Estados iniciales DATA'),use_container_width=True)
    with c2:st.plotly_chart(barras(op_mes,'PERIODO','GESTIONADAS','Gestión inicial y variación'),use_container_width=True)
    st.dataframe(op.groupby('DATA_ESTADO_SERVICIO',dropna=False).size().reset_index(name='CANTIDAD').sort_values('CANTIDAD',ascending=False),hide_index=True,use_container_width=True)
with tabs[2]:
    st.subheader('Evolución mensual del estado operativo detallado — DATA')
    detalle=op.groupby(['MES','DATA_ESTADO_SERVICIO'],dropna=False).size().reset_index(name='SERVICIOS')
    if not detalle.empty:
        fig=px.bar(detalle,x='MES',y='SERVICIOS',color='DATA_ESTADO_SERVICIO',barmode='group',text='SERVICIOS',title='Evolución mensual del estado operativo detallado')
        fig.update_traces(textposition='outside',textfont=dict(size=10,color='#172B4D'),cliponaxis=False)
        estilo(fig,'Evolución mensual del estado operativo detallado',620);ejes_meses(fig,detalle,'MES')
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(detalle.pivot_table(index='MES',columns='DATA_ESTADO_SERVICIO',values='SERVICIOS',fill_value=0),use_container_width=True)
    else:st.info('No hay estados detallados para los filtros seleccionados.')
with tabs[3]:
    if legacy:st.warning('No se puede certificar el estado PAT final usando únicamente la base antigua. Reconstruye con las tres fuentes.')
    else:
        c1,c2=st.columns(2)
        with c1:st.plotly_chart(donut(op,'ESTADO_FINAL_SOLICITUD','Resultado final por solicitud'),use_container_width=True)
        with c2:st.plotly_chart(barras(op_mes,'PERIODO','CON_SEV_PAT','Servicios con remesa SEV'),use_container_width=True)
        st.plotly_chart(linea(op_mes,'PERIODO',['CON_SEV_PAT','EJECUTADAS_CONCILIADAS','CANCELADAS_FINALES'],'Remesa PAT, ejecución conciliada y cancelaciones'),use_container_width=True)
        st.dataframe(op.groupby('ESTADO_FINAL_SOLICITUD',dropna=False).size().reset_index(name='CANTIDAD'),hide_index=True,use_container_width=True)
with tabs[4]:
    c1,c2=st.columns(2)
    with c1:
        st.plotly_chart(barras_comparativas_con_variacion(
            comparativo_pat,[('CANCELADAS_DATA','Cancelaciones iniciales DATA'),('CANCELADOS_PAT','Cancelaciones reales PAT')],
            'Cancelaciones iniciales vs reales y variación mensual'),use_container_width=True)
    with c2:
        st.plotly_chart(linea(op_mes,'PERIODO',['TASA_CANCEL_DATA_%'],'Tasa de cancelación inicial DATA (%)',porcentaje=True),use_container_width=True)
    if not legacy:
        st.plotly_chart(comparativo_barras(op_mes,[('CANCELADAS_DATA','Canceladas inicialmente DATA'),('CANCELADAS_FINALES','Canceladas finales conciliadas')],'Seguimiento de cancelaciones iniciales vs finales'),use_container_width=True)
        st.plotly_chart(linea(op_mes,'PERIODO',['TASA_CANCEL_DATA_%','TASA_CANCEL_FINAL_%'],'Evolución de tasas de cancelación (%)',porcentaje=True),use_container_width=True)
        st.plotly_chart(pareto(op[op.ES_CANCELACION_FINAL],'DATA_CENTRO_ORDEN_COSTO','Pareto de cancelaciones finales por centro'),use_container_width=True)
    tabla_cancel=comparativo_pat[['PERIODO','SOLICITUDES','CANCELADAS_DATA','CANCELADOS_PAT','TASA_CANCELACION_PAT_%']].copy()
    tabla_cancel['VAR_INICIAL_%']=tabla_cancel.CANCELADAS_DATA.pct_change(fill_method=None)*100
    tabla_cancel['VAR_REAL_PAT_%']=tabla_cancel.CANCELADOS_PAT.pct_change(fill_method=None)*100
    tabla_cancel['DIFERENCIA_PAT_MENOS_DATA']=tabla_cancel.CANCELADOS_PAT-tabla_cancel.CANCELADAS_DATA
    st.caption('PAT sin cobertura se muestra N/D, no como cero. SEV prevalece sobre Cancelado; diferencias no significan necesariamente incumplimientos.')
    st.dataframe(tabla_cancel.style.format({'TASA_CANCELACION_PAT_%':lambda x:pct_plain(x),'VAR_INICIAL_%':lambda x:pct(x),'VAR_REAL_PAT_%':lambda x:pct(x)},na_rep='N/D'),hide_index=True,use_container_width=True)
with tabs[5]:
    st.subheader('Solicitudes DATA vs gestionados y cancelados PAT')
    st.caption('Solicitados: filas originales DATA. Gestionados PAT: órdenes únicas con resultado no cancelado o pendiente (incluye remesa SEV). Cancelados PAT: órdenes únicas canceladas sin SEV. Los meses sin cobertura PAT muestran N/D, nunca cero. Las fuentes tienen coberturas distintas.')
    if pat_mes.empty:
        st.warning('Esta Base Maestra no contiene DETALLE_PAT. Genera la Base Maestra con Data Factory actualizada o carga las tres fuentes originales para ver el resultado PAT.')
    else:
        fig=go.Figure()
        for campo,nombre,color in [('SOLICITUDES','Solicitudes iniciales DATA','#003B75'),('GESTIONADOS_PAT','Gestionados PAT','#008A3D'),('CANCELADOS_PAT','Cancelados PAT','#D43D3D')]:
            fig.add_bar(x=comparativo_pat.PERIODO,y=comparativo_pat[campo],name=nombre,marker_color=color,
                        text=[fmt(v) if pd.notna(v) else '' for v in comparativo_pat[campo]],textposition='outside',cliponaxis=False)
        fig.update_layout(barmode='group')
        estilo(fig,'Solicitudes iniciales vs gestión y cancelaciones PAT',540)
        ejes_meses(fig,comparativo_pat,'PERIODO')
        st.plotly_chart(fig,use_container_width=True)
        st.plotly_chart(linea(comparativo_pat,'PERIODO',['SOLICITUDES','GESTIONADOS_PAT','CANCELADOS_PAT'],
                             'Tendencia mensual de solicitudes y resultado PAT'),use_container_width=True)
        st.plotly_chart(linea(comparativo_pat,'PERIODO',['TASA_CANCELACION_PAT_%'],
                             'Cancelaciones finales PAT / solicitudes DATA (%)',porcentaje=True),use_container_width=True)
        st.dataframe(comparativo_pat,hide_index=True,use_container_width=True)
        st.info('Si PAT registra una remesa SEV y también un estado Cancelado, se contabiliza como gestionado y se conserva la alerta para revisión del coordinador. La cobertura PAT comienza en junio para los archivos suministrados.')
with tabs[6]:
    st.subheader('Evolución de la producción operativa: cantidades y variaciones')
    evolucion=op_mes[['PERIODO','SOLICITUDES','GESTIONADAS','CANCELADAS_DATA']].copy()
    for campo in ['SOLICITUDES','GESTIONADAS','CANCELADAS_DATA']:
        evolucion['VAR_'+campo+'_%']=evolucion[campo].pct_change(fill_method=None)*100
    fig_evol=go.Figure()
    for campo,nombre,color in [('SOLICITUDES','Solicitudes DATA','#5CAEF5'),('GESTIONADAS','Gestión inicial DATA','#003B75'),('CANCELADAS_DATA','Canceladas DATA','#D43D3D')]:
        var=evolucion['VAR_'+campo+'_%']
        textos=[f'{fmt(n)}<br>{"Base" if pd.isna(v) else pct(v)}' for n,v in zip(evolucion[campo],var)]
        fig_evol.add_scatter(x=evolucion.PERIODO,y=evolucion[campo],name=nombre,mode='lines+markers+text',
            text=textos,textposition='top center',textfont=dict(size=10,color='#172B4D'),
            line=dict(color=color,width=3),marker=dict(size=9),cliponaxis=False)
    estilo(fig_evol,'Evolución mensual: cantidad y variación respecto al periodo anterior',600)
    ejes_meses(fig_evol,evolucion,'PERIODO');fig_evol.update_layout(margin=dict(l=60,r=45,t=80,b=70))
    st.plotly_chart(fig_evol,use_container_width=True)
    st.dataframe(evolucion.style.format({c:lambda x:pct(x) for c in evolucion if c.startswith('VAR_')},na_rep='Base'),hide_index=True,use_container_width=True)
    if not legacy:st.plotly_chart(linea(op_mes,'PERIODO',['CON_SEV_PAT','EJECUTADAS_CONCILIADAS'],'SEV y ejecución conciliada'),use_container_width=True)
    st.plotly_chart(barras(fin_mes,'PERIODO','REMESAS','Remesas ejecutadas y variación'),use_container_width=True)
    st.dataframe(op_mes,hide_index=True,use_container_width=True)
with tabs[7]:
    c1,c2=st.columns(2)
    with c1:st.plotly_chart(barras(fin_mes,'PERIODO','FACTURACION','Facturación y variación',moneda=True),use_container_width=True)
    with c2:st.plotly_chart(barras(fin_mes,'PERIODO','MARGEN','Margen y variación',moneda=True,color='#008A3D'),use_container_width=True)
    st.plotly_chart(linea(fin_mes,'PERIODO',['FACTURACION','COSTOS','MARGEN'],'Facturación, costos y margen'),use_container_width=True)
    st.plotly_chart(linea(fin_mes,'PERIODO',['MARGEN_%'],'Rentabilidad mensual (%)',porcentaje=True),use_container_width=True)
    st.dataframe(fin_mes,hide_index=True,use_container_width=True)
with tabs[8]:
    st.plotly_chart(pareto(op,'DATA_CENTRO_ORDEN_COSTO','Pareto solicitudes por centro'),use_container_width=True)
    top=op.DATA_CENTRO_ORDEN_COSTO.value_counts().head(12).index
    evol=op[op.DATA_CENTRO_ORDEN_COSTO.isin(top)].groupby(['MES','DATA_CENTRO_ORDEN_COSTO']).size().reset_index(name='SOLICITUDES')
    if not evol.empty:
        malla=pd.MultiIndex.from_product([sorted(op.MES.dropna().unique()),list(top)],names=['MES','DATA_CENTRO_ORDEN_COSTO']).to_frame(index=False)
        evol=malla.merge(evol,on=['MES','DATA_CENTRO_ORDEN_COSTO'],how='left').fillna({'SOLICITUDES':0})
        fig=px.line(evol,x='MES',y='SOLICITUDES',color='DATA_CENTRO_ORDEN_COSTO',markers=True,title='Evolución mensual por centro de costo (top 12)')
        estilo(fig,'Evolución mensual por centro de costo (top 12)',580);ejes_meses(fig,evol,'MES');st.plotly_chart(fig,use_container_width=True)
    st.subheader('Tabla de evolución por producción — incluye meses con cero solicitudes')
    st.caption('0 = ninguna solicitud registrada para esa producción en el mes; no significa necesariamente que se perdió el cliente.')
    tabla_centros=tabla_mensual_completa(op,'MES','DATA_CENTRO_ORDEN_COSTO','SOLICITUDES',sorted(op.MES.dropna().unique()),top=20)
    st.dataframe(tabla_centros,hide_index=True,use_container_width=True)
    st.download_button('📥 Descargar tabla de centros de costo (CSV)',tabla_centros.to_csv(index=False).encode('utf-8-sig'),file_name='RCN_CENTROS_COSTO_MENSUAL.csv',mime='text/csv')
    fcent=fin_unico[fin_unico.FUENTE_CENTRO_COSTO.isin(['DATA','PAT'])]
    if not fcent.empty:
        st.subheader('Financiero por centro conciliado')
        st.dataframe(fcent.groupby('CENTRO_COSTO_CONCILIADO',as_index=False).agg(REMESAS=('ASTRANS_REMESA_NORM','nunique'),FACTURACION=('V_CLIENTE_NUM','sum'),COSTOS=('V_CONDUCT_NUM','sum'),MARGEN=('MARGEN_CALCULADO','sum')).sort_values('FACTURACION',ascending=False),hide_index=True,use_container_width=True)
    st.caption(f'Remesas únicas sin centro de costo conciliado: {len(fin_unico)-len(fcent)}. No se asignan ingresos a producciones por suposición.')
with tabs[9]:
    v=first(fin_unico,['T. VEHICULO','T.VEHICULO','T VEHICULO'])
    m=first(fin_unico,['T.NEGOCIO','TRAY. PROP','LINEA NEG'])
    c1,c2=st.columns(2)
    with c1:
        veh_base=fin_unico if v else op
        veh_campo=v if v else 'DATA_TIPO_VEHICULO'
        fig_veh,tabla_veh=ranking_vehiculos(veh_base,veh_campo,'Ranking de tipos de vehículo — cantidad y participación')
        st.plotly_chart(fig_veh,use_container_width=True)
        st.dataframe(tabla_veh.style.format({'PARTICIPACION_%':lambda x:pct_plain(x)}),hide_index=True,use_container_width=True)
        st.caption('Ranking horizontal en lugar de dona: los tipos de baja participación siguen siendo legibles.')
    with c2:
        if m:st.plotly_chart(donut(fin_unico,m,'Modalidad / negocio'),use_container_width=True)
        else:st.plotly_chart(donut(op,'DATA_MODALIDAD','Modalidad solicitada'),use_container_width=True)
    if 'PLACA' in fin_unico:st.dataframe(fin_unico.groupby('PLACA').size().reset_index(name='REMESAS').sort_values('REMESAS',ascending=False).head(20),hide_index=True,use_container_width=True)
with tabs[10]:
    origen=first(fin_unico,['ORIGEN','ASTRANS_ORIGEN']);destino=first(fin_unico,['DESTINO','ASTRANS_DESTINO'])
    fig=mapa_calor(fin_unico,origen,destino,'Mapa de calor de rutas ejecutadas — Origen × Destino')
    if fig:st.plotly_chart(fig,use_container_width=True)
    else:st.info('No hay suficientes orígenes y destinos en los registros ejecutados seleccionados.')
    fig2=mapa_calor(op,'DATA_ORIGEN','DATA_DESTINO','Mapa de calor de solicitudes — Origen × Destino')
    if fig2:st.plotly_chart(fig2,use_container_width=True)
    st.subheader('Trayectos iniciales DATA vs trayectos ejecutados ASTRANS')
    st.caption('DATA refleja solicitudes por origen–destino; ASTRANS refleja remesas ejecutadas. Son unidades de distinta fuente y su diferencia no es una tasa de incumplimiento.')
    fig_rutas=comparativo_barras(op_mes.merge(fin_mes[['PERIODO','REMESAS']],on='PERIODO',how='left'),
        [('SOLICITUDES','Trayectos solicitados DATA'),('REMESAS','Trayectos ejecutados ASTRANS')],
        'Trayectos solicitados vs ejecutados por periodo')
    st.plotly_chart(fig_rutas,use_container_width=True)
    tabla_rutas=tabla_rutas_iniciales_vs_reales(op,fin_unico)
    if not tabla_rutas.empty:
        st.dataframe(tabla_rutas.head(50),hide_index=True,use_container_width=True)
    else:st.info('No hay pares origen–destino comparables con los filtros actuales.')
with tabs[11]:
    st.metric('Casos para coordinador',len(rev))
    if not rev.empty:st.dataframe(rev,use_container_width=True,hide_index=True)
    else:st.info('Sin alertas disponibles en el libro seleccionado.')
    if not fin.empty:st.dataframe(fin.groupby('ESTADO_TRAZABILIDAD').size().reset_index(name='FILAS'),hide_index=True,use_container_width=True)
    st.metric('Remesas duplicadas en registros ejecutados',len(duplicados))
    st.metric('Registros ejecutados sin remesa SEV',len(fin_sin_sev))
    if not duplicados.empty:st.dataframe(duplicados,hide_index=True,use_container_width=True)
    st.warning('SEV prevalece sobre Estado Cancelado de PAT. El caso debe corregirse con el coordinador, sin alterar el registro original.')
with tabs[12]:
    hojas_export={'RESUMEN_OPERATIVO':op_mes,'RESUMEN_FINANCIERO':fin_mes,
        'CANCELACIONES_COMPARATIVO':comparativo_pat,'CENTROS_MENSUALES':tabla_mensual_completa(op,'MES','DATA_CENTRO_ORDEN_COSTO','SOLICITUDES',sorted(op.MES.dropna().unique()),top=30),
        'TRAYECTOS_RUTAS':tabla_rutas_iniciales_vs_reales(op,fin_unico),'SOLICITUDES_FILTRADAS':op,'TRAYECTOS_FILTRADOS':fin,'REMESAS_UNICAS':fin_unico,'REVISION_COORDINADOR':rev,'REMESAS_DUPLICADAS':duplicados,'SIN_SEV':fin_sin_sev}
    st.download_button('📥 Descargar informe ejecutivo Excel',exportar(hojas_export),file_name='RCN_INFORME_EJECUTIVO_V11.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')
    st.caption('Las variaciones comparan periodos seleccionados consecutivos. Cuando se filtran meses no contiguos, se comparan únicamente los periodos visibles.')
