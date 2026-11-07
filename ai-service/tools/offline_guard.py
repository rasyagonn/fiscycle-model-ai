"""Verification launcher: deny HF imports and external networking, allow loopback."""
import importlib.abc
import ipaddress
import os
from pathlib import Path
import runpy
import sys


class NoHuggingFace(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'huggingface_hub', 'hf_xet'}:
            raise ModuleNotFoundError('Hugging Face deliberately disabled for offline verification')
        return None


def local_address(value):
    if isinstance(value, bytes):
        value = value.decode('ascii')
    if value in {'localhost', None}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def audit(event, args):
    if event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple) and not local_address(address[0]):
            raise PermissionError('External connections disabled by offline verification')
    if event == 'socket.getaddrinfo' and not local_address(args[0]):
        raise PermissionError('External DNS disabled by offline verification')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0]).replace('\\', '/').lower()
        if any(part in path for part in ['/.agents/', '/.local_data/', '/hf_model_upload/', '/.cache/huggingface/']):
            raise PermissionError('Research/HF storage disabled by offline verification')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python tools/offline_guard.py MODULE [arguments]')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.meta_path.insert(0, NoHuggingFace())
    sys.addaudithook(audit)
    os.environ['YOLO_OFFLINE'] = 'true'
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    module = sys.argv.pop(1)
    sys.argv[0] = module
    runpy.run_module(module, run_name='__main__')
