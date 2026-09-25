"""The knowledge-base fetcher only reaches public addresses, on every redirect hop."""
import unittest
from unittest.mock import MagicMock, patch

import kb

PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 443))]
INTERNAL = [(2, 1, 6, "", ("10.0.0.7", 443))]


def _response(status=200, location=None):
    res = MagicMock(status_code=status)
    res.is_redirect = location is not None
    res.headers = {"location": location} if location else {}
    return res


class TestKbUrlSafety(unittest.TestCase):
    def test_hostname_resolving_inside_is_refused(self):
        with patch("socket.getaddrinfo", return_value=INTERNAL), patch("httpx.get") as get:
            with self.assertRaises(ValueError):
                kb._safe_get("https://intranet.example.com/page", timeout=5)
        get.assert_not_called()

    def test_redirect_into_the_network_is_refused(self):
        hops = [_response(302, "http://169.254.169.254/latest/meta-data/")]
        with patch("socket.getaddrinfo", return_value=PUBLIC), patch("httpx.get", side_effect=hops) as get:
            with self.assertRaises(ValueError):
                kb._safe_get("https://example.com/start", timeout=5)
        self.assertEqual(get.call_count, 1)

    def test_public_redirects_are_followed(self):
        hops = [_response(301, "/moved"), _response(200)]
        with patch("socket.getaddrinfo", return_value=PUBLIC), patch("httpx.get", side_effect=hops) as get:
            kb._safe_get("https://example.com/start", timeout=5)
        self.assertEqual(get.call_args_list[1].args[0], "https://example.com/moved")
        self.assertFalse(get.call_args_list[0].kwargs["follow_redirects"])

    def test_redirect_loops_stop(self):
        with patch("socket.getaddrinfo", return_value=PUBLIC), patch("httpx.get", return_value=_response(302, "/again")):
            with self.assertRaises(ValueError):
                kb._safe_get("https://example.com/", timeout=5)


if __name__ == "__main__":
    unittest.main()
