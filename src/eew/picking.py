"""Pick automático de la llegada P en una componente vertical.

Es deliberadamente simple y auditable: primera superación de un umbral
STA/LTA sobre la señal filtrada, refinada con el criterio AIC. Cada pick lleva
su relación señal/ruido; una pick sin SNR suficiente no se entrega. Un pick
automático sin revisión humana tiene incertidumbre de décimas de segundo en
señales claras y puede ser un falso en ruido; por eso la localización rechaza
las picks que no encajan con las demás, y no se asume que cada pick es buena.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from obspy import Trace  # type: ignore[import-untyped]
from obspy.signal.trigger import aic_simple, classic_sta_lta  # type: ignore[import-untyped]


@dataclass(frozen=True)
class PickSettings:
    low_hz: float = 1.0
    high_hz: float = 10.0
    corners: int = 2
    sta_seconds: float = 0.5
    lta_seconds: float = 6.0
    threshold: float = 3.5
    aic_before_seconds: float = 3.0
    aic_after_seconds: float = 0.8
    snr_noise_seconds: float = 4.0
    snr_signal_seconds: float = 2.0
    minimum_snr: float = 3.0
    episode_gap_seconds: float = 3.0


@dataclass(frozen=True)
class OnsetPick:
    time: float  # segundos Unix
    snr: float
    sta_lta_ratio: float


def pick_p_onset(
    trace: Trace,
    search_start: float,
    search_end: float,
    settings: PickSettings = PickSettings(),
) -> OnsetPick | None:
    """Primera llegada P en ``[search_start, search_end]`` (segundos Unix).

    ``None`` si no hay una superación clara del umbral, si la traza tiene
    huecos o valores no finitos en la ventana, o si la SNR no alcanza.
    """

    rate = float(trace.stats.sampling_rate)
    if not np.isfinite(rate) or rate <= 0:
        return None
    data = np.asarray(trace.data, dtype=np.float64)
    if data.size == 0 or not np.isfinite(data).all():
        return None
    start = float(trace.stats.starttime.timestamp)
    lead = settings.lta_seconds * 1.5
    first = max(0, int((search_start - lead - start) * rate))
    last = min(data.size, int((search_end + 1.0 - start) * rate))
    if last - first < int((settings.lta_seconds + 2.0) * rate):
        return None

    work = Trace(data=data[first:last].copy())
    work.stats.sampling_rate = rate
    work.detrend("demean")
    work.detrend("linear")
    nyquist_safe = rate * 0.45
    work.filter(
        "bandpass",
        freqmin=settings.low_hz,
        freqmax=min(settings.high_hz, nyquist_safe),
        corners=settings.corners,
        zerophase=True,
    )
    filtered = np.asarray(work.data, dtype=np.float64)
    nsta = max(1, round(settings.sta_seconds * rate))
    nlta = max(nsta + 1, round(settings.lta_seconds * rate))
    ratio = classic_sta_lta(filtered, nsta, nlta)
    origin = start + first / rate
    window_first = max(nlta, int(round((search_start - origin) * rate)))
    window_last = min(filtered.size, int(round((search_end - origin) * rate)))
    if window_last <= window_first:
        return None
    above = np.flatnonzero(ratio[window_first:window_last] >= settings.threshold)
    if above.size == 0:
        return None
    # Cada episodio sobre el umbral se evalúa por separado: un transitorio de
    # ruido anterior a la llegada real no debe impedir encontrarla. Gana el
    # primer episodio cuya señal supera el ruido, no el primero a secas.
    episode_starts = [int(above[0])] + [
        int(current) for previous, current in zip(above[:-1], above[1:], strict=True)
        if current - previous > int(settings.episode_gap_seconds * rate)
    ]
    for relative in episode_starts:
        crossing = window_first + relative
        aic_start = max(0, crossing - int(settings.aic_before_seconds * rate))
        aic_end = min(filtered.size, crossing + int(settings.aic_after_seconds * rate))
        if aic_end - aic_start < int(0.5 * rate):
            continue
        aic = aic_simple(filtered[aic_start:aic_end])
        onset_index = aic_start + int(np.argmin(aic))
        # Un mínimo en el borde de la ventana no es un cambio de régimen: es el borde.
        if onset_index - aic_start < 2 or aic_end - onset_index < 2:
            continue
        noise_end = onset_index
        noise_start = max(0, noise_end - int(settings.snr_noise_seconds * rate))
        signal_end = min(filtered.size, onset_index + int(settings.snr_signal_seconds * rate))
        if noise_end - noise_start < int(1.0 * rate) or signal_end - onset_index < int(0.5 * rate):
            continue
        noise_rms = float(np.sqrt(np.mean(filtered[noise_start:noise_end] ** 2)))
        signal_rms = float(np.sqrt(np.mean(filtered[onset_index:signal_end] ** 2)))
        if noise_rms <= 0 or not np.isfinite(noise_rms) or not np.isfinite(signal_rms):
            continue
        snr = signal_rms / noise_rms
        if snr < settings.minimum_snr:
            continue
        return OnsetPick(time=origin + onset_index / rate, snr=snr, sta_lta_ratio=float(ratio[crossing]))
    return None
