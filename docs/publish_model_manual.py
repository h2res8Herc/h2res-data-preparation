"""Place the checked documentation beside the specified model without changing it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

D=Path(__file__).resolve().parent


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-root',type=Path,required=True)
    a=p.parse_args(); model=a.model_root.resolve()
    manifest=json.loads((D/'inventory/documented_version.json').read_text(encoding='utf-8'))
    assert model==Path(manifest['model_root']).resolve(), 'Destination must match inspected model'
    validation=json.loads((D/'inventory/documentation_validation.json').read_text(encoding='utf-8'))
    assert validation['passed'], 'Documentation validation must pass before publication'
    expected={key.split('/',1)[1]:value for key,value in manifest['source_hashes'].items() if key.startswith('model/')}
    for relative,digest in expected.items(): assert sha(model/relative)==digest, 'Model source changed: '+relative
    destination=(model/'docs/user_manual_2026_11_12').resolve()
    assert destination.is_relative_to(model/'docs'), 'Publication must stay inside model docs'
    archive=D/'H2RES_DOCUMENTATION_PACKAGE.zip'
    checks=json.loads((D/'inventory/package_validation.json').read_text(encoding='utf-8'))
    assert sha(archive)==checks['sha256'], 'Package changed after verification'
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        contents=json.loads(z.read('docs/PACKAGE_CONTENTS.json'))
        for member in z.infolist():
            if member.is_dir(): continue
            relative=Path(member.filename).relative_to('docs')
            target=(destination/relative).resolve()
            assert target.is_relative_to(destination), 'Unsafe archive member'
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(member) as incoming,target.open('wb') as out: shutil.copyfileobj(incoming,out)
        for relative,digest in contents.items(): assert sha(destination/relative)==digest, 'Copy verification failed: '+relative
    pdf=model/'docs/H2RES_USER_MANUAL.pdf'
    share=model/'docs/H2RES_USER_MANUAL_2026_11_12.zip'
    shutil.copyfile(D/'H2RES_USER_MANUAL.pdf',pdf)
    shutil.copyfile(archive,share)
    assert sha(pdf)==sha(D/'H2RES_USER_MANUAL.pdf')
    assert sha(share)==checks['sha256']
    for relative,digest in expected.items(): assert sha(model/relative)==digest, 'Original model source changed: '+relative
    report=dict(model_root=str(model),manual_pdf=str(pdf),html=str(destination/'H2RES_USER_MANUAL.html'),
                archive=str(share),files_verified=len(contents),archive_sha256=sha(share),
                original_model_sources_unchanged=True,model_executed=False)
    (D/'inventory/manual_publication.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (destination/'inventory/manual_publication.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
