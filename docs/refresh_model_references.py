"""Add checked primary DSM references and preserve supplied integration provenance."""
import json
from pathlib import Path
import re

D=Path(__file__).resolve().parent


def main():
    p=D/'references.json'; refs=json.loads(p.read_text(encoding='utf-8'))
    additions=[
        dict(id='R35',author='Heitkoetter, Wilko and Schyska, Bruno U. and Schmidt, Danielle and Medjroubi, Wided and Vogt, Thomas and Agert, Carsten',year='2020',title='Assessment of the regionalised demand response potential in Germany using an open source tool and dataset',type='article',doi='10.48550/arXiv.2009.05122',url='https://arxiv.org/abs/2009.05122',use='Regional demand-response methods and cost-potential background. German results do not calibrate Croatian residual basic-load DSM or the local 7%/1.5% assumptions.',verification='Primary author preprint landing page, author list and abstract checked 12 November 2026; no numerical transfer or full-text replication claimed.'),
        dict(id='R36',author='Gils, Hans Christian',year='2016',title='Economic potential for future demand response in Germany – Modeling approach and case study',type='article',doi='10.1016/j.apenergy.2015.10.083',url='https://elib.dlr.de/99320/',use='Demand-response modeling and sensitivity background, Applied Energy 162, 401–415. Not a country-specific calibration of local DSM costs.',verification='Primary DLR repository metadata and abstract checked 12 November 2026. Repository lists 2015 publication/deposit metadata; journal volume is conventionally cited as 2016 in the supplied model notes.'),
        dict(id='R37',author='DIETERpy project',year='n.d.',title='Objective Function — DIETERpy documentation',type='online',url='https://diw-evu.gitlab.io/dieter_public/dieterpy/model/equations/eq_objective.html',use='Primary model documentation illustrating annualized DSM enabling/fixed and activation-cost terms. H2RES uses its own moved-energy counting convention.',verification='Primary documentation equations and DSM sections checked 12 November 2026; no assertion that the two models have identical formulations.')]
    for entry in additions:
        matches=[i for i,r in enumerate(refs) if r['id']==entry['id']]
        if matches: refs[matches[0]]=entry
        else: refs.append(entry)
    p.write_text(json.dumps(refs,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    model=Path(json.loads((D/'inventory/documented_version.json').read_text())['model_root'])
    target=D/'model_notes_2026_11_12'
    integration=(model/'reports/unified_integration/README.md').read_text(encoding='utf-8-sig')
    # Relative links in an inherited report refer to its original source tree.
    # Keep those references as paths rather than broken offline hyperlinks.
    integration=re.sub(r'\[([^\]]+)\]\((?!https?://)([^)]+)\)',lambda m:m[1]+' (`'+m[2]+'`, relative to the original integration report)',integration)
    (target/'integration_record.md').write_text('Source: `reports/unified_integration/README.md` in the inspected model. Relative report links below are preserved as source-tree paths. Reported tests were not rerun for this manual.\n\n'+integration,encoding='utf-8')
    p=target/'UNIFIED_MODEL.md'
    p.write_text(p.read_text(encoding='utf-8').replace('../reports/unified_integration/README.md','integration_record.md'),encoding='utf-8')
    for name in ['H2RES_MODEL_MANUAL.md','H2RES_USER_GUIDE.md']:
        p=D/name; text=p.read_text(encoding='utf-8')
        sentence='Demand-response background is provided by [R35](REFERENCES.md#r35), [R36](REFERENCES.md#r36) and [R37](REFERENCES.md#r37); these sources do not validate the local energy-pool percentages or costs.\n\n'
        anchor='## 20. Product based' if name=='H2RES_MODEL_MANUAL.md' else '## 11. New product-industry'
        if sentence not in text: text=text.replace(anchor,sentence+anchor)
        p.write_text(text,encoding='utf-8')
    print('Preserved bibliography and added three checked primary DSM sources.')


if __name__=='__main__': main()
