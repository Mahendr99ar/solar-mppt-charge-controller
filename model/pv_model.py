"""
Single-diode model of a 50 W, 36-cell solar panel.

    I = Iph - I0 * (exp((V + I*Rs) / (Ns*n*Vt)) - 1) - (V + I*Rs) / Rsh

Iph scales with irradiance and temperature; I0 is set so the model hits the
datasheet open-circuit voltage at STC (1000 W/m^2, 25 C).

Used by the design script, the MPPT simulation and (ported to JavaScript) the website.
"""
import math

# ---- Datasheet values of a typical 50 W, 12 V-class panel (STC) ----
VOC_STC = 21.6      # V
ISC_STC = 3.10      # A
NS = 36             # cells in series
N_IDEAL = 1.3       # diode ideality factor
RS = 0.25           # ohm, series resistance
RSH = 250.0         # ohm, shunt resistance
KI = 0.0006         # 1/C, Isc temperature coefficient (+0.06 %/C)
KV = -0.0033        # 1/C, Voc temperature coefficient (-0.33 %/C)

K_BOLTZ = 1.380649e-23
Q_E = 1.602176634e-19


def thermal_voltage(temp_c):
    return K_BOLTZ * (temp_c + 273.15) / Q_E


def panel_params(irradiance, temp_c):
    """Photo-current and saturation current at given conditions."""
    g = irradiance / 1000.0
    dt = temp_c - 25.0
    iph = ISC_STC * g * (1 + KI * dt)
    voc = VOC_STC * (1 + KV * dt) + NS * N_IDEAL * thermal_voltage(temp_c) * math.log(max(g, 1e-6))
    a = NS * N_IDEAL * thermal_voltage(temp_c)
    i0 = iph / (math.exp(voc / a) - 1)
    return iph, i0, a


def current_at(v, irradiance, temp_c):
    """Panel current at terminal voltage v (Newton-Raphson on the implicit equation)."""
    if irradiance <= 0:
        return 0.0
    iph, i0, a = panel_params(irradiance, temp_c)
    i = iph
    for _ in range(50):
        e = math.exp((v + i * RS) / a)
        f = iph - i0 * (e - 1) - (v + i * RS) / RSH - i
        df = -i0 * e * RS / a - RS / RSH - 1
        step = f / df
        i -= step
        if abs(step) < 1e-9:
            break
    return max(i, 0.0)


def iv_curve(irradiance, temp_c, points=200):
    _, _, _ = panel_params(irradiance, temp_c)
    vmax = VOC_STC * 1.15
    vs = [vmax * k / (points - 1) for k in range(points)]
    return [(v, current_at(v, irradiance, temp_c)) for v in vs]


def max_power_point(irradiance, temp_c):
    """Golden-section search for the maximum power point."""
    lo, hi = 0.0, VOC_STC * 1.15
    gr = (math.sqrt(5) - 1) / 2
    for _ in range(80):
        m1 = hi - gr * (hi - lo)
        m2 = lo + gr * (hi - lo)
        if m1 * current_at(m1, irradiance, temp_c) > m2 * current_at(m2, irradiance, temp_c):
            hi = m2
        else:
            lo = m1
    v = (lo + hi) / 2
    i = current_at(v, irradiance, temp_c)
    return v, i, v * i


if __name__ == "__main__":
    for g, t in [(1000, 25), (800, 35), (500, 30), (200, 25)]:
        v, i, p = max_power_point(g, t)
        print(f"G = {g:4d} W/m^2, T = {t} C ->  Vmp = {v:5.2f} V, Imp = {i:4.2f} A, Pmp = {p:5.1f} W")
