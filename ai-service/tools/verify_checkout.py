"""Verify bundled model and gallery hashes without importing ML dependencies."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def verify(path, expected):
    if not path.is_file():
        raise SystemExit(f'MISSING: {path.relative_to(ROOT)}')
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise SystemExit(f'CHECKSUM MISMATCH: {path.relative_to(ROOT)}')


def main():
    registry = json.loads((ROOT / 'model_registry.json').read_text(encoding='utf-8'))
    count = 0
    for entry in registry['models'].values():
        for name, expected in entry['files'].items():
            verify(ROOT / entry['local_dir'] / name, expected)
            count += 1
    gallery = json.loads((ROOT / 'assets/demo_gallery/competition_gallery_selection.json').read_text(encoding='utf-8'))
    items = gallery['images']
    for item in items:
        verify(ROOT / 'assets/demo_gallery' / item['file'], item['sha256'])
        verify(ROOT / 'assets/demo_gallery' / item['thumbnail'], item['thumbnail_sha256'])
    print(json.dumps({'status': 'PASS', 'release': registry['release'],
                      'model_bundles': len(registry['models']), 'model_files': count,
                      'demo_images': len(items)}, indent=2))


if __name__ == '__main__':
    main()
