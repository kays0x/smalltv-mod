"""Build a theme for the configured LAN addresses without editing its source."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
from theme_pack import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--kind', choices=['agents', 'usage'], required=True)
    parser.add_argument('--theme-id', required=True, help='Use a fresh ID when installing a revision')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    name = 'agent-work' if args.kind == 'agents' else 'codexbar-usage'
    manifest = json.loads((REPO / 'examples/themes' / name / 'theme.json').read_text())
    manifest['theme']['id'] = args.theme_id
    for source in manifest['data']:
        provider = source['id']
        endpoint = f'agent-{provider}' if args.kind == 'agents' else provider
        source['url'] = f"http://{config['bind_ip']}:{config['port']}/{endpoint}.json"
    with tempfile.TemporaryDirectory() as scratch:
        source = Path(scratch)
        (source / 'theme.json').write_text(json.dumps(manifest))
        package = build(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package)
    print(f'Built {args.output}: {len(package)} bytes (firmware validator passed)')


if __name__ == '__main__':
    main()
