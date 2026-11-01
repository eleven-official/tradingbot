"""Reproducible local training. No broker keys or order submission."""
import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from core.fusion import analogue, analogue_store
from core.fusion.instrument_history import yahoo_history


def write_snapshot(report,rows):
    data=json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if hashlib.sha256(data).hexdigest()!=report['data_sha256']:
        raise ValueError('Training snapshot does not match its report fingerprint')
    target=analogue_store.directory()/(report['id']+'.data.json.gz')
    if target.exists():
        digest=hashlib.sha256()
        total=0
        with gzip.open(target,'rb') as stream:
            while chunk:=stream.read(65536):
                total+=len(chunk)
                if total>300000000:
                    raise ValueError('Existing training snapshot exceeds size limit')
                digest.update(chunk)
        if digest.hexdigest()!=report['data_sha256']:
            raise ValueError('Existing training snapshot failed integrity; preserve it for review before retraining')
        return target
    name=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.history-',delete=False) as raw:
            name=raw.name
            with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as compressed:
                compressed.write(data)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(name,target)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()
    return target


def read_csv(path):
    path=Path(path)
    if path.stat().st_size>80000000:
        raise ValueError('CSV must be at most 80 MB')
    rows=[]
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        required={'timestamp','open','high','low','close','volume'}
        if not required<=set(reader.fieldnames or []) or len(set(reader.fieldnames or []))!=len(reader.fieldnames or []):
            raise ValueError('CSV needs unique timestamp, open, high, low, close, volume columns')
        for item in reader:
            if len(rows)>=analogue.MAX_BARS:
                raise ValueError('CSV exceeds 500000 candles')
            row={key:float(item[key]) for key in ('open','high','low','close','volume')}
            row['timestamp']=item['timestamp']
            for key in ('session','contract'):
                if key in item:
                    row[key]=item[key]
            rows.append(row)
    return rows


def train(symbols,*,years=20,horizon=3,timeframe='1d',commission=0.01,slippage_ticks=1.0,csv_path=None,source=None):
    if csv_path and len(symbols)!=1:
        raise ValueError('A CSV contains one instrument; select exactly one symbol')
    if not csv_path and (timeframe!='1d' or any(symbol not in {'SPY','QQQ','AAPL','MSFT','NVDA','TSLA'} for symbol in symbols)):
        raise ValueError('Futures/intraday training requires a licensed actual-contract/session CSV; Yahoo daily data is not a substitute')
    results=[]
    for symbol in symbols:
        try:
            rows=read_csv(csv_path) if csv_path else yahoo_history(symbol,years)
            provenance=source or ('Operator CSV; verify vendor rights and adjustments' if csv_path else 'Yahoo Finance via yfinance; daily OHLCV; no dividend adjustment; research only')
            report,artifact=analogue.build(rows,symbol=symbol,timeframe=timeframe,years=years,horizon=horizon,
                                           commission=commission,slippage_ticks=slippage_ticks,source=provenance)
            analogue_store.save(report,artifact)
            # Keep the exact private source snapshot, not just prototypes, so
            # repeated training can verify the original data fingerprint.
            target=write_snapshot(report,rows)
            results.append({'symbol':symbol,'trained':True,'id':report['id'],'version':report['version'],
                            'coverage':report['coverage'],'validation':report['validation'],'test':report['test'],
                            'status':report['status'],'latest_view':report['latest']['decision'] if report['latest'] else None,
                            'snapshot':target.name,'broker_execution_enabled':False})
        except (ValueError,ConnectionError,OSError,EOFError,KeyError,TypeError) as exc:
            results.append({'symbol':symbol,'trained':False,'error_type':type(exc).__name__,
                            'error':str(exc) if isinstance(exc,(ValueError,ConnectionError)) else 'Local input/storage operation failed'})
    return results


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols',nargs='+',default=['SPY','QQQ','AAPL','MSFT'])
    parser.add_argument('--years',type=int,choices=[10,15,20],default=20)
    parser.add_argument('--horizon',type=int,choices=range(1,13),default=3)
    parser.add_argument('--timeframe',choices=list(analogue.MINUTES),default='1d')
    parser.add_argument('--commission',type=float,default=0.01)
    parser.add_argument('--slippage-ticks',type=float,default=1.0)
    parser.add_argument('--csv',dest='csv_path')
    parser.add_argument('--source')
    args=vars(parser.parse_args(argv))
    try:
        results=train(**args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({'results':results,'future_profitability_proven':False,'orders_submitted':False},indent=2,allow_nan=False))
    return 0 if all(row['trained'] for row in results) else 1


if __name__=='__main__':
    sys.exit(main())
