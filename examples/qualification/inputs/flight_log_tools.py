"""Post-flight helpers for barometric altitude logs."""


def smooth(values, window=5):
    """Centred moving average over an odd number of samples.

    Near the ends the average uses only the samples that exist inside the window.
    """
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half)
        chunk = values[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def apogee(rows, window=5):
    """Return (time_s, altitude_m) at the maximum of the smoothed altitude.

    rows are (time_s, altitude_m) samples in time order.
    """
    times = [t for t, _ in rows]
    altitudes = smooth([a for _, a in rows], window)
    k = max(range(len(altitudes)), key=altitudes.__getitem__)
    return times[k], altitudes[k]
