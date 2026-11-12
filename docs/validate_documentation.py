"""Validate documentation links, references, inventory and source integrity."""
from __future__ import annotations
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ast
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


class BookParser(HTMLParser):
    def __init__(self): super().__init__(); self.ids=set(); self.duplicates=[]; self.links=[]; self.scripts=[]; self.images=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id'):
            if attrs['id'] in self.ids: self.duplicates.append(attrs['id'])
            self.ids.add(attrs['id'])
        if tag=='a' and attrs.get('href'): self.links.append(attrs['href'])
        if tag=='img' and attrs.get('src'): self.images.append(attrs['src'])
        if tag=='script': self.scripts.append(attrs.get('src','inline'))


def main():
    failures=[]
    manifest=json.loads((DOCS/'inventory/documented_version.json').read_text(encoding='utf-8'))
    for key,digest in manifest['source_hashes'].items():
        kind,relative=key.split('/',1)
        base=Path(manifest['model_root']) if kind=='model' else ROOT
        path=base/relative
        if not path.exists() or sha256(path)!=digest: failures.append('Documented source changed: '+key)
    with (DOCS/'inventory/model_data_files.csv').open(encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            path=Path(manifest['model_root'])/'data'/row['file']
            if sha256(path)!=row['sha256']: failures.append('Model input changed: '+row['file'])
    refs=json.loads((DOCS/'inventory/reference_register.json').read_text(encoding='utf-8'))
    ref_ids={r['id'].lower() for r in refs}
    if len(ref_ids)!=len(refs): failures.append('Duplicate reference identifiers')
    for path in DOCS.glob('*.md'):
        text=path.read_text(encoding='utf-8')
        for label,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',text):
            if urlparse(target).scheme in ('https','http','mailto'): continue
            relative,_,anchor=target.partition('#')
            resolved=(path.parent/unquote(relative)).resolve() if relative else path
            if not resolved.exists(): failures.append(f'{path.name}: missing link {target}')
            if relative=='REFERENCES.md' and anchor and anchor.lower() not in ref_ids: failures.append(f'{path.name}: unknown reference {anchor}')
    html_path=DOCS/'H2RES_COMPLETE_DOCUMENTATION.html'
    parser=BookParser(); parser.feed(html_path.read_text(encoding='utf-8'))
    failures += ['Duplicate HTML anchor: '+value for value in parser.duplicates]
    for target in parser.links:
        if target.startswith('#') and target[1:] not in parser.ids: failures.append('Missing HTML anchor: '+target)
        elif not target.startswith('#') and not urlparse(target).scheme:
            if not (DOCS/unquote(target.split('#')[0])).exists(): failures.append('Missing HTML local target: '+target)
    if parser.scripts: failures.append('Offline edition contains external/script dependencies')
    focused=BookParser(); focused.feed((DOCS/'H2RES_USER_MANUAL.html').read_text(encoding='utf-8'))
    if focused.duplicates: failures.append('Duplicate focused-manual anchors')
    for book in (parser,focused):
        for target in book.links+book.images:
            if target.startswith('#') and target[1:] not in book.ids: failures.append('Missing manual anchor: '+target)
            elif not target.startswith('#') and not urlparse(target).scheme:
                if not (DOCS/unquote(target.split('#')[0])).exists(): failures.append('Missing manual asset: '+target)
        if book.scripts: failures.append('Manual requires script dependencies')
    capture_path=DOCS/'screenshots/model_2026_11_12/capture_manifest.json'
    capture=json.loads(capture_path.read_text(encoding='utf-8'))
    from PIL import Image, ImageStat
    for view in capture['views']:
        source=Path(capture['model_root'])/view['source']
        if view['source_sha256'] and sha256(source)!=view['source_sha256']: failures.append('Screenshot source changed: '+view['source'])
        picture=capture_path.parent/view['image']
        if not picture.exists() or sha256(picture)!=view.get('image_sha256'): failures.append('Screenshot missing or changed: '+view['image']); continue
        with Image.open(picture) as im:
            if im.size!=(1600,1100) or max(ImageStat.Stat(im.convert('RGB')).stddev)<10: failures.append('Invalid/blank screenshot: '+view['image'])
    for path in (DOCS/'model_notes_2026_11_12').glob('*.md'):
        for _,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if not urlparse(target).scheme and not (path.parent/target.split('#')[0]).exists(): failures.append('Missing copied-note link: '+str(path.name)+': '+target)
    screenshots=[src for src in focused.images if src.startswith('screenshots/model_2026_11_12/')]
    if len(screenshots)!=32: failures.append('Focused manual should include all 32 model screenshots')
    equation_records=json.loads((DOCS/'inventory/equation_sources.json').read_text(encoding='utf-8'))
    equation_images=[src for src in focused.images if src.startswith('equations/')]
    if len(equation_images)!=len(equation_records): failures.append('Equation render count differs from source registry')
    for eq in equation_records:
        source=Path(manifest['model_root'])/eq['source']
        if sha256(source)!=eq['source_sha256']: failures.append('Equation source changed: '+eq['id'])
        text=source.read_text(encoding='utf-8-sig').splitlines()
        if eq['source_anchor'] not in text[eq['first_line']-1]: failures.append('Equation source line mismatch: '+eq['id'])
        svg=DOCS/'equations'/(eq['id']+'.svg')
        stamp=json.loads(svg.with_suffix('.json').read_text(encoding='utf-8'))
        if sha256(svg)!=stamp['svg_sha256']: failures.append('Equation graphic changed: '+eq['id'])
        if hashlib.sha256(eq['latex'].encode('utf-8')).hexdigest()!=stamp['latex_sha256']: failures.append('Equation graphic is stale: '+eq['id'])
        root=ET.parse(svg).getroot()
        if not root.tag.endswith('svg') or not root.findall('.//{http://www.w3.org/2000/svg}path'): failures.append('Invalid equation SVG: '+eq['id'])
    from option_explanations import mappings
    with (DOCS/'inventory/model_configuration.csv').open(encoding='utf-8-sig') as stream: config=list(csv.DictReader(stream))
    missing={ (r['file'],r['name']) for r in config }-mappings().keys()
    if missing: failures.append('Missing option explanations: '+repr(sorted(missing)))
    settings={r['name'] for r in config}
    guide=(DOCS/'MAIN_CONFIGURATION_GUIDE.md').read_text(encoding='utf-8')
    snippets=re.findall(r'```python\n(.*?)\n```',guide,re.S)
    for number,snippet in enumerate(snippets,1):
        tree=ast.parse(snippet)
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign):
                for target in node.targets:
                    if isinstance(target,ast.Name) and target.id not in settings: failures.append('Unknown option in recipe '+str(number)+': '+target.id)
    bib=(DOCS/'references.bib').read_text(encoding='utf-8')
    for r in refs:
        if '{'+r['id']+',' not in bib: failures.append('Missing BibTeX reference: '+r['id'])
    if manifest['variable_call_sites']<150: failures.append('Variable inventory may be missing wrapped declarations')
    report=dict(passed=not failures,errors=failures,model_and_preparation_source_hashes_verified=len(manifest['source_hashes']),
                model_input_hashes_verified=manifest['model_data_files'],reference_entries=len(refs),html_anchors=len(parser.ids),
                constraints_indexed=manifest['constraint_call_sites'],variables_indexed=manifest['variable_call_sites'],
                model_screenshots_verified=len(capture['views']),focused_manual_images=len(focused.images),
                equations_verified=len(equation_records),unique_settings_explained=len({(r['file'],r['name']) for r in config}),
                configuration_recipe_snippets_checked=len(snippets),
                model_executed=False,model_files_modified=False)
    (DOCS/'inventory/documentation_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2)); return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
