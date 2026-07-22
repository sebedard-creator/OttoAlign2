import numpy as np
import scipy.signal
from scipy.interpolate import CubicSpline
import logging

logger = logging.getLogger(__name__)

def gcc_phat(sig, refsig, fs=1, max_tau=None, interp=16, return_polarity=False, return_snr=False, prior_delay_ms=None, prior_sigma_ms=2.0):
    """
    Generalized Cross Correlation - Phase Transform (GCC-PHAT).
    Estimates the delay between sig and refsig.
    Returns delay in samples. Positive delay means `sig` is delayed relative to `refsig`.
    If return_polarity is True, returns (delay, is_inverted) where is_inverted is True
    if the cross-correlation peak is negative (meaning the signal is phase-inverted).
    """
    n = sig.shape[0] + refsig.shape[0]
    
    SIG = np.fft.rfft(sig, n=n)
    REFSIG = np.fft.rfft(refsig, n=n)
    
    # Frequency domain bandpass (80Hz - 8000Hz) to ignore hum and hiss
    freqs = np.fft.rfftfreq(n, d=1.0/fs)
    mask = (freqs >= 80.0) & (freqs <= 8000.0)
    SIG *= mask
    REFSIG *= mask
    
    R = SIG * np.conj(REFSIG)
    
    # Standard Cross-Correlation (no PHAT weighting) prevents high-frequency hiss from dominating the peak
    cc = np.fft.irfft(R, n=(interp * n))
    
    max_shift = int(interp * n / 2)
    if max_tau:
        max_shift = np.minimum(int(interp * fs * max_tau), max_shift)
        
    cc = np.concatenate((cc[-max_shift:], cc[:max_shift+1]))
    
    if prior_delay_ms is not None:
        shifts_ms = np.arange(-max_shift, max_shift + 1) * 1000.0 / (interp * fs)
        prior = np.exp(-0.5 * ((shifts_ms - prior_delay_ms) / prior_sigma_ms)**2)
        cc = cc * prior
        
    idx = np.argmax(np.abs(cc))
    shift = idx - max_shift
    delay = shift / float(interp)
    
    result = [delay]
    if return_polarity:
        result.append(bool(cc[idx] < 0))
    if return_snr:
        rms = np.sqrt(np.mean(cc**2)) + 1e-15
        snr = np.abs(cc[idx]) / rms
        result.append(snr)
        
    if len(result) == 1:
        return result[0]
    return tuple(result)

