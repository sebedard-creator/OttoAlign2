import os
import tempfile
import unittest
import zipfile

from server import _find_session_bundle, _safe_extract


class ServerHelperTests(unittest.TestCase):
    def test_find_session_bundle_accepts_one_nested_complete_session(self):
        with tempfile.TemporaryDirectory() as root:
            project = os.path.join(root, "export", "Project")
            audio_dir = os.path.join(project, "Audio Files")
            os.makedirs(audio_dir)
            session_path = os.path.join(project, "session.PTX")
            with open(session_path, "wb") as stream:
                stream.write(b"test")

            result = _find_session_bundle(root, "test")

            self.assertEqual(result, (session_path, audio_dir))

    def test_find_session_bundle_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("one", "two"):
                project = os.path.join(root, name)
                os.makedirs(os.path.join(project, "Audio Files"))
                with open(os.path.join(project, f"{name}.ptx"), "wb") as stream:
                    stream.write(b"test")

            with self.assertRaisesRegex(ValueError, "plusieurs sessions"):
                _find_session_bundle(root, "test")

    def test_safe_extract_rejects_parent_path(self):
        with tempfile.TemporaryDirectory() as root:
            archive_path = os.path.join(root, "unsafe.zip")
            destination = os.path.join(root, "destination")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "unsafe")

            with self.assertRaisesRegex(ValueError, "Unsafe path"):
                _safe_extract(archive_path, destination)

            self.assertFalse(os.path.exists(os.path.join(root, "escape.txt")))


if __name__ == "__main__":
    unittest.main()
