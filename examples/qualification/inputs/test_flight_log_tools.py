"""Regression check for flight_log_tools; it currently fails."""

from flight_log_tools import apogee

rows = [(i * 0.1, 100.0 - 2.0 * (i * 0.1 - 5.0) ** 2) for i in range(101)]
t, h = apogee(rows)
# A centred 5-sample mean lowers a parabola's peak by 2 * mean(k^2) * dt^2 = 0.04 m.
assert abs(t - 5.0) < 1e-9, f"apogee time {t}, expected 5.0"
assert abs(h - 99.96) < 1e-9, f"apogee altitude {h}, expected 99.96"
print("ok")
