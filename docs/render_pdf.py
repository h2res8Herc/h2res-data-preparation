"""Print the already-built offline HTML with a temporary isolated Chrome profile."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import uuid
import argparse

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previews-only',action='store_true')
    args=parser.parse_args()
    candidates = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                  Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
    browser = next((p for p in candidates if p.exists()), None)
    if browser is None: raise SystemExit('Chrome/Edge not found. Open the HTML and use Print / save PDF.')
    profile = (ROOT / 'validation' / ('documentation_browser_' + uuid.uuid4().hex[:10])).resolve()
    profile.mkdir(parents=True)
    base = [str(browser), '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
            '--disable-extensions', '--disable-background-networking', '--allow-file-access-from-files',
            '--user-data-dir=' + str(profile)]
    source = (DOCS / 'H2RES_COMPLETE_DOCUMENTATION.html').resolve()
    pdf = (DOCS / 'H2RES_COMPLETE_DOCUMENTATION.pdf').resolve()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    editions=[]
    for stem in ['H2RES_COMPLETE_DOCUMENTATION','H2RES_USER_MANUAL']:
        edition_source=DOCS/(stem+'.html'); edition_pdf=DOCS/(stem+'.pdf')
        if not args.previews_only:
            result = subprocess.run(base + ['--no-pdf-header-footer', '--print-to-pdf=' + str(edition_pdf), edition_source.as_uri()],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, creationflags=flags)
            (ROOT/'validation'/(stem.lower()+'_pdf_render.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            if result.returncode != 0 or not edition_pdf.exists(): raise SystemExit('PDF rendering failed: '+stem)
        payload=edition_pdf.read_bytes()
        editions.append(dict(file=edition_pdf.name,bytes=len(payload),pages=len(re.findall(rb'/Type\s*/Page\b',payload)),
                             sha256=hashlib.sha256(payload).hexdigest(),pdf_header_valid=payload.startswith(b'%PDF-'),has_eof=b'%%EOF' in payload[-1024:]))
        print('Rendered '+stem,flush=True)
    html_text = source.read_text(encoding='utf-8')
    preview_head = re.search(r'<head>.*?</head>', html_text, re.S).group(0)
    preview_chapter = re.search(r'<section class="chapter" id="h2res_model_manual">.*?</section>', html_text, re.S).group(0)
    model_preview_source = profile / 'model_chapter_preview.html'
    model_preview_source.write_text('<!doctype html><html lang="en">' + preview_head +
                                   '<body><main class="content" style="max-width:1200px;margin:28px auto">' +
                                   preview_chapter + '</main></body></html>', encoding='utf-8')
    preview_sources=[('cover',source),('model',model_preview_source)]
    for name,start,end in [('equations','mathematical_formulation--2-objective-discounting-and-capital-service','mathematical_formulation--3-capacity'),
                           ('configuration','main_configuration_guide--4-time-modes-select-one-execution-structure','main_configuration_guide--5-electricity')]:
        block_start=html_text.index('<h2 id="'+start)
        # The equation chapter uses the full section title in the next ID.
        block_end=html_text.index('<h2 ',block_start+1)
        content=html_text[block_start:block_end]
        preview=profile/(name+'_preview.html')
        head=preview_head.replace('</head>','<base href="'+DOCS.as_uri()+'/"></head>')
        preview.write_text('<!doctype html><html lang="en">'+head+'<body><section class="chapter" style="max-width:1200px;margin:24px auto">'+content+'</section></body></html>',encoding='utf-8')
        preview_sources.append((name,preview))
    for name, preview_source in preview_sources:
        screenshot = DOCS / ('preview_' + name + '.png')
        preview_uri=preview_source.as_uri()
        shot = subprocess.run(base + ['--window-size=1400,1000', '--run-all-compositor-stages-before-draw',
                                     '--virtual-time-budget=2000', '--screenshot=' + str(screenshot),
                                     preview_uri],
                              capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,creationflags=flags)
        if shot.returncode != 0: raise SystemExit('Preview rendering failed: '+name)
        from PIL import Image,ImageStat
        with Image.open(screenshot) as im:
            if max(ImageStat.Stat(im.convert('RGB')).stddev)<5: raise SystemExit('Blank preview: '+name)
    payload=pdf.read_bytes()
    page_count=len(re.findall(rb'/Type\s*/Page\b',payload))
    report=dict(pdf=pdf.name,bytes=len(payload),pages=page_count,sha256=hashlib.sha256(payload).hexdigest(),
                pdf_header_valid=payload.startswith(b'%PDF-'),has_eof=b'%%EOF' in payload[-1024:],
                renderer=str(browser),isolated_profile=str(profile),model_executed=False,editions=editions)
    (DOCS/'inventory/pdf_render_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
