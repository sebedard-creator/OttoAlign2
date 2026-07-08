import aaf2
import numpy as np
import soundfile as sf
from scipy import signal
import os
import shutil

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

def calculate_phase_shift(ref_audio, target_audio, max_shift_samples=4800):
    """
    Calculates the phase shift (in samples) required to align target_audio to ref_audio.
    Positive shift means target_audio needs to be shifted right (it is early).
    Negative shift means target_audio needs to be shifted left (it is late).
    max_shift_samples restricts the correlation to +/- max_shift_samples (e.g. 100ms at 48kHz).
    """
    # Normalize
    ref_norm = ref_audio / (np.max(np.abs(ref_audio)) + 1e-9)
    target_norm = target_audio / (np.max(np.abs(target_audio)) + 1e-9)
    
    # Correlate
    correlation = signal.correlate(ref_norm, target_norm, mode='full')
    lags = signal.correlation_lags(len(ref_norm), len(target_norm), mode='full')
    
    # Restrict search window
    valid_indices = np.where(np.abs(lags) <= max_shift_samples)[0]
    if len(valid_indices) == 0:
        return 0
        
    windowed_corr = correlation[valid_indices]
    windowed_lags = lags[valid_indices]
    
    best_lag_idx = np.argmax(windowed_corr)
    shift = windowed_lags[best_lag_idx]
    
    return shift

