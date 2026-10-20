"""
Buck converter design for the MPPT charge controller.

Panel side : 50 W panel, Vmp ~17.6 V (range 15-22 V)
Battery    : 12 V lead-acid, 12.0-14.4 V (charging at up to 13.8 V float / 14.4 V absorb)
Switching  : 31.25 kHz (Arduino Timer1, 16 MHz / 512)

Run:  python3 design/buck_design.py
"""

P_MAX = 50.0
V_IN_NOM, V_IN_MAX = 17.6, 22.0
V_BAT_NOM, V_BAT_MAX = 13.8, 14.4
F_SW = 16e6 / 512                 # 31.25 kHz
RIPPLE_I_FRAC = 0.30              # inductor ripple = 30 % of load current
RIPPLE_V_OUT = 0.05               # 50 mV battery-side ripple target
L_STD = [47e-6, 68e-6, 100e-6, 150e-6, 220e-6]
C_STD = [100e-6, 220e-6, 330e-6, 470e-6, 1000e-6]

i_out = P_MAX / V_BAT_NOM
d_nom = V_BAT_NOM / V_IN_NOM
delta_i = RIPPLE_I_FRAC * i_out

# Worst-case ripple occurs at the highest input voltage
d_at_vmax = V_BAT_NOM / V_IN_MAX
l_min = (V_IN_MAX - V_BAT_NOM) * d_at_vmax / (F_SW * delta_i)
l_used = next(l for l in L_STD if l >= l_min)
delta_i_used = (V_IN_MAX - V_BAT_NOM) * d_at_vmax / (F_SW * l_used)

c_min = delta_i_used / (8 * F_SW * RIPPLE_V_OUT)
c_used = next(c for c in C_STD if c >= c_min)

i_in_rms = i_out * (d_nom * (1 - d_nom)) ** 0.5   # input capacitor RMS current
i_peak = i_out + delta_i_used / 2

print(f"Switching frequency      : {F_SW/1e3:.2f} kHz")
print(f"Battery-side current     : {i_out:.2f} A at {P_MAX:.0f} W")
print(f"Duty cycle at MPP        : D = Vbat/Vpv = {V_BAT_NOM}/{V_IN_NOM} = {d_nom:.2f}")
print(f"Inductor (min)           : {l_min*1e6:.0f} uH  -> use {l_used*1e6:.0f} uH, >= {i_peak*1.3:.1f} A saturation")
print(f"Inductor ripple          : {delta_i_used:.2f} A p-p, peak current {i_peak:.2f} A")
print(f"Output capacitor (min)   : {c_min*1e6:.0f} uF -> use {c_used*1e6:.0f} uF / 25 V low-ESR")
print(f"Input capacitor RMS      : {i_in_rms:.2f} A -> 470 uF / 35 V low-ESR")
print(f"MOSFET                   : IRFZ44N (55 V, 17.5 mOhm) driven by IR2104 half-bridge driver")
print(f"Blocking diode           : MBR1045 Schottky stops the battery feeding the panel at night")
