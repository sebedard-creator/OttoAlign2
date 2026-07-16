import aaf2
import numpy as np
import soundfile as sf
import re
import os
import shutil
import tempfile

import pt_api

def get_clip_absolute_times(sequence):
    """
    Returns a list of dictionaries containing info for every clip in the sequence.
    """
    clips = []
    current_time = 0
    
    for comp in sequence.components:
        start_time = current_time
        length = comp.length
        current_time += length
        
        if isinstance(comp, aaf2.components.SourceClip):
            clips.append({
                'type': 'SourceClip',
                'comp': comp,
                'timeline_start': start_time,
                'timeline_end': current_time,
                'length': length,
                'source_start': comp.start,
                'mob': comp.mob
            })
        elif isinstance(comp, aaf2.components.OperationGroup):
            # Try to find the SourceClip inside the OperationGroup
            src = None
            for seg in comp.segments:
                if isinstance(seg, aaf2.components.SourceClip) and seg.mob:
                    src = seg
                    break
            if src:
                clips.append({
                    'type': 'OperationGroup',
                    'comp': comp,
                    'src_comp': src,
                    'timeline_start': start_time,
                    'timeline_end': current_time,
                    'length': length,
                    'source_start': src.start,
                    'mob': src.mob
                })
    return clips

def get_all_clips(file_path, aaf_mode="r"):
    """
    Wrapper to get clips from either AAF or PTX
    """
    is_ptx = file_path.lower().endswith('.ptx')
    if is_ptx:
        session = pt_api.ProToolsSession(file_path)
        raw_clips = session.get_timeline_clips(include_fades=False)
        clips = []
        for c in raw_clips:
            if not c.get('is_fade', False):
                wav_name = c.get('physical_filename') or c['clip_name']
                if not wav_name.lower().endswith('.wav'):
                    wav_name += '.wav'

                clips.append({
                    'track': c['track'],
                    'clip_name': c['clip_name'],
                    'timeline_start': c['start_samples'],
                    'timeline_end': c['end_samples'],
                    'source_start': c['src_offset_samples'],
                    'physical_filename': wav_name,
                    'mob': None
                })
        return clips, session
    else:
        f = aaf2.open(file_path, aaf_mode)
        clips = []
        for mob in f.content.mobs:
            if isinstance(mob, aaf2.mobs.CompositionMob):
                for slot in mob.slots:
                    if isinstance(slot.segment, aaf2.components.Sequence):
                        clips.extend(get_clip_absolute_times(slot.segment))

        return clips, f

def find_overlapping_reference(target_clip, ref_clips):
    """
    Finds the reference clip that has the largest overlap with the target_clip.
    """
    best_ref = None
    max_overlap = 0
    t_start = target_clip['timeline_start']
    t_end = target_clip['timeline_end']
    
    for r in ref_clips:
        r_start = r['timeline_start']
        r_end = r['timeline_end']
        
        overlap_start = max(t_start, r_start)
        overlap_end = min(t_end, r_end)
        overlap = overlap_end - overlap_start
        
        if overlap > max_overlap:
            max_overlap = overlap
            best_ref = r
            
    return best_ref, max_overlap

def get_physical_filename(mob):
    import urllib.parse
    if isinstance(mob, aaf2.mobs.MasterMob):
        for slot in mob.slots:
            if isinstance(slot.segment, aaf2.components.SourceClip) and slot.segment.mob:
                if slot.segment.mob.descriptor and 'Locator' in slot.segment.mob.descriptor:
                    for loc in slot.segment.mob.descriptor['Locator']:
                        url = loc['URLString'].value
                        return urllib.parse.unquote(url.split('/')[-1])
    elif isinstance(mob, aaf2.mobs.SourceMob):
        if mob.descriptor and 'Locator' in mob.descriptor:
            for loc in mob.descriptor['Locator']:
                url = loc['URLString'].value
                return urllib.parse.unquote(url.split('/')[-1])
    return mob.name + ".wav"

