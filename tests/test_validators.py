from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.validators import (  # noqa: E402
    LsppValidationError,
    ensure_within_allowed_roots,
    format_part_ids,
    validate_cfile_content,
)


class ValidatorTests(unittest.TestCase):
    def test_blocks_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            outside = root.parent / "outside.txt"
            with self.assertRaises(LsppValidationError):
                ensure_within_allowed_roots(outside, root, [root])

    def test_forbidden_system_command(self) -> None:
        with self.assertRaises(LsppValidationError):
            validate_cfile_content("c generated\nsystem del important.txt\nexit\n")

    def test_part_id_formatting(self) -> None:
        self.assertEqual(format_part_ids(3), "3")
        self.assertEqual(format_part_ids([1, 2, 3]), "1,2,3")
        self.assertEqual(format_part_ids("1:10"), "1:10")
        with self.assertRaises(LsppValidationError):
            format_part_ids("../bad")


if __name__ == "__main__":
    unittest.main()
