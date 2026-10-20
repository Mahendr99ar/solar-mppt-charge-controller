"""
Perturb & Observe MPPT simulation on the single-diode panel model.

The buck converter is modelled with its averaged steady-state relation
Vpv = Vbat / D (battery holds the output voltage), so changing the duty cycle
moves the panel's operating voltage. Each control step is 50 ms, the same rate
as the Arduino firmware.

Compares three cases over a changing-weather profile:
  1. P&O MPPT (this project)
  2. Panel connected directly to the battery (cheap PWM controller)
  3. Ideal: always at the true maximum power point

Run:  python3 simulation/mppt_sim.py      (writes PNG plots and results.txt)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))
import pv_model as pv  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
V_BAT = 12.8                 # battery voltage (V)
DT = 0.05                    # control period (s)
STEP_D = 0.005               # duty-cycle perturbation size
D_MIN, D_MAX = 0.40, 0.95
T_END = 60.0                 # seconds simulated


def weather(t):
    """Irradiance (W/m^2) and cell temperature (C): clear sky, cloud, partial recovery."""
    if t < 15:
        g = 1000
    elif t < 20:
        g = 1000 - 600 * (t - 15) / 5        # cloud moves in
    elif t < 35:
        g = 400
    elif t < 40:
        g = 400 + 400 * (t - 35) / 5         # cloud clears
    else:
        g = 800
    temp = 25 + 15 * min(t, 40) / 40         # panel warms up
    return g, temp


def run():
    steps = int(T_END / DT)
    d = 0.90                                 # start far from the MPP on purpose
    direction = -1                           # -1: lower D (raise panel V), +1: raise D
    p_prev = 0.0
    log = {k: [] for k in ("t", "g", "v", "p", "p_ideal", "p_direct", "d")}

    for k in range(steps):
        t = k * DT
        g, temp = weather(t)
        v = V_BAT / d
        i = pv.current_at(v, g, temp)
        p = v * i

        # ---- Perturb & Observe ----
        # Keep stepping the duty cycle the same way while power rises;
        # reverse when power falls. It never stops, so it can't get stuck.
        if p < p_prev:
            direction = -direction
        d += direction * STEP_D
        if d <= D_MIN or d >= D_MAX:          # hit a limit: clamp and turn back
            d = min(max(d, D_MIN), D_MAX)
            direction = -direction
        p_prev = p

        log["t"].append(t)
        log["g"].append(g)
        log["v"].append(v)
        log["p"].append(p)
        log["d"].append(d)
        log["p_ideal"].append(pv.max_power_point(g, temp)[2])
        log["p_direct"].append(V_BAT * pv.current_at(V_BAT, g, temp))
    return log


def energy(series):
    return sum(series) * DT


if __name__ == "__main__":
    log = run()
    e_mppt, e_ideal, e_direct = energy(log["p"]), energy(log["p_ideal"]), energy(log["p_direct"])
    eff = e_mppt / e_ideal * 100
    gain = (e_mppt / e_direct - 1) * 100

    # time for the tracker to first reach 98 % of the ideal power from the bad start
    settle = next(t for t, p, pi in zip(log["t"], log["p"], log["p_ideal"]) if p >= 0.98 * pi)

    lines = [
        f"Simulated time                  : {T_END:.0f} s, control period {DT*1e3:.0f} ms",
        f"Energy, ideal MPP               : {e_ideal:.1f} J",
        f"Energy, P&O MPPT                : {e_mppt:.1f} J",
        f"Energy, direct battery connect  : {e_direct:.1f} J",
        f"MPPT tracking efficiency        : {eff:.1f} %",
        f"Extra energy vs direct connect  : +{gain:.1f} %",
        f"Start-up settling (to 98 %)     : {settle:.2f} s",
    ]
    out = "\n".join(lines)
    print(out)
    with open(os.path.join(HERE, "results.txt"), "w") as f:
        f.write(out + "\n")

    # ---- Plot 1: tracking over time ----
    fig, ax = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    ax[0].plot(log["t"], log["g"], color="#d97706")
    ax[0].set_ylabel("Irradiance (W/m²)")
    ax[0].set_title("P&O MPPT tracking under changing sunlight")
    ax[1].plot(log["t"], log["p_ideal"], "--", color="#111", label="Ideal MPP")
    ax[1].plot(log["t"], log["p"], color="#2563eb", label="P&O MPPT")
    ax[1].plot(log["t"], log["p_direct"], color="#dc2626", label="Direct to battery")
    ax[1].set_ylabel("Panel power (W)")
    ax[1].legend(loc="lower left")
    ax[2].plot(log["t"], log["v"], color="#059669")
    ax[2].set_ylabel("Panel voltage (V)")
    ax[2].set_xlabel("Time (s)")
    for a in ax:
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "mppt_tracking.png"), dpi=130)

    # ---- Plot 2: P-V curves ----
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for g, temp in [(1000, 25), (800, 40), (400, 35)]:
        curve = pv.iv_curve(g, temp)
        ax.plot([v for v, _ in curve], [v * i for v, i in curve], label=f"{g} W/m², {temp} °C")
        vm, _, pm = pv.max_power_point(g, temp)
        ax.plot(vm, pm, "o", color="black")
    ax.axvline(V_BAT, color="#dc2626", ls=":", label="Battery voltage (direct connect)")
    ax.set_xlabel("Panel voltage (V)")
    ax.set_ylabel("Power (W)")
    ax.set_title("50 W panel P-V curves (dots = maximum power point)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "pv_curves.png"), dpi=130)
