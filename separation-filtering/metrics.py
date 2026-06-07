"""
canary/metrics.py
------------------
Audio quality metrics:
  - SI-SNR  (Scale-Invariant Signal-to-Noise Ratio)
  - SI-SDR  (Scale-Invariant Signal-to-Distortion Ratio)  [same formula]
  - SNR     (classical, dB)
  - RMS     (root mean square level)

All functions accept numpy arrays (float32/64), 1-D.

Reference:
  Le Roux et al. (2018) "SDR – Half-baked or Well Done?"
  https://arxiv.org/abs/1811.02508
"""

from __future__ import annotations

import numpy as np
from typing import Optional


# ---------------------------------------------------------------------------
def si_snr(estimate: np.ndarray, reference: np.ndarray) -> float:
    """
    Compute Scale-Invariant SNR (dB) between estimate and reference.

    SI-SNR = 10 * log10( ||s_target||^2 / ||e_noise||^2 )

    where s_target = <estimate, reference> / ||reference||^2 * reference
          e_noise  = estimate - s_target

    Parameters
    ----------
    estimate  : np.ndarray  shape (N,)  – separated speaker stream
    reference : np.ndarray  shape (N,)  – clean reference (if available)

    Returns
    -------
    float  SI-SNR in dB  (higher is better)
    """
    if len(estimate) != len(reference):
        min_len = min(len(estimate), len(reference))
        estimate = estimate[:min_len]
        reference = reference[:min_len]

    # Zero-mean
    e = estimate - estimate.mean()
    r = reference - reference.mean()

    # Scale-invariant target
    dot = np.dot(e, r)
    ref_pow = np.dot(r, r) + 1e-8
    s_target = (dot / ref_pow) * r

    e_noise = e - s_target

    target_pow = np.dot(s_target, s_target) + 1e-8
    noise_pow = np.dot(e_noise, e_noise) + 1e-8

    return float(10.0 * np.log10(target_pow / noise_pow))


# ---------------------------------------------------------------------------
def snr(estimate: np.ndarray, reference: np.ndarray) -> float:
    """Classical Signal-to-Noise Ratio in dB."""
    if len(estimate) != len(reference):
        min_len = min(len(estimate), len(reference))
        estimate = estimate[:min_len]
        reference = reference[:min_len]

    noise = estimate - reference
    signal_pow = np.dot(reference, reference) + 1e-8
    noise_pow = np.dot(noise, noise) + 1e-8
    return float(10.0 * np.log10(signal_pow / noise_pow))


# ---------------------------------------------------------------------------
def rms_db(audio: np.ndarray) -> float:
    """RMS level in dBFS."""
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2) + 1e-12)
    return float(20.0 * np.log10(rms))


# ---------------------------------------------------------------------------
def self_si_snr(separated_streams: list[np.ndarray]) -> list[float]:
    """
    Self-evaluated SI-SNR: when no reference is available, we compute
    SI-SNR of each stream against the *sum* of the other streams
    (inter-speaker leakage measure). Higher = less leakage = better.

    Returns list of SI-SNR values (one per stream).
    """
    scores = []
    for i, stream in enumerate(separated_streams):
        others = [separated_streams[j] for j in range(len(separated_streams)) if j != i]
        if not others:
            scores.append(float("inf"))
            continue
        # Reconstruct what the "noise" is: sum of other streams
        leakage = np.sum(np.stack(others, axis=0), axis=0)
        # We treat stream as "signal" and leakage as "noise"
        # This is a measure of cross-talk rejection
        sig_pow = float(np.dot(stream, stream)) + 1e-8
        noise_pow = float(np.dot(leakage, leakage)) + 1e-8
        scores.append(float(10.0 * np.log10(sig_pow / noise_pow)))
    return scores


# ---------------------------------------------------------------------------
def denoising_gain(noisy: np.ndarray, denoised: np.ndarray) -> dict:
    """
    Report noise reduction metrics:
      - RMS change (dB)
      - High-frequency energy reduction (proxy for noise floor)

    Returns dict with keys: rms_noisy_db, rms_denoised_db, hf_reduction_db
    """
    sr_proxy = 16000  # assume 16kHz
    rms_n = rms_db(noisy)
    rms_d = rms_db(denoised)

    # HF energy (>4kHz at 16kHz)
    spec_n = np.abs(np.fft.rfft(noisy.astype(np.float64), n=2048))
    spec_d = np.abs(np.fft.rfft(denoised.astype(np.float64), n=2048))
    hf_start = 512  # bin index for ~4kHz at 16kHz with n=2048
    hf_n = float(np.mean(spec_n[hf_start:] ** 2)) + 1e-12
    hf_d = float(np.mean(spec_d[hf_start:] ** 2)) + 1e-12
    hf_reduction = float(10.0 * np.log10(hf_n / hf_d))

    return {
        "rms_noisy_db": round(rms_n, 2),
        "rms_denoised_db": round(rms_d, 2),
        "hf_reduction_db": round(hf_reduction, 2),
    }
