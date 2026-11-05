"""RCN Informe Ejecutivo V9 — consume BASE_MAESTRA_RCN_ACTUALIZADA.xlsx.
Ejecutar: streamlit run app.py
"""
import io
import re
import unicodedata
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='RCN Informe Ejecutivo V9',page_icon='📊',layout='wide')
st.markdown('''<style>.block-container{padding-top:1rem}h1,h2,h3{color:#003B75!important}div[data-testid="stMetric"]{border:1px solid #dbe4ef;border-radius:10px;padding:12px}div[data-testid="stDataFrame"]{font-size:12px}</style>''',unsafe_allow_html=True)
st.title('📊 RCN | Informe Ejecutivo Operativo y Financiero V9')
st.caption('Solicitudes DATA · Resultado PAT · Ejecución y finanzas TRAYECTOS · Trazabilidad de remesas SEV')


def norm(x):
    if pd.isna(x):return ''
    return ''.join(c for c in unicodedata.normalize('NFKD',str(x).upper().strip()) if not unicodedata.combining(c))


def periodos(d,fecha):
    d=d.copy();dt=pd.to_datetime(d[fecha],errors='coerce')
    d['MES']=dt.dt.strftime('%Y-%m');d['ANO']=dt.dt.year
    d['BIMESTRE']=dt.dt.year.astype('Int64').astype(str)+'-B'+(((dt.dt.month-1)//2)+1).astype('Int64').astype(str)
    d['TRIMESTRE']=dt.dt.year.astype('Int64').astype(str)+'-T'+(((dt.dt.month-1)//3)+1).astype('Int64').astype(str)
    d['SEMESTRE']=dt.dt.year.astype('Int64').astype(str)+'-S'+(((dt.dt.month-1)//6)+1).astype('Int64').astype(str)
    return d


def fmt(n):return f'{n:,.0f}'.replace(',','.')

def cop(n):return '$ '+fmt(n)+' COP'

def pct(n):return f'{n:.2f}%'.replace('.',',')

def bar(d,x,y,title,color='#003B75'):
    fig=px.bar(d,x=x,y=y,text=y,title=title)
    fig.update_traces(marker_color=color,textposition='outside')
    fig.update_layout(height=430,plot_bgcolor='white',paper_bgcolor='white',font_color='#253047',margin=dict(l=20,r=20,t=55,b=40))
    return fig


def table_agg(d,group,metric):
    if d.empty:return pd.DataFrame(columns=[group,metric])
    return d.groupby(group,dropna=False).size().reset_index(name=metric).sort_values(group)


def exportar(hojas):
    buf=io.BytesIO()
    with pd.ExcelWriter(buf,engine='xlsxwriter',datetime_format='dd/mm/yyyy') as w:
        for name,d in hojas.items():
            d.to_excel(w,sheet_name=name[:31],index=False)
            ws=w.sheets[name[:31]];ws.freeze_panes(1,0)
            if len(d.columns):
                ws.autofilter(0,0,len(d),len(d.columns)-1)
                fmt_head=w.book.add_format({'bold':True,'font_color':'white','bg_color':'#003B75'})
                for i,c in enumerate(d.columns):ws.write(0,i,c,fmt_head);ws.set_column(i,i,min(36,max(15,len(c)+2)))
    return buf.getvalue()

st.info('📌 Esta aplicación requiere la Base Maestra **V9** generada con la aplicación **Data Factory V9**. Una Base Maestra V8 o anterior no contiene todas las hojas necesarias para la conciliación.')
f=st.file_uploader('Cargar BASE_MAESTRA_RCN_ACTUALIZADA.xlsx (generada por Data Factory V9)',type=['xlsx'])
if not f:
    st.info('Primero ejecuta **app (1).py**, carga DATA RCN, SERVICIO PAT y TRAYECTOS TODOS, y descarga la nueva Base Maestra. Luego cárgala aquí.')
    st.stop()
try:
    raw=f.getvalue()
    book=pd.ExcelFile(io.BytesIO(raw))
except Exception as e:
    st.error('No se pudo abrir el archivo Excel. Verifica que sea un libro .xlsx válido y que no esté dañado.')
    st.caption(f'Detalle técnico: {e}')
    st.stop()
required=['BASE_SOLICITUDES','BASE_MAESTRA_RCN','REVISION_COORDINADOR']
missing=[name for name in required if name not in book.sheet_names]
if missing:
    st.error('**Archivo incompatible: la Base Maestra cargada no corresponde al formato V9.**')
    st.write('**Hojas encontradas:** '+', '.join(f'`{name}`' for name in book.sheet_names))
    st.write('**Hojas faltantes:** '+', '.join(f'`{name}`' for name in missing))
    st.warning('No es posible calcular de forma confiable los resultados finales de PAT, la prioridad de las remesas SEV y las alertas de revisión del coordinador a partir de esta base antigua.')
    st.markdown('''**Cómo solucionarlo:**
    1. Abre la aplicación **RCN Data Factory V9** (`app (1).py`).
    2. Carga los archivos originales **DATA RCN**, **SERVICIO PAT** y **TRAYECTOS TODOS**.
    3. Descarga el Excel **BASE_MAESTRA_RCN_ACTUALIZADA.xlsx**.
    4. Regresa aquí y reemplaza el archivo cargado por el Excel recién generado.

    **Importante:** cambiar el nombre de un archivo V8 a V9 no lo convierte; es necesario volver a procesar las tres fuentes.''')
    st.stop()
try:
    op=pd.read_excel(io.BytesIO(raw),sheet_name='BASE_SOLICITUDES')
    fin=pd.read_excel(io.BytesIO(raw),sheet_name='BASE_MAESTRA_RCN')
    rev=pd.read_excel(io.BytesIO(raw),sheet_name='REVISION_COORDINADOR')
    columnas_op=['DATA_FECHA_SERVICIO','DATA_CANCELADO','COINCIDE_PAT','EJECUCION_CONFIRMADA_ASTRANS','DATA_CENTRO_ORDEN_COSTO']
    columnas_fin=['ASTRANS_FECHA_SERVICIO','ASTRANS_FECHA_CARGA','V_CLIENTE_NUM','V_CONDUCT_NUM','MARGEN_CALCULADO','ES_EJECUCION_VALIDA','ES_ANULADO','ES_CIERRE_PENDIENTE','CENTRO_COSTO_CONCILIADO']
    faltan_op=[c for c in columnas_op if c not in op.columns]
    faltan_fin=[c for c in columnas_fin if c not in fin.columns]
    if faltan_op or faltan_fin:
        st.error('El archivo tiene las hojas V9, pero faltan columnas obligatorias para el informe.')
        if faltan_op:st.write('**BASE_SOLICITUDES:** '+', '.join(f'`{c}`' for c in faltan_op))
        if faltan_fin:st.write('**BASE_MAESTRA_RCN:** '+', '.join(f'`{c}`' for c in faltan_fin))
        st.info('Vuelve a generar el libro usando la Data Factory V9 incluida en el mismo paquete que este informe.')
        st.stop()
    for c in ['V_CLIENTE_NUM','V_CONDUCT_NUM','MARGEN_CALCULADO']:
        fin[c]=pd.to_numeric(fin[c],errors='coerce').fillna(0)
    for c in ['DATA_CANCELADO','COINCIDE_PAT','EJECUCION_CONFIRMADA_ASTRANS']:
        op[c]=op[c].fillna(False).astype(bool)
    for c in ['ES_EJECUCION_VALIDA','ES_ANULADO','ES_CIERRE_PENDIENTE']:
        fin[c]=fin[c].fillna(False).astype(bool)
    op=periodos(op,'DATA_FECHA_SERVICIO')
    fin=periodos(fin,'ASTRANS_FECHA_SERVICIO')
    fin['MES_CARGA']=pd.to_datetime(fin.ASTRANS_FECHA_CARGA,errors='coerce').dt.strftime('%Y-%m')
except Exception as e:
    st.error('No fue posible preparar la Base Maestra V9 para el informe. Comprueba que se haya generado completamente.')
    with st.expander('Ver detalle técnico'):
        st.exception(e)
    st.stop()

# Los filtros se aplican sobre la misma llave de servicio o sobre el centro conciliado.
with st.sidebar:
    st.header('🔎 Filtros')
    meses=sorted(set(op.MES.dropna()) | set(fin.MES.dropna()))
    elegidos=st.multiselect('Meses',meses,default=meses)
    if not elegidos:elegidos=meses
    periodicidad=st.selectbox('Periodicidad',['Mensual','Bimestral','Trimestral','Semestral'])
    pcol={'Mensual':'MES','Bimestral':'BIMESTRE','Trimestral':'TRIMESTRE','Semestral':'SEMESTRE'}[periodicidad]
    centros=sorted(set(op.DATA_CENTRO_ORDEN_COSTO.dropna().astype(str)) | set(fin.CENTRO_COSTO_CONCILIADO.dropna().astype(str)))
    centros=[c for c in centros if c and c.lower()!='nan']
    centros_sel=st.multiselect('Centro / Orden de costo',centros)
    tipo_fecha=st.radio('Fecha para análisis financiero',['Fecha del servicio','Fecha de carga'],index=0,help='La fecha del servicio permite comparar actividad; la fecha de carga sirve para conciliación administrativa.')
    solo_conciliados=st.checkbox('Financiero: solo centros conciliados',value=False)

op=op[op.MES.isin(elegidos)].copy()
fin=fin[fin[('MES' if tipo_fecha=='Fecha del servicio' else 'MES_CARGA')].isin(elegidos)].copy()
if centros_sel:
    op=op[op.DATA_CENTRO_ORDEN_COSTO.astype(str).isin(centros_sel)].copy()
    fin=fin[fin.CENTRO_COSTO_CONCILIADO.astype(str).isin(centros_sel)].copy()
if solo_conciliados:fin=fin[fin.FUENTE_CENTRO_COSTO.ne('SIN_CONCILIAR')].copy()
if tipo_fecha=='Fecha de carga':
    fin=periodos(fin,'ASTRANS_FECHA_CARGA')

op['ESTADO_FINAL_SOLICITUD']=op.ESTADO_FINAL_SOLICITUD.fillna('PENDIENTE_CONCILIACION')
fin['RESULTADO_SERVICIO']=fin.RESULTADO_SERVICIO.fillna('REVISAR_ESTADO_ASTRANS')
solicitudes=len(op)
inicial_gestionados=int((~op.DATA_CANCELADO).sum())
inicial_cancelados=int(op.DATA_CANCELADO.sum())
final_cancelados=int(op.ESTADO_FINAL_SOLICITUD.isin(['CANCELADO_CONFIRMADO_PAT','CANCELADO_DATA_SIN_PAT']).sum())
con_remesa=int(op.ESTADO_FINAL_SOLICITUD.isin(['PRESTADO_CON_REMESA','EJECUTADO_CONCILIADO']).sum())
confirmados=int(op.EJECUCION_CONFIRMADA_ASTRANS.sum())
pendientes=int(op.ESTADO_FINAL_SOLICITUD.eq('PENDIENTE_CONCILIACION').sum())
valid_fin=fin[fin.ES_EJECUCION_VALIDA & ~fin.ES_ANULADO].copy()
# No sumar remesas repetidas dos veces sin alertarlo: conservar detalle, usar una fila por remesa para KPIs.
con_sev=valid_fin[valid_fin.ASTRANS_REMESA_NORM.fillna('').astype(str).ne('')].copy()
con_sev['DUPLICADO_REMESA']=con_sev.duplicated('ASTRANS_REMESA_NORM',keep=False)
fin_unico=con_sev.drop_duplicates('ASTRANS_REMESA_NORM',keep='first').copy()
fin_sin_sev=valid_fin[valid_fin.ASTRANS_REMESA_NORM.fillna('').astype(str).eq('')].copy()
# Registros sin remesa se conservan en control, pero NO se agregan al financiero verificado.
importe=float(fin_unico.V_CLIENTE_NUM.sum());costo=float(fin_unico.V_CONDUCT_NUM.sum());margen=importe-costo
n_ejecutados=len(fin_unico);ticket=importe/n_ejecutados if n_ejecutados else 0

st.subheader('Indicadores principales')
a=st.columns(6)
for box,label,val in zip(a,['Solicitudes DATA','Gestionados iniciales','Cancelados DATA','Cancelados finales','Con remesa PAT','Ejecutados conciliados'],
                         [solicitudes,inicial_gestionados,inicial_cancelados,final_cancelados,con_remesa,confirmados]):box.metric(label,fmt(val))
b=st.columns(6)
for box,label,val in zip(b,['Pendientes','Remesas ejecutadas únicas','Facturación verificada','Costos','Margen','Rentabilidad'],
                         [fmt(pendientes),fmt(n_ejecutados),cop(importe),cop(costo),cop(margen),pct(100*margen/importe if importe else 0)]):box.metric(label,val)
st.caption('Cancelaciones finales = cancelado PAT o cancelado DATA sin PAT. Una remesa SEV prevalece sobre Estado Cancelado en PAT. Los servicios PAT sin confirmación ASTRANS se muestran aparte.')

op_mes=op.groupby(pcol,as_index=False).agg(SOLICITUDES=('DATA_ID','count'),GESTIONADOS_INICIALES=('DATA_CANCELADO',lambda x:(~x).sum()),CANCELADOS_INICIALES=('DATA_CANCELADO','sum'),CANCELADOS_FINALES=('ESTADO_FINAL_SOLICITUD',lambda x:x.isin(['CANCELADO_CONFIRMADO_PAT','CANCELADO_DATA_SIN_PAT']).sum()),CON_REMESA_PAT=('ESTADO_FINAL_SOLICITUD',lambda x:x.isin(['PRESTADO_CON_REMESA','EJECUTADO_CONCILIADO']).sum()),EJECUTADOS_CONCILIADOS=('EJECUCION_CONFIRMADA_ASTRANS','sum')).sort_values(pcol)
op_mes['TASA_CANCELACION_FINAL_%']=np.where(op_mes.SOLICITUDES.gt(0),op_mes.CANCELADOS_FINALES/op_mes.SOLICITUDES*100,0)
op_mes['VAR_SOLICITUDES_%']=op_mes.SOLICITUDES.pct_change()*100
fin_mes=fin_unico.groupby(pcol,as_index=False).agg(REMESAS=('ASTRANS_REMESA_NORM','nunique'),FACTURACION=('V_CLIENTE_NUM','sum'),COSTOS=('V_CONDUCT_NUM','sum'),MARGEN=('MARGEN_CALCULADO','sum')).sort_values(pcol)
fin_mes['RENTABILIDAD_%']=np.where(fin_mes.FACTURACION.ne(0),fin_mes.MARGEN/fin_mes.FACTURACION*100,0)
fin_mes['TICKET_PROMEDIO']=np.where(fin_mes.REMESAS.ne(0),fin_mes.FACTURACION/fin_mes.REMESAS,0)
fin_mes['VAR_FACTURACION_%']=fin_mes.FACTURACION.pct_change()*100

names=['🏢 Resumen ejecutivo','📋 Estado inicial DATA','🔗 Resultado PAT','❌ Cancelaciones','📈 Evolución operativa','🚚 Ejecución ASTRANS','💰 Financiero','🎬 Centros de costo','🚙 Vehículos / rutas','⚠️ Conciliación','📥 Exportar']
tabs=st.tabs(names)
with tabs[0]:
    c1,c2=st.columns(2)
    with c1:st.plotly_chart(bar(op_mes,pcol,'SOLICITUDES','Demanda inicial '+periodicidad.lower()),use_container_width=True)
    with c2:st.plotly_chart(bar(fin_mes,pcol,'FACTURACION','Facturación verificada '+periodicidad.lower(),color='#F58220'),use_container_width=True)
    st.dataframe(op_mes.merge(fin_mes,on=pcol,how='outer').sort_values(pcol),use_container_width=True,hide_index=True)
    st.markdown(f'**Lectura ejecutiva:** {fmt(solicitudes)} solicitudes iniciales; {fmt(final_cancelados)} cancelaciones finales identificadas; {fmt(confirmados)} solicitudes vinculadas a ejecución ASTRANS; {fmt(n_ejecutados)} remesas ejecutadas únicas en el alcance financiero; facturación {cop(importe)} y margen {cop(margen)}. Las cifras operativas y financieras tienen universos diferentes y no deben restarse sin conciliación.')
with tabs[1]:
    d=op.groupby('DATA_ESTADO_SERVICIO',dropna=False).size().reset_index(name='CANTIDAD').sort_values('CANTIDAD',ascending=False)
    st.plotly_chart(bar(d,'DATA_ESTADO_SERVICIO','CANTIDAD','Estados iniciales DATA'),use_container_width=True)
    st.dataframe(d,use_container_width=True,hide_index=True)
with tabs[2]:
    d=op.groupby('ESTADO_FINAL_SOLICITUD',dropna=False).size().reset_index(name='CANTIDAD').sort_values('CANTIDAD',ascending=False)
    st.plotly_chart(bar(d,'ESTADO_FINAL_SOLICITUD','CANTIDAD','Resultado de solicitud tras cruce DATA–PAT–ASTRANS'),use_container_width=True)
    st.dataframe(d,use_container_width=True,hide_index=True)
    st.info('PRESTADO_CON_REMESA: PAT contiene SEV, pero no se confirmó una remesa ejecutada válida en ASTRANS. No equivale a facturación confirmada.')
with tabs[3]:
    d=op_mes[[pcol,'CANCELADOS_INICIALES','CANCELADOS_FINALES','TASA_CANCELACION_FINAL_%']]
    st.plotly_chart(px.bar(d,x=pcol,y=['CANCELADOS_INICIALES','CANCELADOS_FINALES'],barmode='group',title='Cancelaciones DATA vs resultado conciliado'),use_container_width=True)
    st.dataframe(d,use_container_width=True,hide_index=True)
    ca=op[op.ESTADO_FINAL_SOLICITUD.isin(['CANCELADO_CONFIRMADO_PAT','CANCELADO_DATA_SIN_PAT'])]
    st.dataframe(ca.groupby('DATA_CENTRO_ORDEN_COSTO').size().reset_index(name='CANCELADOS').sort_values('CANCELADOS',ascending=False).head(25),hide_index=True,use_container_width=True)
with tabs[4]:
    d=op_mes[[pcol,'SOLICITUDES','GESTIONADOS_INICIALES','CON_REMESA_PAT','EJECUTADOS_CONCILIADOS']]
    st.plotly_chart(px.line(d,x=pcol,y=['SOLICITUDES','GESTIONADOS_INICIALES','CON_REMESA_PAT','EJECUTADOS_CONCILIADOS'],markers=True,title='Embudo operativo por periodo'),use_container_width=True)
    st.dataframe(d,hide_index=True,use_container_width=True)
with tabs[5]:
    d=fin.groupby('RESULTADO_SERVICIO').size().reset_index(name='REGISTROS')
    st.plotly_chart(bar(d,'RESULTADO_SERVICIO','REGISTROS','Estados de ejecución ASTRANS'),use_container_width=True)
    st.plotly_chart(bar(fin_mes,pcol,'REMESAS','Remesas únicas ejecutadas'),use_container_width=True)
    st.caption(f'Registros ASTRANS sin remesa SEV: {len(fin_sin_sev)} · Filas duplicadas por remesa dentro del conjunto válido: {int(con_sev.DUPLICADO_REMESA.sum())}. Se excluyen del agregado verificado para evitar doble conteo; deben revisarse antes de cerrar valores.')
with tabs[6]:
    c1,c2=st.columns(2)
    with c1:st.plotly_chart(bar(fin_mes,pcol,'FACTURACION','Facturación',color='#003B75'),use_container_width=True)
    with c2:st.plotly_chart(bar(fin_mes,pcol,'MARGEN','Margen',color='#008A3D'),use_container_width=True)
    st.dataframe(fin_mes,hide_index=True,use_container_width=True)
    st.metric('Ticket promedio por remesa',cop(ticket))
with tabs[7]:
    opcent=op.groupby([pcol,'DATA_CENTRO_ORDEN_COSTO'],as_index=False).size().rename(columns={'size':'SOLICITUDES'})
    top=op.groupby('DATA_CENTRO_ORDEN_COSTO').size().nlargest(12).index
    d=opcent[opcent.DATA_CENTRO_ORDEN_COSTO.isin(top)]
    st.plotly_chart(px.line(d,x=pcol,y='SOLICITUDES',color='DATA_CENTRO_ORDEN_COSTO',markers=True,title='Demanda inicial por centro de costo'),use_container_width=True)
    st.dataframe(op.groupby('DATA_CENTRO_ORDEN_COSTO').size().reset_index(name='SOLICITUDES').sort_values('SOLICITUDES',ascending=False).head(30),hide_index=True,use_container_width=True)
    fcent=fin_unico[fin_unico.FUENTE_CENTRO_COSTO.ne('SIN_CONCILIAR')]
    st.subheader('Facturación por centro conciliado')
    st.dataframe(fcent.groupby('CENTRO_COSTO_CONCILIADO',as_index=False).agg(REMESAS=('ASTRANS_REMESA_NORM','nunique'),FACTURACION=('V_CLIENTE_NUM','sum'),MARGEN=('MARGEN_CALCULADO','sum')).sort_values('FACTURACION',ascending=False).head(30),hide_index=True,use_container_width=True)
    st.caption(f'{len(fin_unico)-len(fcent)} remesas ejecutadas únicas carecen de centro de costo conciliado. No se asigna facturación a un centro por inferencia.')
with tabs[8]:
    veh='T. VEHICULO' if 'T. VEHICULO' in fin_unico else None
    if veh:
        d=fin_unico.groupby(veh).size().reset_index(name='SERVICIOS').sort_values('SERVICIOS',ascending=False).head(15)
        st.plotly_chart(bar(d,veh,'SERVICIOS','Participación de flota por vehículo'),use_container_width=True)
    if 'ORIGEN' in fin_unico and 'DESTINO' in fin_unico:
        od=fin_unico.groupby(['ORIGEN','DESTINO']).size().reset_index(name='SERVICIOS').sort_values('SERVICIOS',ascending=False).head(20)
        st.dataframe(od,use_container_width=True,hide_index=True)
with tabs[9]:
    if centros_sel:
        revf=rev[rev.get('CENTRO',pd.Series('',index=rev.index)).astype(str).isin(centros_sel)].copy()
    else:revf=rev.copy()
    st.metric('Casos para coordinador',len(revf))
    st.dataframe(revf,use_container_width=True,hide_index=True)
    st.subheader('Cobertura de trazabilidad financiera')
    st.dataframe(fin.groupby('ESTADO_TRAZABILIDAD').size().reset_index(name='FILAS'),hide_index=True,use_container_width=True)
    st.warning('La alerta SEV + Cancelado no elimina el servicio: se cuenta como prestado con inconsistencia y requiere ajuste del estado PAT. No se modifican fuentes originales.')
with tabs[10]:
    hojas={'RESUMEN_OPERATIVO':op_mes,'RESUMEN_FINANCIERO':fin_mes,'SOLICITUDES_FILTRADAS':op,'TRAYECTOS_FILTRADOS':fin,'REMESAS_EJECUTADAS':fin_unico,'REVISION_COORDINADOR':rev}
    st.download_button('📥 Descargar informe ejecutivo conciliado',exportar(hojas),file_name='RCN_INFORME_EJECUTIVO_V9.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')
    st.markdown('**Interpretación:** una caída de solicitudes por centro de costo puede estar relacionada con el cierre de producción, pero no se atribuye automáticamente sin confirmar el cronograma. Cancelación inicial, cancelación final, remesa registrada y ejecución financiera se muestran como indicadores separados.')
