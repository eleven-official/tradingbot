"""Native MiroFish report normalization. AGPL-3.0, see upstream/LICENSE.

Executes the retained original data classes in a separate process. It neither
contacts the MiroFish HTTP API nor imports any LLM, graph or broker SDK.
"""
import importlib.util
import json
from pathlib import Path
import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='strict')


def main():
    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Native report is too large')
    value = json.loads(raw)
    source = Path(__file__).with_name('report_contracts.py')
    spec = importlib.util.spec_from_file_location('loki_mirofish_report_contracts', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ReportManager.REPORTS_DIR=value['reports_directory']
    report=module.ReportManager.get_report(value['report_id'])
    if report is None:
        raise ValueError('Native report not found')
    print(json.dumps({'report':report.to_dict(), 'native_classes':['ReportManager','Report','ReportOutline','ReportSection','ReportStatus']}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'error':'Native MiroFish report contracts rejected this artifact'}))
        raise SystemExit(1)
