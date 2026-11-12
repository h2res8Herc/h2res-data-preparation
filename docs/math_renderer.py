"""Render documented equations as offline vector SVGs; never imports the model."""
import hashlib
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import math_to_image

D=Path(__file__).resolve().parent


def equation_html(identifier, latex, chapter):
    records=json.loads((D/'inventory/equation_sources.json').read_text(encoding='utf-8'))
    record=next(r for r in records if r['id']==identifier)
    assert record['latex']==latex.strip(), 'Equation source map is stale: '+identifier
    directory=D/'equations'; directory.mkdir(exist_ok=True)
    filename=identifier+'.svg'; target=directory/filename
    fingerprint=hashlib.sha256(latex.encode('utf-8')).hexdigest()
    stamp=directory/(identifier+'.json')
    previous=json.loads(stamp.read_text()) if stamp.exists() else {}
    if not target.exists() or previous.get('latex_sha256')!=fingerprint:
        math_to_image('$'+latex.strip()+'$',target,prop=FontProperties(size=19),
                      dpi=150,format='svg',color='#142d40')
        stamp.write_text(json.dumps(dict(id=identifier,latex_sha256=fingerprint,
                                        svg_sha256=hashlib.sha256(target.read_bytes()).hexdigest()),indent=2),encoding='utf-8')
    source='equations/'+filename
    caption=identifier+' · '+record['source']+':'+str(record['first_line'])+' · '+record['representation']
    return ('<figure class="equation" data-equation-id="'+identifier+'" id="'+chapter+'--equation-'+identifier.lower()+'">'
            '<a href="'+source+'"><img src="'+source+'" alt="'+html.escape(latex,quote=True)+'"></a>'
            '<figcaption>'+html.escape(caption)+'</figcaption></figure>')
