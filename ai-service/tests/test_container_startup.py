"""Host-side transport regression tests; no models or Docker required."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_container import wait_for_health


class StartupTests(unittest.TestCase):
    def test_transient_failures_and_unready_then_healthy(self):
        responses = [ConnectionResetError(104, 'reset'),
                     ConnectionRefusedError(), TimeoutError(),
                     urllib.error.URLError('not listening'),
                     io.BytesIO(b'{"ready":false}'),
                     io.BytesIO(b'{"ready":true,"services":{}}')]
        with patch('tools.verify_container.urllib.request.urlopen', side_effect=responses), \
             patch('tools.verify_container.time.sleep') as sleep:
            self.assertTrue(wait_for_health('http://localhost')['ready'])
            self.assertEqual(sleep.call_count, 5)

    def test_repeated_resets_have_bounded_timeout_and_cause(self):
        with patch('tools.verify_container.urllib.request.urlopen', side_effect=ConnectionResetError()), \
             patch('tools.verify_container.time.monotonic', side_effect=[0, 181]):
            with self.assertRaises(RuntimeError) as caught:
                wait_for_health('http://localhost')
            self.assertIsInstance(caught.exception.__cause__, ConnectionResetError)

    def test_malformed_response_is_not_hidden_as_startup_delay(self):
        with patch('tools.verify_container.urllib.request.urlopen', return_value=io.BytesIO(b'not json')):
            with self.assertRaises(json.JSONDecodeError):
                wait_for_health('http://localhost')


if __name__ == '__main__':
    unittest.main()
