"""Capture read-only documentation views of real model source and input files.

These are explicitly labelled browser documentation views, not an IDE or Excel.
Never imports the model, evaluates formulas, saves a workbook or starts a solve.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
from openpyxl import load_workbook

DOCS = Path(__file__).resolve().parent
OUT = DOCS / "screenshots/model_2026_11_12"
CSS = """
*{box-sizing:border-box}body{margin:0;background:#edf1f5;color:#142d40;font:16px 'Segoe UI',Arial}
header{background:#153d54;color:white;padding:22px 30px}header small{color:#b9d7e8;text-transform:uppercase;letter-spacing:1px}
h1{margin:8px 0;font-size:26px}header p{margin:6px 0;color:#d9e8ef;font-size:14px}.body{margin:22px 30px;background:white;border:1px solid #c8d5de;border-radius:6px;padding:20px}
.badge{display:inline-block;background:#dceef5;color:#174969;font-size:13px;padding:6px 10px;margin:0 8px 15px 0;border-radius:4px}
table{border-collapse:collapse;width:100%;font-size:14px;table-layout:fixed}th,td{border:1px solid #d4dfe7;padding:9px;text-align:left;overflow-wrap:anywhere;vertical-align:top}th{background:#e5eff6}tr:nth-child(even){background:#f5f8fa}
pre{font:16px/1.62 Consolas,monospace;margin:0;white-space:pre-wrap;overflow-wrap:anywhere}code .num{display:inline-block;width:48px;color:#8697a3;user-select:none}code .comment{color:#537850}.code{background:#f8fafc}
footer{margin:16px 30px;color:#526d80;font-size:13px}.tabs{font-size:13px;line-height:2.1;margin-top:16px;color:#35617a}.active{background:#d9ebf7;font-weight:bold;padding:3px 6px;border-bottom:3px solid #166996}
.directory table{font-size:13px}.directory td,.directory th{padding:6px}
"""


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def table(rows):
    width=max(map(len,rows),default=1)
    padded=[list(r)+['']*(width-len(r)) for r in rows]
    return '<table>'+''.join('<tr>'+''.join('<'+('th' if i==0 else 'td')+'>'+html.escape(str(v) if v is not None else '')+'</'+('th' if i==0 else 'td')+'>' for v in row)+'</tr>' for i,row in enumerate(padded))+'</table>'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-root',type=Path,default=Path(r'D:\POSAO\H2RES_12.11.2026'))
    p.add_argument('--render',action='store_true')
    p.add_argument('--only',nargs='*',help='Re-render only these view IDs; retain hashes of existing captures.')
    a=p.parse_args(); model=a.model_root.resolve(); OUT.mkdir(parents=True,exist_ok=True)
    views=[]
    def add(name,relative,title,body,detail):
        source=model/relative
        page=OUT/(name+'.html')
        page.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>'+html.escape(title)+'</title><style>'+CSS+'</style></head><body><header><small>H2RES 12 November 2026 · read-only documentation view</small><h1>'+html.escape(title)+'</h1><p>'+html.escape(relative)+'</p><p>Actual local file contents · source excerpt / table preview · no model execution</p></header><div class="body">'+body+'</div><footer>'+html.escape(detail)+'<br>Browser documentation view; not an IDE, Excel or the desktop model GUI. Original files are unchanged.</footer></body></html>',encoding='utf-8')
        views.append(dict(id=name,title=title,source=relative,source_sha256=sha(source) if source.is_file() else None,detail=detail,html=page.name,image=name+'.png'))
    code_views=[
        ('01_main','main.py',1,24,'Start here: scenario, policy loading and planning switches'),
        ('02_industry_switches','main.py',80,25,'Select legacy, category, complex or product industry'),
        ('03_file_selection','main.py',316,27,'How the model selects its input workbooks'),
        ('04_model_policy','policy/model_policy.py',1,26,'Physical and transition assumptions'),
        ('05_runtime_policy','policy/runtime_policy.py',1,23,'DSM budgets and numerical settings'),
        ('06_transport_policy','policy/transport_pathways.py',1,24,'Transport conversion policy'),
        ('07_reader','scripts/read_process_data.py',1,23,'The input reader: sets, keys and tables'),
        ('08_builder','scripts/Build_model_dual_industry_categories_named_debug.py',40,24,'Constraint construction and accounting helpers'),
        ('09_cost_solver','scripts/CAPEX_OPEX_Gurobi_settings_dual_industry_categories1.py',1,24,'Costs, objective and solver'),
        ('10_dsm','scripts/electricity_dsm.py',1,22,'Electricity demand shifting implementation'),
        ('11_simple_industry','scripts/simple_industry_inputs.py',1,23,'Product based industry input validation')]
    for name,relative,start,count,title in code_views:
        lines=(model/relative).read_text(encoding='utf-8-sig').splitlines()
        body='<div class="badge">'+f'Lines {start}–{min(start+count-1,len(lines))}'+'</div><pre><code>'
        for i,line in enumerate(lines[start-1:start+count-1],start):
            body+='<span class="num">'+str(i)+'</span><span'+(' class="comment"' if line.lstrip().startswith('#') else '')+'>'+html.escape(line)+'</span>\n'
        add(name,relative,title,body+'</code></pre>',f'Source excerpt, lines {start}–{start+count-1}. Read the surrounding implementation before editing.')
    for name,relative,title in [('12_folder','.','Model project structure'),('13_data_folder','data','The native H2RES data folder')]:
        folder=model/relative
        rows=[['Name','Kind','Size / contents']]
        items=sorted(folder.iterdir(),key=lambda x:(x.is_file(),x.name.lower()))
        if relative=='.':
            keep={'main.py','policy','scripts','data','docs','reports','tools','README.md','requirements_local_reference.txt'}
            items=[x for x in items if x.name in keep]
        for item in items:
            if item.name.startswith('~$'): continue
            rows.append([item.name,'Folder' if item.is_dir() else item.suffix.lstrip('.'),str(sum(x.is_file() for x in item.iterdir()))+' immediate files' if item.is_dir() else f'{item.stat().st_size:,} bytes'])
        # Two-column directory preview keeps all actual filenames legible.
        body=table(rows) if len(rows)<22 else '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">'+table(rows[:1]+rows[1:24])+table(rows[:1]+rows[24:])+'</div>'
        add(name,relative,title,'<div class="directory">'+body+'</div>','Read-only directory listing. No file was created inside this model folder.')
    with (model/'data/generators.csv').open(encoding='utf-8-sig',newline='') as f:
        records=list(csv.reader(f))
    columns=['unit_name','cap_mw','fuel_type','technology','System','Zone']
    indexes=[records[0].index(c) for c in columns]
    rows=[columns]+[[row[i] if i<len(row) else '' for i in indexes] for row in records[1:13]]
    add('14_generators','data/generators.csv','Generators: asset names, power and geography',table(rows),f'First 12 asset records; {len(records)-1} source records. Selected columns; all other columns remain in the CSV.')
    workbooks=[
        ('15_regular','flex_tech.xlsx','simple_industry'),
        ('16_categories','flex_tech_categories.xlsx','Industry_data'),
        ('17_complex','flex_tech_complex_industry.xlsx','Industry_data'),
        ('18_efuel','flex_tech_efuel.xlsx','efuel'),
        ('19_efuel_categories','flex_tech_efuel_categories.xlsx','Industry_data'),
        ('20_efuel_complex','flex_tech_efuel_complex_industry.xlsx','Industry_data'),
        ('21_technical','variants/technical_2050/flex_tech_efuel_categories.xlsx','Industry_data'),
        ('22_active_zones','flex_tech_efuel_categories.xlsx','active_zones'),
        ('23_investment_limits','flex_tech_efuel_categories.xlsx','cap_inv_lim'),
        ('24_technology_costs','flex_tech_efuel_categories.xlsx','tech_cost_years'),
        ('25_policy_setup','policy_efuel.xlsx','setup'),
        ('26_policy_co2','policy_efuel.xlsx','CO2'),
        ('27_policy_rps','policy.xlsx','RPS'),
        ('28_fuel_prices','policy_fuels.xlsx',None),
        ('29_process_data','industry_complex_efuel.xlsx','Process_data'),
        ('30_products','simple_industry.xlsx','plants'),
        ('31_markets','simple_industry.xlsx','markets'),
        ('32_outside_suppliers','simple_industry.xlsx','import_suppliers')]
    for name,filename,sheetname in workbooks:
        path=model/'data'/filename
        book=load_workbook(path,read_only=True,data_only=False)
        sheet=book[sheetname] if sheetname else book.worksheets[0]
        rows=list(sheet.iter_rows(min_row=1,max_row=min(sheet.max_row or 13,13),max_col=min(sheet.max_column or 8,8),values_only=True))
        body='<span class="badge">Sheet: '+html.escape(sheet.title)+'</span><span class="badge">Formula view · first rows / columns</span>'+table(rows)
        body+='<div class="tabs">'+ ' · '.join('<span class="active">'+html.escape(n)+'</span>' if n==sheet.title else html.escape(n) for n in book.sheetnames[:24])+'</div>'
        add(name,'data/'+filename,filename+' — '+sheet.title,body,'Actual worksheet cells; formulas are shown as stored and are not recalculated. Preview limited to the first 8 columns / 13 rows. Full sheet inventory accompanies the manual.')
        book.close()
    if a.render:
        browser=next(p for p in [Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')] if p.exists())
        with tempfile.TemporaryDirectory(prefix='h2res_manual_browser_') as profile:
            for view in views:
                output=OUT/view['image']
                if a.only and view['id'] not in a.only:
                    if output.exists(): view['image_sha256']=sha(output)
                    continue
                command=[str(browser),'--headless=new','--disable-gpu','--no-first-run','--disable-extensions','--disable-background-networking','--user-data-dir='+profile,'--hide-scrollbars','--window-size=1600,1100','--run-all-compositor-stages-before-draw','--screenshot='+str(output),(OUT/view['html']).as_uri()]
                result=subprocess.run(command,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if result.returncode or not output.is_file(): raise RuntimeError('Screenshot failed: '+view['id'])
                view['image_sha256']=sha(output)
                print('Captured '+view['id'],flush=True)
    manifest=dict(model_root=str(model),date='2026-11-12',method='Headless Chromium screenshots of explicitly labelled read-only documentation views of actual local files.',model_executed=False,desktop_gui_included=False,views=views)
    (OUT/'capture_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(views=len(views),rendered=a.render),indent=2))


if __name__=='__main__': main()
