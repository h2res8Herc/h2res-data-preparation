"""Package the documentation for sharing, without source datasets or browser profiles."""
from pathlib import Path
import hashlib
import json
import zipfile
from urllib.parse import unquote, urlparse
from validate_documentation import BookParser

DOCS = Path(__file__).resolve().parent
ARCHIVE = DOCS / 'H2RES_DOCUMENTATION_PACKAGE.zip'
REPORT = DOCS / 'inventory/package_validation.json'


def main():
    allowed = {'.md', '.html', '.pdf', '.bib', '.json', '.csv', '.py', '.png', '.svg'}
    files = sorted(p for p in DOCS.rglob('*') if p.is_file() and p.suffix in allowed
                   and '__pycache__' not in p.parts and p != REPORT
                   and p.name != 'manual_publication.json')
    file_hashes = {p.relative_to(DOCS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manual=BookParser()
    manual.feed((DOCS/'H2RES_USER_MANUAL.html').read_text(encoding='utf-8'))
    checked=0
    for target in manual.links+manual.images:
        if target.startswith('#') or urlparse(target).scheme: continue
        path=(DOCS/unquote(target.split('#')[0])).resolve()
        relative=path.relative_to(DOCS).as_posix()
        assert relative in file_hashes or path.is_dir(), 'Missing offline manual asset: '+target
        checked+=1
    with zipfile.ZipFile(ARCHIVE, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in files:
            bundle.write(path, 'docs/' + path.relative_to(DOCS).as_posix())
        bundle.writestr('docs/PACKAGE_CONTENTS.json', json.dumps(file_hashes, indent=2))
    with zipfile.ZipFile(ARCHIVE) as bundle:
        invalid_member = bundle.testzip()
        assert invalid_member is None, invalid_member
        for name, expected in file_hashes.items():
            assert hashlib.sha256(bundle.read('docs/' + name)).hexdigest() == expected, name
    report = dict(archive=ARCHIVE.name, files=len(files)+1, bytes=ARCHIVE.stat().st_size,
                  sha256=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
                  crc_and_file_hashes_verified=True, source_datasets_included=False,
                  focused_manual_local_links_verified=checked,model_executed=False)
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