def read_audio_chunk(wav_path, start_sample, length):
    """
    Reads a specific chunk of audio from a WAV file efficiently.
    """
    if not os.path.exists(wav_path):
        return None
        
    try:
        info = sf.info(wav_path)
        total_frames = info.frames
        
        if start_sample >= total_frames:
            return np.zeros(length, dtype=np.float32)
            
        read_start = max(0, start_sample)
        read_length = length
        
        if start_sample < 0:
            read_length = length + start_sample
            
        if read_start + read_length > total_frames:
            read_length = total_frames - read_start
            
        if read_length <= 0:
            return np.zeros(length, dtype=np.float32)
            
        data, rate = sf.read(wav_path, start=read_start, frames=read_length)
    except Exception as e:
        print(f"Error reading {wav_path}: {e}")
        return None
    
    # Handle stereo/multichannel by taking the first channel
    if len(data.shape) > 1:
        data = data[:, 0]
        
    chunk = data.astype(np.float32)
    
    # Pad with zeros if we reached the end of the file or had a negative start
    if start_sample < 0 or len(chunk) < length:
        pad_left = max(0, -start_sample)
        pad_right = max(0, length - len(chunk) - pad_left)
        chunk = np.pad(chunk, (pad_left, pad_right), 'constant')
        
    return chunk

def _base36(value):
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if value < 0:
        raise ValueError("The output filename serial must be non-negative.")
    result = "0"
    if value:
        digits = []
        while value:
            value, remainder = divmod(value, 36)
            digits.append(alphabet[remainder])
        result = "".join(reversed(digits))
    return result


def _unique_ptx_wav_name(source_name, serial, reserved_names):
    stem, extension = os.path.splitext(source_name)
    if extension.lower() != ".wav":
        raise ValueError("PTX alignment currently supports WAV files only.")

    channel_match = re.search(r"(\.[A-Za-z]\d+)$", stem)
    channel_suffix = channel_match.group(1) if channel_match else ""
    naming_stem = stem[:-len(channel_suffix)] if channel_suffix else stem
    separator = max(
        naming_stem.rfind("_"),
        naming_stem.rfind("-"),
        naming_stem.rfind(" "),
    )
    suffix_width = len(naming_stem) - separator - 1
    if (
        suffix_width < 4
        or not naming_stem[separator + 1:].isascii()
    ):
        suffix_width = min(10, len(naming_stem))
        separator = len(naming_stem) - suffix_width - 1
    if suffix_width < 4 or not naming_stem[-suffix_width:].isascii():
        raise ValueError(
            "PTX output naming requires an ASCII suffix of at least four characters."
        )
    prefix = naming_stem[:-suffix_width]
    while True:
        encoded_serial = _base36(serial)
        if len(encoded_serial) > suffix_width - 2:
            raise OverflowError("No same-length PTX output filename remains.")
        token = "OA" + encoded_serial.rjust(suffix_width - 2, "0")
        candidate = prefix + token + channel_suffix + extension
        if len(candidate.encode("utf-8")) != len(source_name.encode("utf-8")):
            raise ValueError("Generated PTX WAV name changed its UTF-8 byte length.")
        key = candidate.casefold()
        if key not in reserved_names:
            reserved_names.add(key)
            return candidate, serial + 1
        serial += 1


def _unique_aligned_clip_name(source_name, reserved_names):
    candidate = source_name + "_ALIGNED"
    suffix = 2
    while candidate in reserved_names:
        candidate = f"{source_name}_ALIGNED_{suffix}"
        suffix += 1
    reserved_names.add(candidate)
    return candidate


def _aligned_aaf_filename(filename):
    stem, extension = os.path.splitext(filename)
    if stem.casefold().endswith("_ottoaligned"):
        return filename
    return f"{stem}_ottoaligned{extension}"


