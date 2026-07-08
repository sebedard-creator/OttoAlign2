import numpy as np
import scipy.signal
from scipy.interpolate import CubicSpline
import logging

logger = logging.getLogger(__name__)

def gcc_phat(sig, refsig, fs=1, max_tau=None, interp=16):
    """
    Generalized Cross Correlation - Phase Transform (GCC-PHAT).
    Estimates the delay between sig and refsig.
    Returns delay in samples. Positive delay means `sig` is delayed relative to `refsig`.
    """
    n = sig.shape[0] + refsig.shape[0]
    
    SIG = np.fft.rfft(sig, n=n)
    REFSIG = np.fft.rfft(refsig, n=n)
    
    R = SIG * np.conj(REFSIG)
    
    cc = np.fft.irfft(R / (np.abs(R) + 1e-15), n=(interp * n))
    
    max_shift = int(interp * n / 2)
    if max_tau:
        max_shift = np.minimum(int(interp * fs * max_tau), max_shift)
        
    cc = np.concatenate((cc[-max_shift:], cc[:max_shift+1]))
    
    shift = np.argmax(np.abs(cc)) - max_shift
    
    return shift / float(interp)

def dynamic_align(target, source, fs, window_ms=100, hop_ms=25, max_delay_ms=20, energy_thresh=1e-5):
    """
    Align target to source using dynamic delay tracking.
    """
    logger.info(f"Starting dynamic alignment. Source len: {len(source)}, Target len: {len(target)}")
    
    window_samples = int(fs * window_ms / 1000)
    hop_samples = int(fs * hop_ms / 1000)
    
    num_samples = len(target)
    
    delays = []
    times = []
    
    for i in range(0, num_samples - window_samples, hop_samples):
        s_win = source[i:i+window_samples]
        t_win = target[i:i+window_samples]
        
        # Calculate energy for Voice Activity Detection
        energy = np.mean(s_win**2)
        
        if energy > energy_thresh:
            # If target is delayed, gcc_phat returns negative (depending on argument order)
            # Let's test the sign: if target = source(t-D), then sig=t_win, refsig=s_win.
            delay = gcc_phat(t_win, s_win, fs=fs, max_tau=max_delay_ms/1000.0)
            delays.append(delay)
        else:
            if len(delays) > 0:
                delays.append(delays[-1]) # hold last delay
            else:
                delays.append(0.0)
        times.append(i + window_samples//2)
        
    if not delays:
        return target # No signal detected above threshold
        
    delays = np.array(delays)
    
    # Median filter to smooth the delay curve (e.g. 500ms window)
    kernel_size = int((500 / hop_ms)) | 1 # ensure odd
    if len(delays) > kernel_size:
        smoothed_delays = scipy.signal.medfilt(delays, kernel_size=kernel_size)
    else:
        smoothed_delays = delays
        
    # Interpolate delay curve for every sample
    times_samples = np.array(times)
    sample_indices = np.arange(num_samples)
    
    # Pad at ends to cover the whole array
    times_padded = np.concatenate(([0], times_samples, [num_samples]))
    delays_padded = np.concatenate(([smoothed_delays[0]], smoothed_delays, [smoothed_delays[-1]]))
    
    per_sample_delays = np.interp(sample_indices, times_padded, delays_padded)
    
    # Apply variable delay line using CubicSpline (fractional delay)
    t_orig = np.arange(num_samples)
    # If target is delayed by +D samples relative to source, gcc_phat gives +D.
    # We want aligned_target[t] = target[t + D] to shift it back.
    t_new = t_orig + per_sample_delays 
    
    cs = CubicSpline(t_orig, target)
    aligned_target = cs(t_new)
    
    # Zero out boundaries where we extrapolated
    aligned_target[t_new < 0] = 0
    aligned_target[t_new > num_samples - 1] = 0
    
    return aligned_target, per_sample_delays
