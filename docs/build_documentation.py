"""Build a self-contained HTML documentation book and reference exports.

Uses the standard library and the existing local inventories. No model execution.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import unquote

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
DATE = "2026-11-12"
CHAPTERS = ["README.md", "PORTABLE_USER_GUIDE.md", "DATA_PREPARATION_MANUAL.md", "H2RES_USER_GUIDE.md", "MAIN_CONFIGURATION_GUIDE.md", "MATHEMATICAL_FORMULATION.md", "H2RES_MODEL_MANUAL.md", "MODEL_OPTION_REFERENCE.md", "DATA_REFERENCE.md",
            "ASSUMPTIONS_AND_LIMITATIONS.md", "REFERENCES.md", "CLI_REFERENCE.md", "CODE_REFERENCE.md"]


def source_references():
    refs = json.loads((DOCS / "references.json").read_text(encoding="utf-8"))
    inherited_files = [
        ROOT / "industry/handoff/model/analysis/industry_fuel_compatibility_2026_10_31/references.csv",
        ROOT / "industry/handoff/model/analysis/category_electricity_review_2026_10_31/paper/references.csv",
        ROOT / "industry/handoff/preparation_history/analysis/paper_industry_limits_2026_10_31/references.csv",
    ]
    known = {r["url"] for r in refs}
    for path in inherited_files:
        if not path.exists(): continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                url = row.get("URL", "").strip()
                if not url or url in known: continue
                known.add(url)
                year = row.get("Year", "").removesuffix(".0") or "n.d."
                refs.append(dict(id=f"H{sum(r['id'].startswith('H') for r in refs)+1:02d}",
                                 author=row.get("Author", "Unknown supplied author"), year=year, title=row.get("Title", "Supplied reference"),
                                 type="inherited reference", url=url, doi=row.get("DOI", ""),
                                 use="Identifiable reference retained from the supplied industry methodology/bibliography. Some URLs duplicate a curated work using a different endpoint.",
                                 verification="Bibliographic metadata retained from supplied handoff; not every document or numeric transfer independently re-read in this documentation session.",
                                 inherited_from=str(path.relative_to(ROOT)), inherited_key=row.get("BibTeX_key", "")))
    opex_file = Path(json.loads((DOCS / "inventory/documented_version.json").read_text())["model_root"]) / "data/literature_fixed_opex.csv"
    grouped = {}
    if opex_file.exists():
        with opex_file.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                key = row["source_id"], row["source_url"]
                group = grouped.setdefault(key, dict(source_id=key[0], source_url=key[1], rows=0,
                                                     example_technology=row["technology"], example_workbook=row["workbook"],
                                                     example_sheet=row["source_sheets"], example_cells=row["source_cells"],
                                                     example_price_years=row["source_price_years"]))
                group["rows"] += 1
    with (DOCS / "inventory/fixed_opex_sources.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["source_id", "source_url", "rows", "example_technology", "example_workbook", "example_sheet", "example_cells", "example_price_years"]
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(grouped.values())
    for i, ((source_id, url), row) in enumerate(sorted(grouped.items()), 1):
        refs.append(dict(id=f"T{i:02d}", author="Danish Energy Agency", year="n.d.",
                         title=f"Technology-data workbook identified as {source_id} in the supplied fixed-OPEX source table",
                         type="technology workbook", url=url, use=f"Source endpoint retained for {row['rows']} technology/year/workbook rate records; see fixed_opex_sources.csv for an example sheet/cell trace.",
                         verification="Source URL and extraction provenance read from the live model CSV. Full downloaded catalogue and every numeric conversion were not independently re-audited here."))
    return refs


def build_references():
    refs = source_references()
    lines = ["# References and source register", "", f"Documentation/source check date: **{DATE}**.", "",
             "R entries are the curated scientific/data/software references. H entries preserve additional identifiable sources from the supplied industry handoff. T entries preserve the live fixed-OPEX workbook sources. Multiple URLs can describe the same work; entries are not a count of independent validation studies.", "",
             "The verification note records whether a primary page/PDF was actually inspected or metadata were retained from supplied files. No missing source, price year or parameter calibration has been invented. A reference to a technology catalogue is not proof that every local default was transferred correctly.", "",
             "## Citation practice", "", "For a study, cite the H2RES optimization formulation (R02), the actual dataset releases, and the technology sources used. Also identify the local model hash, preparation version and scenario assumptions. Historical H2RES simulation and later optimization versions must not be treated as the same code.", "",
             "Record download/request dates and local hashes for mutable URLs, mirrored archives and manually prepared statistics extracts. The source's licence and the web-service usage terms are separate matters; check both before redistribution. OSM attribution follows its provider's licence terms. This register documents source conditions, not a legal opinion.", "",
             "## Curated references", ""]
    last = "R"
    for r in refs:
        group = r["id"][0]
        if group != last:
            lines += ["## " + ("Additional industry handoff references" if group == "H" else "Fixed-OPEX source workbooks"), ""]
            last = group
        lines += [f"<a id=\"{r['id'].lower()}\"></a>", f"### {r['id']} — {r['title']}", "",
                  f"{r['author']}. ({r['year']}). *{r['title']}*. {r['type']}.", "",
                  f"[Primary/preserved source]({r['url']})." + (f" DOI: `{r['doi']}`." if r.get("doi") else ""), "",
                  "**Use:** " + r["use"], "", "**Verification:** " + r["verification"], ""]
        if r.get("verified_url"):
            lines += [f"[Additional checked page]({r['verified_url']}).", ""]
        if r.get("license_note"): lines += ["**Source conditions:** " + r["license_note"], ""]
        if r.get("inherited_from"): lines += [f"Supplied bibliography: `{r['inherited_from']}`, key `{r['inherited_key']}`.", ""]
    lines += ["## Provenance appendices", "",
              "- [URLs extracted from executable source constants](inventory/source_urls_from_code.csv): includes APIs, XML namespaces and plotting resources; not every URL is a dataset/reference.",
              "- [Workbook source/reference URL occurrences](inventory/workbook_reference_urls.csv): exact workbook/sheet/cell context.",
              "- [Fixed-OPEX source groups](inventory/fixed_opex_sources.csv): retained source endpoints and example extraction cells.",
              "- [Documented file hashes](inventory/documented_version.json) and [input hashes](inventory/model_data_files.csv).", "",
              "## Unresolved provenance", "",
              "Generic technology defaults, some future demand/build/policy inputs, bundled profile/national-table assumptions and source price-year gaps remain inherited assumptions unless their own metadata establish a specific primary source. The manuals identify these rather than assigning a misleading scientific citation. Complete parameter-level re-auditing would require the original extraction workbooks, editions, page/table/cell references and conversion calculations.", ""]
    (DOCS / "REFERENCES.md").write_text("\n".join(lines), encoding="utf-8")
    (DOCS / "inventory/reference_register.json").write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    with (DOCS / "inventory/reference_register.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["id", "author", "year", "title", "type", "doi", "url", "use", "verification"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(refs)
    bib = []
    for r in refs:
        kind = "article" if r["type"] == "article" else "misc"
        fields = dict(author=r["author"], title="{" + r["title"] + "}", year=r["year"], url=r["url"], urldate=DATE,
                      note=r["use"] + " Verification: " + r["verification"])
        if r.get("doi"): fields["doi"] = r["doi"]
        def escape(value): return value.replace("%", "\\%").replace("&", "\\&").replace("_", "\\_")
        bib.append("@" + kind + "{" + r["id"] + ",\n" + ",\n".join("  " + k + " = {" + escape(v) + "}" for k,v in fields.items()) + "\n}\n")
    (DOCS / "references.bib").write_text("\n".join(bib), encoding="utf-8")
    return refs


def build_cli_reference():
    with (DOCS / "inventory/preparation_cli_options.csv").open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    lines = ["# Preparation command-line reference", "", "Generated from the actual `add_argument` call sites. Expressions such as `SCRIPT_DIR / ...` show the source default; they are not literal shell arguments. The authoritative fully resolved help is the script's `--help` output. These commands prepare data rather than execute H2RES.", ""]
    for filename in dict.fromkeys(r["file"] for r in rows):
        lines += ["## " + filename, "", "| Option | Default | Choices / action | Help |", "|---|---|---|---|"]
        for r in rows:
            if r["file"] != filename: continue
            clean = lambda x: x.replace("|", "&#124;").replace("\n", " ")
            lines.append(f"| `{clean(r['options'])}` | `{clean(r['default'])}` | `{clean(r['choices'] or r['action'])}` | {clean(r['help'])} |")
        lines += [""]
    (DOCS / "CLI_REFERENCE.md").write_text("\n".join(lines), encoding="utf-8")


def slug(text):
    text = re.sub(r"<[^>]+>|[`*]", "", text).strip().lower()
    return re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE).strip("-")


def inline(text, chapter):
    escaped = html.escape(text, quote=False)
    tokens = []
    def code(match):
        tokens.append("<code>" + match.group(1) + "</code>")
        return "\x00" + str(len(tokens)-1) + "\x00"
    escaped = re.sub(r"`([^`]+)`", code, escaped)
    def link(match):
        label, url = match.group(1), html.unescape(match.group(2))
        path, sep, anchor = url.partition("#")
        if path in CHAPTERS:
            url = "#" + Path(path).stem.lower() + ("--" + anchor if sep else "")
        elif url.startswith("#"):
            url = "#" + chapter + "--" + url[1:]
        return '<a href="' + html.escape(url, quote=True) + '">' + label + '</a>'
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return re.sub("\x00([0-9]+)\x00", lambda m: tokens[int(m.group(1))], escaped)


def render_markdown(payload, chapter):
    lines = payload.splitlines(); out = []; toc = []; i = 0
    used_ids = set()
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        picture = re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
        if picture:
            caption, source = picture.groups()
            out.append('<figure><a href="'+html.escape(source,quote=True)+'"><img src="'+html.escape(source,quote=True)+'" alt="'+html.escape(caption,quote=True)+'"></a><figcaption>'+html.escape(caption)+'</figcaption></figure>')
            i += 1; continue
        if line.startswith("```"):
            language = line[3:].strip(); code = []; i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            if language.startswith('equation '):
                from math_renderer import equation_html
                out.append(equation_html(language.split()[1], '\n'.join(code), chapter))
                i += 1; continue
            out.append('<pre><code class="language-' + html.escape(language) + '">' + html.escape("\n".join(code)) + '</code></pre>'); i += 1; continue
        anchor = re.fullmatch(r'<a id="([^"]+)"></a>', line.strip())
        if anchor:
            out.append('<span id="' + chapter + '--' + anchor.group(1) + '"></span>'); i += 1; continue
        heading = re.match(r"^(#{1,6}) (.+)$", line)
        if heading:
            level, label = len(heading.group(1)), heading.group(2)
            sid = chapter + "--" + slug(label); original = sid; n = 1
            while sid in used_ids: n += 1; sid = original + "-" + str(n)
            used_ids.add(sid)
            out.append(f'<h{level} id="{sid}">' + inline(label, chapter) + f'</h{level}>')
            if level <= 2: toc.append((level, sid, label))
            i += 1; continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|\-]+\|$", lines[i+1]):
            rows = []; header = line; i += 2
            while i < len(lines) and lines[i].startswith("|"): rows.append(lines[i]); i += 1
            cells = lambda value, tag: "".join("<"+tag+">"+inline(v.strip(), chapter)+"</"+tag+">" for v in value.strip().strip("|").split("|"))
            out.append('<div class="table-wrap"><table><thead><tr>'+cells(header,"th")+'</tr></thead><tbody>'+
                       "".join("<tr>"+cells(r,"td")+"</tr>" for r in rows)+"</tbody></table></div>"); continue
        bullet = re.match(r"^(?:[-*] |\d+\. )(.+)$", line)
        if bullet:
            ordered = bool(re.match(r"^\d+\.",line)); tag = "ol" if ordered else "ul"; items = []
            while i < len(lines) and re.match(r"^(?:[-*] |\d+\. )", lines[i]):
                items.append(re.sub(r"^(?:[-*] |\d+\. )", "", lines[i])); i += 1
            out.append('<'+tag+'>'+"".join("<li>"+inline(item,chapter)+"</li>" for item in items)+'</'+tag+'>'); continue
        paragraph = [line]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|```|\||[-*] |\d+\. |<a id=)", lines[i]):
            paragraph.append(lines[i]); i += 1
        out.append('<p>'+inline(" ".join(paragraph),chapter)+'</p>')
    return "\n".join(out), toc


CSS = """
:root{--ink:#162b3a;--blue:#17658a;--muted:#526879;--line:#d5e0e6;--paper:#fff}
*{box-sizing:border-box}body{margin:0;background:#edf2f5;color:var(--ink);font:16px/1.65 'Segoe UI',Arial,sans-serif;overflow-wrap:anywhere}
a{color:var(--blue)}.cover{background:#14384c;color:white;padding:64px max(6vw,28px)}.cover p{max-width:800px;color:#d8e8f1}.cover h1{font-size:42px;line-height:1.16;max-width:1000px;margin:12px 0 22px}.eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:12px}
.toolbar{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;padding:12px 5vw;z-index:2;display:flex;align-items:center;gap:16px}.toolbar button{background:var(--blue);color:#fff;border:0;border-radius:4px;padding:9px 14px;font:inherit;cursor:pointer}.toolbar span{font-size:13px;color:var(--muted)}
.layout{display:grid;grid-template-columns:270px minmax(0,1fr);max-width:1480px;margin:auto;gap:32px;padding:32px}.toc{font-size:13px;align-self:start;position:sticky;top:82px;max-height:calc(100vh - 100px);overflow:auto;padding:16px;background:white;border:1px solid var(--line)}.toc a{display:block;text-decoration:none;margin:7px 0}.toc .sub{padding-left:12px;color:var(--muted);font-size:12px}.content{min-width:0}.chapter{background:var(--paper);padding:42px 46px;margin-bottom:28px;border:1px solid var(--line);border-radius:5px;scroll-margin-top:80px}
h1{font-size:30px;line-height:1.25}h2{font-size:23px;border-top:1px solid var(--line);padding-top:20px;margin-top:32px;scroll-margin-top:85px}h3{font-size:18px;scroll-margin-top:85px}p{margin:12px 0}code{font:0.9em Consolas,monospace;background:#edf2f5;padding:1px 4px;border-radius:3px;overflow-wrap:anywhere}pre{font:12px/1.5 Consolas,monospace;background:#eef4f7;padding:16px;border-left:3px solid var(--blue);white-space:pre-wrap;overflow-wrap:anywhere}pre code{padding:0;background:none}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0;line-height:1.4}th,td{border:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e8f0f5}tr:nth-child(even){background:#f8fafb}footer{max-width:1100px;margin:20px auto 50px;color:var(--muted);font-size:12px;padding:0 32px}
@media(max-width:900px){.layout{display:block;padding:12px}.toc{position:static;max-height:300px}.chapter{padding:24px}.cover h1{font-size:31px}}
@media print{@page{size:A4;margin:17mm 15mm 18mm}body{background:white;font:10pt/1.48 'Segoe UI',Arial,sans-serif}.toolbar,.toc{display:none}.cover{background:white;color:#162b3a;padding:30mm 0 35mm;break-after:page}.cover p{color:#526879}.cover h1{font-size:31pt}.layout{display:block;padding:0;margin:0;max-width:none}.chapter{padding:0;border:0;border-radius:0;margin:0;break-before:page}.chapter h1{font-size:22pt}h2{font-size:15pt;break-after:avoid}h3{font-size:12pt;break-after:avoid}table{font-size:8pt;table-layout:fixed}td,th{padding:5px 6px}thead{display:table-header-group}tr{break-inside:avoid}pre{font-size:8pt;break-inside:avoid}.table-wrap{overflow:visible}a{text-decoration:none;color:#154964}footer{display:none}p,li{orphans:3;widows:3}}
"""
CSS += "\nfigure{margin:22px 0;break-inside:avoid}figure img{display:block;width:100%;height:auto;border:1px solid #c8d5de}figcaption{color:#526879;font-size:12px;margin-top:7px} @media print{figure{break-inside:avoid}figure img{max-height:210mm;object-fit:contain}}\n"
CSS += "\n.equation{background:#f3f7fa;border-left:3px solid #17658a;padding:18px;overflow:auto}.equation img{width:auto;max-width:100%;height:auto;border:0;margin:auto}.equation figcaption{font-size:11px;line-height:1.45;overflow-wrap:anywhere}.equation a{display:block} @media print{.equation{padding:10px;overflow:visible}.equation img{max-height:48mm}.equation figcaption{font-size:7pt}}\n"


def main():
    refs = build_references(); build_cli_reference()
    sections, toc = [], []
    for name in CHAPTERS:
        chapter = Path(name).stem.lower(); payload = (DOCS / name).read_text(encoding="utf-8")
        rendered, headings = render_markdown(payload, chapter)
        sections.append(f'<section class="chapter" id="{chapter}">{rendered}</section>')
        toc.extend(headings)
    sidebar = "".join('<a class="'+('sub' if level == 2 else '')+'" href="#'+sid+'">'+html.escape(label)+'</a>' for level,sid,label in toc)
    page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>H2RES — Data Preparation and Model Documentation</title><style>'+CSS+'</style></head><body>'
    page += '<header class="cover"><div class="eyebrow">Technical and user documentation · 12 November 2026</div><h1>Energy Data Preparation<br>and the H2RES Model</h1><p>A version-specific reference covering public data sources, preparation methods, model equations, input contracts, scenario assumptions, operational workflows, numerical quality and references.</p><p>Documented model: H2RES_12.11.2026 · Separate preparation and optimization workflows · Source hashes and machine-readable inventories included</p></header>'
    page += '<div class="toolbar"><button onclick="window.print()">Print / save PDF</button><span>Offline HTML edition. Use Ctrl+F to search. Code/configuration appendices describe static call sites.</span></div><div class="layout"><nav class="toc"><strong>Contents</strong>'+sidebar+'</nav><main class="content">'+"\n".join(sections)+'</main></div><footer>Prepared from the specified local source/input snapshot. Reference limitations and inherited assumptions are stated explicitly. No optimization was executed to generate these documents.</footer></body></html>'
    output = DOCS / 'H2RES_COMPLETE_DOCUMENTATION.html'; output.write_text(page, encoding='utf-8')
    # A focused edition for the model user: code/configuration appendices remain
    # linked as separate files rather than silently linking to absent anchors.
    selected = ['H2RES_USER_GUIDE.md', 'MAIN_CONFIGURATION_GUIDE.md', 'MATHEMATICAL_FORMULATION.md',
                'H2RES_MODEL_MANUAL.md', 'MODEL_OPTION_REFERENCE.md', 'DATA_REFERENCE.md',
                'ASSUMPTIONS_AND_LIMITATIONS.md', 'REFERENCES.md']
    selected_ids = {Path(name).stem.lower() for name in selected}
    focused = '\n'.join(section for name,section in zip(CHAPTERS,sections) if name in selected)
    for omitted in set(CHAPTERS)-set(selected):
        prefix = Path(omitted).stem.lower()
        focused = re.sub(r'href="#'+re.escape(prefix)+r'(?:--([^"]+))?"',
                         lambda m: 'href="'+omitted+('#'+m.group(1) if m.group(1) else '')+'"', focused)
    nav = ''.join('<a class="'+('sub' if level==2 else '')+'" href="#'+sid+'">'+html.escape(label)+'</a>'
                  for level,sid,label in toc if sid.split('--')[0] in selected_ids)
    focused_page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>H2RES User Manual — 12 November 2026</title><style>'+CSS+'</style></head><body>'
    focused_page += '<header class="cover"><div class="eyebrow">Script-based model user manual · 12 November 2026</div><h1>H2RES User Manual</h1><p>For H2RES_12.11.2026: main.py, policies, native data files, workbook variations, electricity DSM and product based industry.</p><p>62 source-linked equations · 378 unique settings explained · Complete workflow and dependency guide · 32 illustrated source/data views · Reference bibliography · Desktop GUI excluded</p></header>'
    focused_page += '<div class="toolbar"><button onclick="window.print()">Print / save PDF</button><span>Offline model manual. Click an image to open it at full resolution.</span></div><div class="layout"><nav class="toc"><strong>Contents</strong>'+nav+'</nav><main class="content">'+focused+'</main></div><footer>No model optimization was executed to prepare this manual.</footer></body></html>'
    (DOCS/'H2RES_USER_MANUAL.html').write_text(focused_page,encoding='utf-8')
    text_files = {name: (DOCS/name).read_text(encoding='utf-8') for name in CHAPTERS}
    report = dict(date=DATE, chapters=CHAPTERS, reference_entries=len(refs),
                  narrative_words=sum(len(re.findall(r"\b\w+\b", payload)) for name,payload in text_files.items() if name not in ('CODE_REFERENCE.md','CLI_REFERENCE.md')),
                  html_bytes=output.stat().st_size, html_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  generated_utc=datetime.now(timezone.utc).isoformat())
    (DOCS/'inventory/documentation_build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
