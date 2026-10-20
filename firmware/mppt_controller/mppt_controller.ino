/*
 * Solar MPPT Charge Controller - Arduino Nano firmware
 *
 * Hardware:
 *   - Synchronous buck: 2 x IRFZ44N, IR2104 half-bridge driver, 220 uH inductor
 *   - Panel voltage : divider 47k / 10k  -> A0
 *   - Battery volt. : divider 47k / 10k  -> A1
 *   - Panel current : ACS712-05B         -> A2
 *   - PWM to IR2104 IN : D9  (Timer1, 31.25 kHz)
 *   - IR2104 SD (enable): D8
 *   - 16x2 I2C LCD (address 0x27) on A4/A5
 *
 * Charging:
 *   BULK   : P&O MPPT, all available solar power into the battery
 *   ABSORB : hold the battery at 14.4 V (constant voltage) by trimming duty
 *   FLOAT  : hold 13.8 V once the charge current tapers off
 *   NIGHT  : panel below battery + 0.5 V -> converter off
 */
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ---------------- Pins ----------------
const uint8_t PIN_VPV = A0, PIN_VBAT = A1, PIN_IPV = A2;
const uint8_t PIN_PWM = 9, PIN_DRV_EN = 8;

// ---------------- Calibration ----------------
const float ADC_REF = 5.0;
const float DIV_RATIO = (47.0 + 10.0) / 10.0;     // 5.7
const float ACS_ZERO_V = 2.5, ACS_V_PER_A = 0.185; // ACS712-05B

// ---------------- Control constants ----------------
const uint16_t PWM_TOP = 511;                      // 16 MHz / 512 = 31.25 kHz
const float D_MIN = 0.40, D_MAX = 0.95, D_STEP = 0.005;
const float V_ABSORB = 14.4, V_FLOAT = 13.8;
const float I_FLOAT_SWITCH = 0.3;                  // A: absorb -> float when current tapers
const unsigned long CONTROL_MS = 50;

enum Stage { NIGHT, BULK, ABSORB, FLOAT_STAGE };
Stage stage = NIGHT;

float duty = 0.80;
int8_t direction = -1;     // -1 lowers duty (raises panel voltage)
float pPrev = 0;

LiquidCrystal_I2C lcd(0x27, 16, 2);

float readAvg(uint8_t pin) {
  long sum = 0;
  for (uint8_t i = 0; i < 16; i++) sum += analogRead(pin);
  return (sum / 16.0) * ADC_REF / 1023.0;
}

void setDuty(float d) {
  duty = constrain(d, D_MIN, D_MAX);
  OCR1A = (uint16_t)(duty * PWM_TOP);
}

void converterOn(bool on) {
  digitalWrite(PIN_DRV_EN, on ? HIGH : LOW);
}

void setup() {
  pinMode(PIN_PWM, OUTPUT);
  pinMode(PIN_DRV_EN, OUTPUT);
  converterOn(false);

  // Timer1: fast PWM, TOP = ICR1, non-inverting on OC1A (D9), no prescaler
  TCCR1A = _BV(COM1A1) | _BV(WGM11);
  TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS10);
  ICR1 = PWM_TOP;
  setDuty(duty);

  lcd.init();
  lcd.backlight();
  Serial.begin(115200);
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last < CONTROL_MS) return;
  last = millis();

  float vpv = readAvg(PIN_VPV) * DIV_RATIO;
  float vbat = readAvg(PIN_VBAT) * DIV_RATIO;
  float ipv = (readAvg(PIN_IPV) - ACS_ZERO_V) / ACS_V_PER_A;
  if (ipv < 0) ipv = 0;
  float ppv = vpv * ipv;

  // ---------------- Stage selection ----------------
  if (vpv < vbat + 0.5) {
    stage = NIGHT;
  } else if (stage == NIGHT) {
    stage = BULK;
    setDuty(vbat / vpv);           // start near the right ratio
  }

  switch (stage) {
    case NIGHT:
      converterOn(false);
      break;

    case BULK:                     // Perturb & Observe MPPT
      converterOn(true);
      if (ppv < pPrev) direction = -direction;
      setDuty(duty + direction * D_STEP);
      if (duty <= D_MIN || duty >= D_MAX) direction = -direction;
      if (vbat >= V_ABSORB) stage = ABSORB;
      break;

    case ABSORB:                   // constant voltage at 14.4 V
    case FLOAT_STAGE: {            // constant voltage at 13.8 V
      converterOn(true);
      float target = (stage == ABSORB) ? V_ABSORB : V_FLOAT;
      setDuty(duty + (vbat < target ? D_STEP : -D_STEP));
      if (stage == ABSORB && ipv < I_FLOAT_SWITCH) stage = FLOAT_STAGE;
      if (vbat < V_FLOAT - 0.6) stage = BULK;   // heavy load pulled the battery down
      break;
    }
  }
  pPrev = ppv;

  // ---------------- Display ----------------
  static uint8_t tick = 0;
  if (++tick >= 10) {              // refresh every 0.5 s
    tick = 0;
    const char *names[] = {"NIGHT", "BULK ", "ABSRB", "FLOAT"};
    lcd.setCursor(0, 0);
    lcd.print("PV "); lcd.print(vpv, 1); lcd.print("V ");
    lcd.print(ppv, 1); lcd.print("W  ");
    lcd.setCursor(0, 1);
    lcd.print("BT "); lcd.print(vbat, 1); lcd.print("V ");
    lcd.print(names[stage]); lcd.print(" ");
    lcd.print((int)(duty * 100)); lcd.print("%  ");

    Serial.print(vpv); Serial.print(','); Serial.print(ipv); Serial.print(',');
    Serial.print(ppv); Serial.print(','); Serial.print(vbat); Serial.print(',');
    Serial.print(duty); Serial.print(','); Serial.println(names[stage]);
  }
}
