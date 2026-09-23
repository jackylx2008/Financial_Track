from __future__ import annotations

import tempfile
import unittest
import json
import ctypes
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from unittest.mock import MagicMock, patch

from flows.gui.review_file_server import (
    ReviewFileServer,
    _open_with_windows_file_association,
    resolve_allowed_source,
)


class ReviewFileServerTests(unittest.TestCase):
    def test_windows_opener_uses_registered_open_verb(self) -> None:
        shell32 = MagicMock()
        shell32.ShellExecuteW.return_value = 33
        with patch.object(ctypes, "windll", create=True) as windll:
            windll.shell32 = shell32
            source = Path(r"C:\sample\statement.pdf")

            _open_with_windows_file_association(source)

        shell32.ShellExecuteW.assert_called_once_with(
            None,
            "open",
            str(source),
            None,
            str(source.parent),
            1,
        )

    def test_windows_opener_reports_missing_file_association(self) -> None:
        shell32 = MagicMock()
        shell32.ShellExecuteW.return_value = 31
        with patch.object(ctypes, "windll", create=True) as windll:
            windll.shell32 = shell32
            with self.assertRaisesRegex(OSError, "错误码 31"):
                _open_with_windows_file_association(Path(r"C:\sample\message.eml"))

    def test_allows_existing_file_below_raw_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw_data"
            source = root / "bank" / "statement.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"sample")

            resolved = resolve_allowed_source(str(source), root)

            self.assertEqual(resolved, source.resolve())

    def test_rejects_file_outside_raw_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "raw_data"
            root.mkdir()
            outside = parent / "private.txt"
            outside.write_text("sample", encoding="utf-8")

            with self.assertRaises(ValueError):
                resolve_allowed_source(str(outside), root)

    def test_local_server_serves_review_and_delegates_source_to_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            raw_root = parent / "raw_data"
            source = raw_root / "bank" / "statement.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"sample")
            review = parent / "review.html"
            review.write_text("<h1>review</h1>", encoding="utf-8")
            opened: list[Path] = []
            with patch("flows.gui.review_file_server.open_with_default_application", side_effect=opened.append):
                server = ReviewFileServer(review, raw_root)
                try:
                    url = server.start()
                    with urlopen(url, timeout=2) as response:
                        self.assertIn("review", response.read().decode("utf-8"))
                    parsed = urlparse(url)
                    token = parse_qs(parsed.query)["token"][0]
                    query = urlencode({"path": str(source), "token": token})
                    endpoint = f"{parsed.scheme}://{parsed.netloc}/open-source?{query}"
                    with urlopen(endpoint, timeout=2) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                finally:
                    server.close()

            self.assertEqual(payload["status"], "opened")
            self.assertEqual(opened, [source.resolve()])

    def test_local_server_saves_review_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            raw_root = parent / "raw_data"
            raw_root.mkdir()
            review = parent / "review.html"
            review.write_text("<h1>review</h1>", encoding="utf-8")
            received: list[dict[str, object]] = []

            def saver(payload: dict[str, object]) -> dict[str, object]:
                received.append(payload)
                return {"status": "saved"}

            server = ReviewFileServer(review, raw_root, selection_saver=saver)
            try:
                url = server.start()
                parsed = urlparse(url)
                token = parse_qs(parsed.query)["token"][0]
                endpoint = f"{parsed.scheme}://{parsed.netloc}/save-selection?token={token}"
                request = Request(
                    endpoint,
                    data=json.dumps({"authoritative_group_token": "email-a"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.close()

            self.assertEqual(payload["status"], "saved")
            self.assertEqual(received, [{"authoritative_group_token": "email-a"}])


if __name__ == "__main__":
    unittest.main()
