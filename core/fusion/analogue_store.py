"""Local, immutable analogue bundles; no private data is published or uploaded."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from itertools import islice


def directory():
    return Path(os.environ.get('LOKI_ANALOGUE_DIR', str(Path(__file__).resolve().parents[2]/'state/analogue_models'))).resolve()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def catalog():
    from core.fusion.analogue import VERSION
    root=directory()
    files=list(islice(root.glob('*.json'),201)) if root.exists() else []
    models,unreadable=[],0
    for path in files[:200]:
        if not re.fullmatch(r'[a-f0-9]{64}',path.stem):
            continue
        try:
            report,_=load(path.stem)
            models.append({key:report[key] for key in ('id','symbol','version','timeframe','horizon_bars','coverage','status','source')})
        except (ValueError,KeyError,TypeError,OSError):
            unreadable+=1
    models.sort(key=lambda row:(row['version']==VERSION,row['coverage']['end'],row['symbol'],row['id']),reverse=True)
    return {'model_version':VERSION,'models':models,'unreadable_models':unreadable,
            'scan_limit_reached':len(files)>200,'research_only':True}


def load(identifier):
    if not re.fullmatch(r'[a-f0-9]{64}',identifier):
        raise ValueError('Invalid analogue model identifier')
    path=directory()/(identifier+'.json')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Saved analogue model not found')
    with path.open('rb') as stream:
        data=stream.read(8000001)
    if len(data)>8000000:
        raise ValueError('Saved analogue bundle exceeds size limit')
    bundle=json.loads(data)
    digest=fingerprint(bundle['artifact'])
    if bundle['report']['id']!=identifier or digest!=bundle['report']['artifact_sha256']:
        raise ValueError('Saved analogue bundle failed its integrity check')
    expected=hashlib.sha256((bundle['report']['data_sha256']+digest).encode()).hexdigest()
    if expected!=identifier:
        raise ValueError('Saved analogue data/model identity failed its integrity check')
    if bundle.get('format')==2:
        if fingerprint(bundle['report'])!=bundle.get('report_sha256'):
            raise ValueError('Saved analogue report failed its integrity check')
    from core.fusion.analogue import VERSION
    if bundle.get('format')!=2 or bundle['artifact'].get('version')!=VERSION:
        # Keep older reports viewable, but never present v1's flawed historical
        # cost-hurdle evaluation as eligibility for a current forecast.
        bundle['report']['status']='legacy_research_retrain_required'
        bundle['report']['broker_execution_enabled']=False
        bundle['report']['limitations']=bundle['report'].get('limitations',[])+[
            'Legacy bundle: view historical results only; retrain with '+VERSION+' for current forecast rules. Version 1 also used next-open information in the cost-hurdle decision.'
        ]
    return bundle['report'],bundle['artifact']


def save(report,artifact):
    root=directory()
    root.mkdir(parents=True,exist_ok=True)
    target=root/(report['id']+'.json')
    if target.exists():
        return load(report['id'])[0]
    data=json.dumps({'format':2,'report':report,'artifact':artifact,'report_sha256':fingerprint(report)},allow_nan=False,separators=(',',':')).encode()
    if len(data)>8000000:
        raise ValueError('Analogue bundle exceeds size limit')
    name=None
    try:
        with tempfile.NamedTemporaryFile(dir=root,prefix='.analogue-',delete=False) as stream:
            name=stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,target)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()
    return report