def align_aafs(ref_aaf_path, ref_audio_dir, target_aaf_path, target_audio_dir, out_aaf_path, max_shift_ms=100):
    print(f"Aligning {target_aaf_path} against {ref_aaf_path}...")
    
    shutil.copy(target_aaf_path, out_aaf_path)
    
    ref_f = aaf2.open(ref_aaf_path, 'r')
    
    with aaf2.open(out_aaf_path, 'rw') as target_f:
        # Find all sequences in reference
        ref_clips = []
        for mob in ref_f.content.mobs:
            if isinstance(mob, aaf2.mobs.CompositionMob):
                for slot in mob.slots:
                    if isinstance(slot.segment, aaf2.components.Sequence):
                        ref_clips.extend(get_clip_absolute_times(slot.segment))
                
        if not ref_clips:
            print("Could not find reference clips.")
            ref_f.close()
            return
        
        # Find all sequences in target
        target_clips = []
        for mob in target_f.content.mobs:
            if isinstance(mob, aaf2.mobs.CompositionMob):
                for slot in mob.slots:
                    if isinstance(slot.segment, aaf2.components.Sequence):
                        target_clips.extend(get_clip_absolute_times(slot.segment))
                
        if not target_clips:
            print("Could not find target clips.")
            ref_f.close()
            return
        
        from dsp_core import dynamic_align
        
        aligned_count = 0
        
        for t_clip in target_clips:
            ref_clip, overlap = find_overlapping_reference(t_clip, ref_clips)
            if not ref_clip:
                continue
                
            overlap_start = max(t_clip['timeline_start'], ref_clip['timeline_start'])
            overlap_end = min(t_clip['timeline_end'], ref_clip['timeline_end'])
            overlap_len = overlap_end - overlap_start
            
            t_source_start = t_clip['source_start'] + (overlap_start - t_clip['timeline_start'])
            r_source_start = ref_clip['source_start'] + (overlap_start - ref_clip['timeline_start'])
            
            t_wav_name = get_physical_filename(t_clip['mob'])
            r_wav_name = get_physical_filename(ref_clip['mob'])
            
            t_wav_path = os.path.join(target_audio_dir, t_wav_name)
            r_wav_path = os.path.join(ref_audio_dir, r_wav_name)
            
            if not os.path.exists(t_wav_path) or not os.path.exists(r_wav_path):
                continue
                
            try:
                t_info = sf.info(t_wav_path)
            except Exception as e:
                print(f"Error reading target info {t_wav_path}: {e}")
                continue
                
            if overlap < t_info.samplerate * 0.5:
                continue
                
            # Read full target audio
            try:
                t_data, t_fs = sf.read(t_wav_path)
            except Exception as e:
                print(f"Error reading target {t_wav_path}: {e}")
                continue
                
            is_stereo = len(t_data.shape) > 1
            if is_stereo:
                t_mono = t_data[:, 0].astype(np.float32)
            else:
                t_mono = t_data.astype(np.float32)
                
            # Read the overlapping reference chunk
            r_audio_overlap = read_audio_chunk(r_wav_path, r_source_start, overlap_len)
            if r_audio_overlap is None:
                continue
                
            # Pad reference to match full target length
            source_padded = np.zeros_like(t_mono)
            
            insert_start = t_source_start
            insert_end = t_source_start + overlap_len
            
            # Ensure bounds
            if insert_start < 0:
                r_audio_overlap = r_audio_overlap[-insert_start:]
                insert_start = 0
            if insert_end > len(source_padded):
                excess = insert_end - len(source_padded)
                r_audio_overlap = r_audio_overlap[:-excess]
                insert_end = len(source_padded)
                
            if len(r_audio_overlap) > 0:
                source_padded[insert_start:insert_end] = r_audio_overlap
                
            # Run dynamic alignment
            aligned_mono, delays = dynamic_align(t_mono, source_padded, t_fs)
            
            # Reconstruct audio
            if is_stereo:
                final_data = t_data.copy()
                final_data[:, 0] = aligned_mono
                
                # Apply the exact same delay curve to the second channel to preserve phase
                from scipy.interpolate import CubicSpline
                num_samples = len(t_data)
                t_orig = np.arange(num_samples)
                t_new = t_orig + delays
                cs_right = CubicSpline(t_orig, t_data[:, 1])
                aligned_right = cs_right(t_new)
                aligned_right[t_new < 0] = 0
                aligned_right[t_new > num_samples - 1] = 0
                
                final_data[:, 1] = aligned_right
            else:
                final_data = aligned_mono
                
            # Write new WAV file
            if '_ottoaligned' in t_wav_name:
                out_wav_name = t_wav_name
            else:
                out_wav_name = t_wav_name.replace('.wav', '_ottoaligned.wav')
                
            out_wav_path = os.path.join(target_audio_dir, out_wav_name)
            
            t_info = sf.info(t_wav_path)
            sf.write(out_wav_path, final_data, t_fs, subtype=t_info.subtype)
            
            # Update AAF properties (non-destructive to FAT chain)
            mob = t_clip['mob']
            if '_ottoaligned' not in mob.name:
                if isinstance(mob, aaf2.mobs.MasterMob):
                    mob.name = mob.name + '_ottoaligned'
                    for slot in mob.slots:
                        if isinstance(slot.segment, aaf2.components.SourceClip) and slot.segment.mob:
                            if '_ottoaligned' not in slot.segment.mob.name:
                                slot.segment.mob.name = slot.segment.mob.name + '_ottoaligned'
                            if slot.segment.mob.descriptor and 'Locator' in slot.segment.mob.descriptor:
                                for loc in slot.segment.mob.descriptor['Locator']:
                                    old_url = loc['URLString'].value
                                    if '_ottoaligned' not in old_url:
                                        loc['URLString'].value = old_url.replace('.wav', '_ottoaligned.wav')
                elif isinstance(mob, aaf2.mobs.SourceMob):
                    mob.name = mob.name + '_ottoaligned'
                    if mob.descriptor and 'Locator' in mob.descriptor:
                        for loc in mob.descriptor['Locator']:
                            old_url = loc['URLString'].value
                            if '_ottoaligned' not in old_url:
                                loc['URLString'].value = old_url.replace('.wav', '_ottoaligned.wav')
            
            aligned_count += 1
            print(f"Dynamically aligned {mob.name}")
                
        ref_f.close()
        print(f"Successfully aligned {aligned_count} clips. Output saved to {out_aaf_path}")

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
