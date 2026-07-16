import unittest
import os
import tempfile
from types import SimpleNamespace
from unittest import mock

from align_engine import (
    _aligned_aaf_filename,
    _base36,
    _unique_aligned_clip_name,
    _unique_ptx_wav_name,
    align_aafs,
    get_all_clips,
)


class AlignmentHelperTests(unittest.TestCase):
    def test_preflight_rejects_existing_output_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as root:
            audio_dir = os.path.join(root, "Audio Files")
            os.makedirs(audio_dir)
            reference = os.path.join(root, "reference.aaf")
            target = os.path.join(root, "target.aaf")
            output = os.path.join(root, "output.aaf")
            for path, payload in (
                (reference, b"reference"),
                (target, b"target"),
                (output, b"preserve"),
            ):
                with open(path, "wb") as stream:
                    stream.write(payload)

            with self.assertRaises(FileExistsError):
                align_aafs(
                    reference,
                    audio_dir,
                    target,
                    audio_dir,
                    output,
                )

            with open(output, "rb") as stream:
                self.assertEqual(stream.read(), b"preserve")

    def test_preflight_rejects_missing_audio_directory_before_copy(self):
        with tempfile.TemporaryDirectory() as root:
            reference = os.path.join(root, "reference.aaf")
            target = os.path.join(root, "target.aaf")
            reference_audio = os.path.join(root, "Reference Audio")
            missing_audio = os.path.join(root, "Missing Audio")
            output = os.path.join(root, "output.aaf")
            os.makedirs(reference_audio)
            for path in (reference, target):
                with open(path, "wb") as stream:
                    stream.write(b"test")

            with self.assertRaises(FileNotFoundError):
                align_aafs(
                    reference,
                    reference_audio,
                    target,
                    missing_audio,
                    output,
                )

            self.assertFalse(os.path.exists(output))

    def test_aaf_filename_handles_uppercase_extension_and_existing_suffix(self):
        self.assertEqual(
            _aligned_aaf_filename("Boom.WAV"),
            "Boom_ottoaligned.WAV",
        )
        self.assertEqual(
            _aligned_aaf_filename("Boom_OTTOALIGNED.wav"),
            "Boom_OTTOALIGNED.wav",
        )

    def test_base36_boundaries(self):
        self.assertEqual(_base36(0), "0")
        self.assertEqual(_base36(35), "Z")
        self.assertEqual(_base36(36), "10")

    def test_ptx_name_preserves_length_and_channel_suffix(self):
        source = "IND_15_BOOM_-Gain_03_PFX_Ready.A1.wav"
        candidate, next_serial = _unique_ptx_wav_name(source, 1, set())

        self.assertEqual(candidate, "IND_15_BOOM_-Gain_03_PFX_OA001.A1.wav")
        self.assertEqual(next_serial, 2)
        self.assertEqual(len(candidate.encode("utf-8")), len(source.encode("utf-8")))

    def test_ptx_name_skips_reserved_case_insensitively(self):
        source = "IND_15_BOOM_-Gain_03_PFX_Ready.A1.wav"
        reserved = {"ind_15_boom_-gain_03_pfx_oa001.a1.wav"}

        candidate, next_serial = _unique_ptx_wav_name(source, 1, reserved)

        self.assertEqual(candidate, "IND_15_BOOM_-Gain_03_PFX_OA002.A1.wav")
        self.assertEqual(next_serial, 3)

    def test_duplicate_source_clip_names_receive_unique_output_names(self):
        reserved = {"Clip", "Clip_ALIGNED"}

        first = _unique_aligned_clip_name("Clip", reserved)
        second = _unique_aligned_clip_name("Clip", reserved)

        self.assertEqual(first, "Clip_ALIGNED_2")
        self.assertEqual(second, "Clip_ALIGNED_3")

    def test_aaf_target_can_be_opened_read_write(self):
        fake_file = SimpleNamespace(
            content=SimpleNamespace(mobs=[]),
        )
        with mock.patch("align_engine.aaf2.open", return_value=fake_file) as opener:
            clips, returned_file = get_all_clips("target.aaf", aaf_mode="rw")

        self.assertEqual(clips, [])
        self.assertIs(returned_file, fake_file)
        opener.assert_called_once_with("target.aaf", "rw")


if __name__ == "__main__":
    unittest.main()
