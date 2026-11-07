"""Test a built image using real development fixtures, without private Water data.

Requires Docker Engine. Uses only Python standard library on the host. Neither
this verifier nor its fixtures change frozen models or preprocessing.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def wait_for_health(base, timeout=180):
    """Wait through transient port resets, but retain a bounded readiness gate."""
    deadline = time.monotonic() + timeout
    last_error = None
    while True:
        try:
            with urllib.request.urlopen(base + '/health', timeout=3) as response:
                health = json.load(response)
            if health['ready']:
                return health
            last_error = RuntimeError('Health endpoint reports ready=false')
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Container did not become ready within {timeout} seconds') from last_error
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    token = secrets.token_urlsafe(32)
    env = {**os.environ, 'FISCYCLE_AI_SERVICE_TOKEN': token}
    pytest_name = 'fiscycle-pytest-' + uuid.uuid4().hex[:12]
    live_name = 'fiscycle-http-' + uuid.uuid4().hex[:12]
    mounts = ['--volume', f'{ROOT / "tools"}:/service/tools:ro']

    def docker(*arguments, capture=False):
        result = subprocess.run(['docker', *arguments], env=env, check=True,
                                stdout=subprocess.PIPE if capture else None,
                                text=True)
        return result.stdout.strip() if capture else None

    with tempfile.TemporaryDirectory(prefix='fiscycle-container-') as folder:
        output = Path(folder)
        try:
            docker('run', '--rm', '--network', 'none', *mounts,
                   args.image, 'python', 'tools/verify_checkout.py')
            docker('run', '--name', pytest_name, '--network', 'none',
                   '--env', 'FISCYCLE_RUNTIME_ENV=development',
                   '--env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', *mounts,
                   '--volume', f'{ROOT / "tests"}:/service/tests:ro',
                   args.image, 'python', 'tools/offline_guard.py', 'pytest',
                   'tests/test_service.py', '-q',
                   '--junitxml=/service/.cache/container-tests.xml')
            docker('cp', pytest_name + ':/service/.cache/container-tests.xml', str(output / 'tests.xml'))
            tree = ET.parse(output / 'tests.xml')
            suites = list(tree.getroot().iter('testsuite'))
            counts = {key: sum(int(s.get(key, 0)) for s in suites)
                      for key in ['tests', 'failures', 'errors', 'skipped']}
            assert counts == {'tests': 18, 'failures': 0, 'errors': 0, 'skipped': 2}, counts
            skipped = {case.get('name') for case in tree.getroot().iter('testcase')
                       if case.find('skipped') is not None}
            assert skipped == {'test_water_golden_and_dss', 'test_water_replay_paired_metrics'}, skipped

            docker('run', '--detach', '--name', live_name,
                   '--publish', '127.0.0.1::8000',
                   '--env', 'FISCYCLE_AI_SERVICE_TOKEN', *mounts,
                   args.image, 'python', 'tools/offline_guard.py', 'uvicorn',
                   'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--workers', '1')
            binding = docker('port', live_name, '8000/tcp', capture=True)
            base = 'http://' + binding.splitlines()[0]
            health = wait_for_health(base)
            assert not health['services']['water_replay']
            assert health['services']['bsf_replay'] and health['services']['curated_gallery']
            assert all(row['loaded'] and row['artifacts_verified'] and row['model_source'] == 'local'
                       for row in health['runtime_models'].values())

            docker('exec', live_name, 'python', 'tools/offline_guard.py', 'tools.http_smoke',
                   '--base-url', 'http://127.0.0.1:8000',
                   '--water-fixture', '/private-fixture-not-supplied/water_reference.json',
                   '--output', '/service/.cache/container-http.json')
            docker('cp', live_name + ':/service/.cache/container-http.json', str(output / 'http.json'))
            http = json.loads((output / 'http.json').read_text())
            skipped_http = {row['check'] for row in http['checks'] if row['status'] == 'SKIPPED'}
            assert skipped_http == {'Water numeric forecasts', 'Water replay'}, skipped_http
            assert all(row['status'] in {'PASS', 'SKIPPED'} for row in http['checks'])
            assert sum(row['status'] == 'PASS' for row in http['checks']) >= 19
            print(json.dumps({'status': 'PASS_WITH_EXPLICIT_PRIVATE_WATER_SKIPS',
                              'pytest': counts,
                              'http_passed': sum(row['status'] == 'PASS' for row in http['checks']),
                              'private_water_checks': 'NOT_RUN_PRIVATE_FIXTURES_NOT_UPLOADED',
                              'all_four_models_loaded': True}, indent=2), flush=True)
        except Exception:
            subprocess.run(['docker', 'logs', live_name], check=False)
            raise
        finally:
            for name in [live_name, pytest_name]:
                subprocess.run(['docker', 'rm', '--force', name], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