def align_aafs(
    ref_aaf_path,
    ref_audio_dir,
    target_aaf_path,
    target_audio_dir,
    out_aaf_path,
    max_shift_ms=20,
):
    if (
        isinstance(max_shift_ms, bool)
        or not isinstance(max_shift_ms, (int, float))
        or not np.isfinite(max_shift_ms)
        or max_shift_ms <= 0
    ):
        raise ValueError("max_shift_ms must be a finite positive number.")
    ref_aaf_path = os.path.abspath(ref_aaf_path)
    ref_audio_dir = os.path.abspath(ref_audio_dir)
    target_aaf_path = os.path.abspath(target_aaf_path)
    target_audio_dir = os.path.abspath(target_audio_dir)
    out_aaf_path = os.path.abspath(out_aaf_path)
    print(f"Aligning {target_aaf_path} against {ref_aaf_path}...")

    for session_path, label in (
        (ref_aaf_path, "Reference"),
        (target_aaf_path, "Target"),
    ):
        if os.path.splitext(session_path)[1].lower() not in (".aaf", ".ptx"):
            raise ValueError(f"{label} session must be an AAF or PTX file.")
        if not os.path.isfile(session_path):
            raise FileNotFoundError(f"{label} session does not exist: {session_path}")
    for audio_dir, label in (
        (ref_audio_dir, "Reference"),
        (target_audio_dir, "Target"),
    ):
        if not os.path.isdir(audio_dir):
            raise FileNotFoundError(f"{label} audio directory does not exist: {audio_dir}")

    is_ref_ptx = ref_aaf_path.lower().endswith(".ptx")
    is_target_ptx = target_aaf_path.lower().endswith(".ptx")
    for is_ptx, session_path, audio_dir, label in (
        (is_ref_ptx, ref_aaf_path, ref_audio_dir, "Reference"),
        (is_target_ptx, target_aaf_path, target_audio_dir, "Target"),
    ):
        if is_ptx:
            expected = os.path.abspath(
                os.path.join(os.path.dirname(session_path), "Audio Files")
            )
            if os.path.normcase(audio_dir) != os.path.normcase(expected):
                raise ValueError(
                    f"{label} PTX must use its sibling 'Audio Files' directory."
                )
    if os.path.normcase(out_aaf_path) == os.path.normcase(target_aaf_path):
        raise ValueError("The output session must differ from the target session.")
    if os.path.exists(out_aaf_path):
        raise FileExistsError(f"The output session already exists: {out_aaf_path}")
    output_dir = os.path.dirname(out_aaf_path)
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"The output directory does not exist: {output_dir}")
    if is_target_ptx:
        if not out_aaf_path.lower().endswith(".ptx"):
            raise ValueError("A PTX target requires a .ptx output path.")
        if os.path.normcase(os.path.dirname(out_aaf_path)) != os.path.normcase(
            os.path.dirname(target_aaf_path)
        ):
            raise ValueError(
                "The PTX output must remain beside the target's Audio Files folder."
            )

    from dsp_core import dynamic_align

    shutil.copy2(target_aaf_path, out_aaf_path)
    ref_f = None
    target_f = None
    try:
        ref_clips, ref_f = get_all_clips(ref_aaf_path)
        target_clips, target_f = get_all_clips(
            out_aaf_path,
            aaf_mode="r" if is_target_ptx else "rw",
        )
        if not ref_clips:
            raise RuntimeError("Could not find reference clips.")
        if not target_clips:
            raise RuntimeError("Could not find target clips.")
    except Exception:
        if ref_f is not None and not is_ref_ptx:
            ref_f.close()
        if target_f is not None and not is_target_ptx:
            target_f.close()
        try:
            os.remove(out_aaf_path)
        except FileNotFoundError:
            pass
        raise

    try:
        aligned_clips_log = []
        skipped_clips_log = []
        created_audio_files = []
        reserved_names = {
            name.casefold() for name in os.listdir(target_audio_dir)
        }
        reserved_clip_names = (
            {clip["name"] for clip in target_f.get_clips()}
            if is_target_ptx
            else set()
        )
        output_serial = 1
    except Exception:
        if ref_f is not None and not is_ref_ptx:
            ref_f.close()
        if target_f is not None and not is_target_ptx:
            target_f.close()
        try:
            os.remove(out_aaf_path)
        except FileNotFoundError:
            pass
        raise

    try:
        for t_clip in target_clips:
            ref_clip, overlap = find_overlapping_reference(t_clip, ref_clips)
            t_wav_name = t_clip.get("physical_filename") or get_physical_filename(
                t_clip["mob"]
            )
            if not ref_clip:
                message = (
                    f"{t_wav_name} (Timecode Start: {t_clip['timeline_start']}) "
                    "- Raison: Aucun audio de référence en face"
                )
                print(f"Skipped {message}")
                skipped_clips_log.append(message)
                continue

            overlap_start = max(t_clip["timeline_start"], ref_clip["timeline_start"])
            overlap_end = min(t_clip["timeline_end"], ref_clip["timeline_end"])
            overlap_len = overlap_end - overlap_start
            t_source_start = t_clip["source_start"] + (
                overlap_start - t_clip["timeline_start"]
            )
            r_source_start = ref_clip["source_start"] + (
                overlap_start - ref_clip["timeline_start"]
            )
            r_wav_name = ref_clip.get("physical_filename") or get_physical_filename(
                ref_clip["mob"]
            )
            t_wav_path = os.path.join(target_audio_dir, t_wav_name)
            r_wav_path = os.path.join(ref_audio_dir, r_wav_name)

            if not os.path.isfile(t_wav_path) or not os.path.isfile(r_wav_path):
                message = (
                    f"{t_wav_name} (Timecode Start: {t_clip['timeline_start']}) "
                    "- Raison: média cible ou référence introuvable"
                )
                print(f"Skipped {message}")
                skipped_clips_log.append(message)
                continue

            try:
                t_info = sf.info(t_wav_path)
                r_info = sf.info(r_wav_path)
                t_fs = t_info.samplerate
            except Exception as exc:
                message = f"{t_wav_name} - Raison: lecture impossible ({exc})"
                print(f"Skipped {message}")
                skipped_clips_log.append(message)
                continue
            if r_info.samplerate != t_fs:
                message = (
                    f"{t_wav_name} - Raison: fréquences d'échantillonnage "
                    f"incompatibles ({t_fs} Hz / {r_info.samplerate} Hz)"
                )
                print(f"Skipped {message}")
                skipped_clips_log.append(message)
                continue
            if overlap < t_info.samplerate * 0.5:
                message = (
                    f"{t_wav_name} - Raison: chevauchement inférieur à 0,5 seconde"
                )
                print(f"Skipped {message}")
                skipped_clips_log.append(message)
                continue

            r_audio_overlap = read_audio_chunk(
                r_wav_path, r_source_start, overlap_len
            )
            if r_audio_overlap is None:
                message = f"{t_wav_name} - Raison: lecture de référence impossible"
                print(f"Skipped {message}")
                skipped_clips_log.append(message)
                continue

            if is_target_ptx:
                if (
                    t_source_start < 0
                    or t_source_start + overlap_len > t_info.frames
                ):
                    message = (
                        f"{t_wav_name} - Raison: portion utilisée hors des bornes "
                        "du média cible"
                    )
                    print(f"Skipped {message}")
                    skipped_clips_log.append(message)
                    continue
                try:
                    t_data, read_fs = sf.read(
                        t_wav_path,
                        start=t_source_start,
                        frames=overlap_len,
                        always_2d=True,
                    )
                except Exception as exc:
                    message = (
                        f"{t_wav_name} - Raison: lecture de la portion cible "
                        f"impossible ({exc})"
                    )
                    print(f"Skipped {message}")
                    skipped_clips_log.append(message)
                    continue
                if read_fs != t_fs or len(t_data) != overlap_len:
                    message = (
                        f"{t_wav_name} - Raison: portion cible tronquée ou "
                        "fréquence incohérente"
                    )
                    print(f"Skipped {message}")
                    skipped_clips_log.append(message)
                    continue
            else:
                try:
                    t_data, read_fs = sf.read(t_wav_path, always_2d=True)
                except Exception as exc:
                    message = f"{t_wav_name} - Raison: lecture impossible ({exc})"
                    print(f"Skipped {message}")
                    skipped_clips_log.append(message)
                    continue
                if read_fs != t_fs:
                    raise RuntimeError("Target WAV sample rate changed while reading.")
                source_padded = np.zeros(len(t_data), dtype=np.float32)
                insert_start = t_source_start
                insert_end = t_source_start + overlap_len
                if insert_start < 0:
                    r_audio_overlap = r_audio_overlap[-insert_start:]
                    insert_start = 0
                if insert_end > len(source_padded):
                    excess = insert_end - len(source_padded)
                    r_audio_overlap = r_audio_overlap[:-excess]
                    insert_end = len(source_padded)
                if len(r_audio_overlap) > 0:
                    source_padded[insert_start:insert_end] = r_audio_overlap
                r_audio_overlap = source_padded

            t_mono = t_data[:, 0].astype(np.float32)
            aligned_mono, delays = dynamic_align(
                t_mono,
                r_audio_overlap,
                t_fs,
                max_delay_ms=max_shift_ms,
            )
            if t_data.shape[1] > 1:
                from scipy.interpolate import CubicSpline

                final_data = t_data.copy()
                final_data[:, 0] = aligned_mono
                num_samples = len(t_data)
                t_orig = np.arange(num_samples)
                t_new = t_orig + delays
                for channel in range(1, t_data.shape[1]):
                    spline = CubicSpline(t_orig, t_data[:, channel])
                    aligned_channel = spline(t_new)
                    aligned_channel[t_new < 0] = 0
                    aligned_channel[t_new > num_samples - 1] = 0
                    final_data[:, channel] = aligned_channel
            else:
                final_data = aligned_mono

            if is_target_ptx:
                out_wav_name, output_serial = _unique_ptx_wav_name(
                    t_wav_name, output_serial, reserved_names
                )
                out_wav_path = os.path.join(target_audio_dir, out_wav_name)
                descriptor, rendered_path = tempfile.mkstemp(
                    prefix=".ottoalign_",
                    suffix=".wav",
                    dir=target_audio_dir,
                )
                os.close(descriptor)
                try:
                    shutil.copyfile(t_wav_path, rendered_path)
                    with sf.SoundFile(rendered_path, mode="r+") as rendered:
                        rendered.seek(t_source_start)
                        rendered.write(final_data)
                    out_clip_name = _unique_aligned_clip_name(
                        t_clip["clip_name"], reserved_clip_names
                    )
                    result = target_f.relink_clip(
                        t_clip["track"],
                        t_clip["clip_name"],
                        t_clip["timeline_start"],
                        out_clip_name,
                        t_wav_path,
                        out_wav_path,
                        replacement_audio_path=rendered_path,
                    )
                finally:
                    try:
                        os.remove(rendered_path)
                    except FileNotFoundError:
                        pass
                created_audio_files.append(out_wav_path)
                clip_print_name = result["physical_filename"]
            else:
                out_wav_name = _aligned_aaf_filename(t_wav_name)
                out_wav_path = os.path.join(target_audio_dir, out_wav_name)
                if os.path.normcase(out_wav_path) == os.path.normcase(t_wav_path):
                    raise ValueError(
                        "AAF target media already uses the _ottoaligned suffix."
                    )
                if os.path.exists(out_wav_path):
                    raise FileExistsError(
                        f"AAF output WAV already exists: {out_wav_path}"
                    )
                sf.write(
                    out_wav_path,
                    final_data,
                    t_fs,
                    subtype=t_info.subtype,
                )
                created_audio_files.append(out_wav_path)
                mob = t_clip["mob"]
                if "_ottoaligned" not in mob.name.casefold():
                    if isinstance(mob, aaf2.mobs.MasterMob):
                        mob.name += "_ottoaligned"
                        for slot in mob.slots:
                            if (
                                isinstance(slot.segment, aaf2.components.SourceClip)
                                and slot.segment.mob
                            ):
                                if "_ottoaligned" not in slot.segment.mob.name.casefold():
                                    slot.segment.mob.name += "_ottoaligned"
                                if (
                                    slot.segment.mob.descriptor
                                    and "Locator" in slot.segment.mob.descriptor
                                ):
                                    for locator in slot.segment.mob.descriptor["Locator"]:
                                        old_url = locator["URLString"].value
                                        if "_ottoaligned" not in old_url.casefold():
                                            locator["URLString"].value = (
                                                _aligned_aaf_filename(old_url)
                                            )
                    elif isinstance(mob, aaf2.mobs.SourceMob):
                        mob.name += "_ottoaligned"
                        if mob.descriptor and "Locator" in mob.descriptor:
                            for locator in mob.descriptor["Locator"]:
                                old_url = locator["URLString"].value
                                if "_ottoaligned" not in old_url.casefold():
                                    locator["URLString"].value = (
                                        _aligned_aaf_filename(old_url)
                                    )
                clip_print_name = mob.name

            shift_ms = float(np.mean(delays)) * 1000 / t_fs
            print(f"Dynamically aligned {clip_print_name}")
            aligned_clips_log.append(
                f"{clip_print_name} (Décalage corrigé: {shift_ms:.3f} ms)"
            )

        if is_target_ptx:
            target_f.save(out_aaf_path)
        else:
            target_f.close()
            target_f = None
    except Exception:
        for created_path in reversed(created_audio_files):
            try:
                os.remove(created_path)
            except FileNotFoundError:
                pass
        try:
            os.remove(out_aaf_path)
        except FileNotFoundError:
            pass
        raise
    finally:
        if ref_f is not None and not is_ref_ptx:
            ref_f.close()
        if target_f is not None and not is_target_ptx:
            target_f.close()

    report_path = os.path.join(target_audio_dir, "OttoAlign_Report.txt")
    try:
        with open(report_path, "w", encoding="utf-8") as report:
            report.write("Rapport OttoAlign\n")
            report.write("=================\n\n")
            report.write(
                f"Clips alignés avec succès ({len(aligned_clips_log)} clips):\n"
            )
            for entry in aligned_clips_log:
                report.write(f"- {entry}\n")
            report.write(f"\nClips ignorés ({len(skipped_clips_log)} clips):\n")
            for entry in skipped_clips_log:
                report.write(f"- {entry}\n")
    except OSError as exc:
        print(f"Erreur création rapport: {exc}")

    print(
        "Alignment complete! Successfully aligned "
        f"{len(aligned_clips_log)} clips."
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("ref_aaf")
    parser.add_argument("ref_audio_dir")
    parser.add_argument("target_aaf")
    parser.add_argument("target_audio_dir")
    parser.add_argument("out_aaf")
    args = parser.parse_args()
    
    align_aafs(args.ref_aaf, args.ref_audio_dir, args.target_aaf, args.target_audio_dir, args.out_aaf)