def dynamic_align(target, source, fs, window_ms=100, hop_ms=25, max_delay_ms=20, energy_thresh=1e-5, anchor_hint=None):
    """
    Align target to source using a rolling anchored dynamic delay tracking.
    This prevents autotune artifacts by strictly bounding local searches
    around a Gaussian prior centered on the previous delay frame.
    `anchor_hint` can be provided as (global_delay_samples, is_inverted) to enforce
    phase coherence across fragmented clips.
    """
    import scipy.ndimage
    logger.info(f"Starting dynamic alignment. Source len: {len(source)}, Target len: {len(target)}")
    
    if anchor_hint is not None:
        global_delay, is_inverted = anchor_hint
        logger.info(f"Using provided anchor hint: {global_delay} samples, inv={is_inverted}")
        
        # CRITICAL FIX for fragmented clips phasing:
        # If an anchor hint is provided (meaning this clip is part of a grouped physical file),
        # we MUST apply a constant, static shift. Dynamic alignment on independent chunks 
        # will always diverge at their boundaries due to smoothing edge-effects, causing 
        # phase discontinuities at crossfades.
        # We use an integer shift to avoid CubicSpline sub-sample phasing artifacts on dialog.
        num_samples = len(target)
        shift = int(np.round(global_delay))
        aligned_target = np.zeros_like(target)
        
        if shift > 0:
            # Target is delayed (happens late), shift left
            aligned_target[:-shift] = target[shift:]
        elif shift < 0:
            # Target is early, shift right
            aligned_target[-shift:] = target[:shift]
        else:
            aligned_target = target.copy()
            
        if is_inverted:
            aligned_target = -aligned_target
            
        return aligned_target, np.full(num_samples, global_delay, dtype=np.float64), is_inverted
    else:
        # Calculate Global Anchor Delay & Polarity
        global_delay, is_inverted = gcc_phat(target, source, fs=fs, max_tau=max_delay_ms/1000.0, return_polarity=True)
    
    if is_inverted:
        logger.info("Phase inversion detected! Polarity will be flipped.")
    
    window_samples = int(fs * window_ms / 1000)
    hop_samples = int(fs * hop_ms / 1000)
    
    num_samples = len(target)
    
    delays = []
    high_snr_delays = []
    times = []
    
    current_prior_ms = (global_delay * 1000.0) / fs
    
    for i in range(0, num_samples - window_samples, hop_samples):
        s_win = source[i:i+window_samples]
        t_win = target[i:i+window_samples]
        
        energy = np.mean(s_win**2)
        
        if energy > energy_thresh:
            local_delay_samples, local_snr = gcc_phat(
                t_win, s_win, fs=fs, max_tau=max_delay_ms/1000.0, 
                prior_delay_ms=current_prior_ms, prior_sigma_ms=2.0,
                return_snr=True
            )
            delays.append(local_delay_samples)
            if local_snr >= 8.0:
                high_snr_delays.append(local_delay_samples)
            
            # Update rolling anchor with light smoothing
            local_delay_ms = (local_delay_samples * 1000.0) / fs
            current_prior_ms = 0.5 * current_prior_ms + 0.5 * local_delay_ms
        else:
            if len(delays) > 0:
                delays.append(delays[-1])
            else:
                delays.append(global_delay)
        times.append(i + window_samples//2)
        
    eval_delays = high_snr_delays if len(high_snr_delays) >= 3 else delays
    if not eval_delays or np.std(eval_delays) < 2.0:
        # Fallback to pure static alignment if high-confidence delay curve has negligible variance,
        # or if the chunking failed. This avoids CubicSpline phase smearing.
        shift = int(np.round(global_delay))
        aligned_target = np.zeros_like(target)
        
        if shift > 0:
            aligned_target[:-shift] = target[shift:]
        elif shift < 0:
            aligned_target[-shift:] = target[:shift]
        else:
            aligned_target = target.copy()
            
        if is_inverted:
            aligned_target = -aligned_target
        return aligned_target, np.full(num_samples, global_delay, dtype=np.float64), is_inverted
        
    delays = np.array(delays)
    
    # Heavy smoothing (1 second window = 1000 / hop_ms frames)
    smooth_frames = int(1000 / hop_ms)
    smooth_frames = min(smooth_frames, max(1, len(delays)))
    smoothed_delays = scipy.ndimage.uniform_filter1d(delays, size=smooth_frames)
    
    # Interpolate delay curve for every sample
    times_samples = np.array(times)
    sample_indices = np.arange(num_samples)
    
    # Pad at ends to cover the whole array
    times_padded = np.concatenate(([0], times_samples, [num_samples]))
    delays_padded = np.concatenate(([smoothed_delays[0]], smoothed_delays, [smoothed_delays[-1]]))
    
    per_sample_delays = np.interp(sample_indices, times_padded, delays_padded)
    
    # Apply variable delay line using CubicSpline (fractional delay)
    t_orig = np.arange(num_samples)
    t_new = t_orig + per_sample_delays 
    
    cs = CubicSpline(t_orig, target)
    aligned_target = cs(t_new)
    
    # Zero out boundaries where we extrapolated
    aligned_target[t_new < 0] = 0
    aligned_target[t_new > num_samples - 1] = 0
    
    # Apply polarity correction if phase is inverted
    if is_inverted:
        aligned_target = -aligned_target
        
    return aligned_target, per_sample_delays, is_inverted
