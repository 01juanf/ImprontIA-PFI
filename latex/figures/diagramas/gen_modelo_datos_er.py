"""Genera figures/modelo_datos_er.pdf (Figura del modelo entidad-relación, cap. 15).

Transcripción fiel del diagrama anterior (imagen figures/modelo_datos_er.png, que se conserva), redibujado
el 22/10/2026 con Graphviz para imprimir el texto en negro y con fuente mayor: diez entidades,
mismos atributos, tipos, claves y relaciones (notación pata de gallo: || = uno, o{ = cero o muchos).

Uso (desde esta carpeta; requiere graphviz, pdftoppm, pypdf, Pillow y numpy):
    python3 gen_modelo_datos_er.py
"""
import os, subprocess, tempfile
from pypdf import PdfReader,PdfWriter
from PIL import Image
import numpy as np

def recortar(src,dst,m=3):
    """Recorta la página al contenido dibujado (margen m en pt)."""
    d=tempfile.mkdtemp(); subprocess.run(['pdftoppm','-r','144','-png','-singlefile',src,d+'/p'],check=True)
    a=np.array(Image.open(d+'/p.png').convert('L')); ys,xs=np.where(a<245)
    H,W=a.shape; r=PdfReader(src); p=r.pages[0]; pw=float(p.mediabox.width); ph=float(p.mediabox.height)
    sx=pw/W; sy=ph/H
    x0=xs.min()*sx-m; x1=(xs.max()+1)*sx+m; y0=ph-(ys.max()+1)*sy-m; y1=ph-ys.min()*sy+m
    llx=float(p.mediabox.left); lly=float(p.mediabox.bottom)
    p.mediabox.lower_left=(llx+x0,lly+y0); p.mediabox.upper_right=(llx+x1,lly+y1); p.cropbox=p.mediabox
    w=PdfWriter(); w.add_page(p); w.write(dst); print('cropped to',round(x1-x0),'x',round(y1-y0))

ENT = {
 "USUARIO":[("uuid","id","PK",""),("string","nombre","",""),("string","email","",""),("enum","rol","","")],
 "EVALUACION":[("uuid","id","PK",""),("string","titulo","",""),("string","catedra","",""),("uuid","docente_id","FK",""),("enum","estado","","")],
 "POLITICA_CAPTURA":[("uuid","id","PK",""),("uuid","evaluacion_id","FK",""),("int","version","",""),("json","senales_habilitadas","",""),("text","finalidad","",""),("int","retencion_dias","","")],
 "SESION":[("uuid","id","PK",""),("uuid","evaluacion_id","FK",""),("uuid","estudiante_id","FK",""),("uuid","politica_id","FK",""),("timestamp","inicio","",""),("timestamp","informado_en","",""),("json","contexto","",""),("enum","estado","","")],
 "EVENTO":[("bigint","id","PK",""),("uuid","sesion_id","FK",""),("bigint","secuencia","",""),("enum","tipo","",""),("timestamp","ts_cliente","",""),("timestamp","ts_servidor","",""),("string","item_ref","","nullable"),("json","payload_minimo","","")],
 "METRICA":[("uuid","id","PK",""),("uuid","sesion_id","FK",""),("bigint","evento_desde","FK",""),("bigint","evento_hasta","FK",""),("enum","tipo","",""),("numeric","valor","",""),("string","item_ref","","nullable, denormalizado")],
 "INDICADOR":[("uuid","id","PK",""),("uuid","sesion_id","FK",""),("enum","tipo","",""),("enum","nivel","",""),("enum","estado","",""),("timestamp","generado_en","","")],
 "REVISION":[("uuid","id","PK",""),("uuid","sesion_id","FK",""),("uuid","docente_id","FK",""),("enum","resultado","",""),("text","comentario","",""),("timestamp","fecha","","")],
 "INDICADOR_METRICA":[("uuid","indicador_id","FK",""),("uuid","metrica_id","FK","")],
 "REVISION_INDICADOR":[("uuid","revision_id","FK",""),("uuid","indicador_id","FK","")],
}
REL = [("USUARIO","EVALUACION","es_responsable_de"),("EVALUACION","POLITICA_CAPTURA","versiona"),
 ("EVALUACION","SESION","instancia"),("USUARIO","SESION","rinde_como_estudiante"),("USUARIO","REVISION","firma_como_docente"),
 ("POLITICA_CAPTURA","SESION","snapshot_en"),("SESION","EVENTO","registra"),("SESION","METRICA","deriva"),
 ("SESION","INDICADOR","genera"),("SESION","REVISION","es_revisada_en"),("EVENTO","METRICA","origina"),
 ("METRICA","INDICADOR_METRICA","sustenta"),("INDICADOR","INDICADOR_METRICA","se_sustenta_en"),
 ("INDICADOR","REVISION_INDICADOR","es_atendido_en"),("REVISION","REVISION_INDICADOR","atiende")]
B="#16406D"
out=['digraph ER {','  graph [forcelabels=true, splines=true, overlap=false, sep="+6", esep="+3", fontname="Helvetica", bgcolor="white", pad=0.05];',
     f'  node [shape=plaintext, fontname="Helvetica", fontsize=FS, fontcolor="black"];',
     f'  edge [color="{B}", penwidth=1.1, fontname="Helvetica", fontsize=FSE, fontcolor="black", dir=both, arrowtail=teetee, arrowhead=crowodot, arrowsize=0.9];']
POS={"USUARIO":(0,712),"EVALUACION":(243,599),"POLITICA_CAPTURA":(475,712),
 "SESION":(232,399),"EVENTO":(498,475),"REVISION":(0,162),"INDICADOR":(232,162),"METRICA":(475,183),
 "REVISION_INDICADOR":(0,-10),"INDICADOR_METRICA":(232,-10)}
for n,rows in ENT.items():
    hascom=False
    ncol=3
    h=[f'<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="3" COLOR="{B}">',
       f'<TR><TD COLSPAN="{ncol}" BGCOLOR="#DFE8F2"><B>{n}</B></TD></TR>']
    for i,(t,a,k,c) in enumerate(rows):
        bg="#FFFFFF" if i%2==0 else "#F1F5FA"
        cells=f'<TD ALIGN="LEFT" BGCOLOR="{bg}">{t}</TD><TD ALIGN="LEFT" BGCOLOR="{bg}">{a}{('<BR ALIGN="LEFT"/><I>'+c+'</I><BR ALIGN="LEFT"/>') if c else ''}</TD><TD BGCOLOR="{bg}">{k if k else " "}</TD>'
        if hascom: cells+=f'<TD ALIGN="LEFT" BGCOLOR="{bg}">{c if c else " "}</TD>'
        h.append(f'<TR>{cells}</TR>')
    h.append('</TABLE>')
    x,y=POS[n]
    out.append(f'  {n} [pos="{x},{y}!", label=<{"".join(h)}>];')
CORTAS=set()
for a,b,l in REL:
    out.append(f'  {a} -> {b} [{"xlabel" if (a,b) in CORTAS else "label"}=" {l} "];')
out.append('}')
txt="\n".join(out)+"\n"
txt=txt.replace('FSE','10').replace('FS','11')
base=os.path.dirname(os.path.abspath(__file__))
dot_path=os.path.join(base,'modelo_datos_er.dot'); open(dot_path,'w').write(txt)
tmp=os.path.join(tempfile.mkdtemp(),'er.pdf')
subprocess.run(['neato','-n2','-Tpdf',dot_path,'-o',tmp],check=True)
recortar(tmp, os.path.join(base,'..','modelo_datos_er.pdf'))

