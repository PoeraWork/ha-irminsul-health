# Irminsul Health

Irminsul Health is a person-centered health data hub for Home Assistant. It
accepts low-frequency health observations through a private webhook, keeps an
exact bounded record, and exposes the latest value as Home Assistant entities.

Each profile can select common body, cardiac, lab, activity, and sleep metrics.
The data contract is versioned so Apple HealthKit, Android Health Connect, OCR, and device adapters
can be added without making Home Assistant depend on one mobile platform.

## Status

This repository is an early development version. Do not use it as the only copy
of medical data. It is not a medical device and does not provide medical advice.

## Install for development

Copy `custom_components/irminsul_health` into the Home Assistant `config`
directory, restart Home Assistant, then add **Irminsul Health** from
**Settings → Devices & services**.

The setup result displays a private webhook URL and an ingest token. Treat both
as passwords. New profiles accept local network requests only by default. Enable
remote requests explicitly and use HTTPS or a trusted VPN.

Open **Reconfigure** on the integration entry to view the current URL or generate
a new one. Rotating credentials invalidates both the old URL and token after the
integration reloads.

## Configure people and metrics

Open **Settings → Devices & services → Irminsul Health → Configure** on a profile.
Select an optional **Person** entity, a metric policy, and the metric list:

- **Whitelist**: accept and expose only selected metrics. An empty list enables none.
- **Blacklist**: accept and expose all catalog metrics except those selected. An empty
  list enables all, including metrics added to the catalog in future updates.

Each HA person can be linked to one health profile. Linking follows entity renames
and does not change home/away state. Profile IDs, webhook credentials, and existing
sensor IDs are independent of the selected person. Sensors expose the association
through their `person_entity_id` attribute; this does not add fields to `person.xxx`.

Saving reloads the integration entry. Disabled metrics reject uploads with HTTP
403; a mixed batch containing a disabled metric is rejected in full. Their existing
sensor registry entries are disabled, not deleted, and retained observations remain.
Reenabling restores the same entities and latest retained values. Entities separately
disabled by the user remain disabled. During reload, an in-flight request may receive
HTTP 503 and can be retried after the profile is ready.

New profiles default to weight, heart rate, steps, and sleep duration. Existing
profiles without metric settings retain uric acid and blood glucose until configured.
Select uric acid in the whitelist before using the example below. Values stay
`unknown` until data is submitted; selecting a metric does not start a data source.

## Supported metrics

The sender must provide an explicit metric and unit. Storage uses the canonical
units below and rounds numeric values to two decimal places; some sensors display
whole numbers. Bounds validate the data format, not a clinical diagnosis.

| Measurement | `metric` | Canonical unit |
| --- | --- | --- |
| Uric acid / 尿酸 | `uric_acid` | µmol/L |
| Blood glucose / 血糖 | `blood_glucose` | mmol/L |
| Height / 身高 | `height` | cm |
| Weight / 体重 | `weight` | kg |
| BMI | `bmi` | kg/m² |
| Body fat / 体脂率 | `body_fat` | % |
| Waist / 腰围 | `waist` | cm |
| Body temperature / 体温 | `body_temperature` | °C |
| Heart rate / 心率 | `heart_rate` | bpm |
| Resting heart rate / 静息心率 | `resting_heart_rate` | bpm |
| HRV (SDNN) / 心率变异性 | `hrv_sdnn` | ms |
| Oxygen saturation / 血氧饱和度 | `oxygen_saturation` | % |
| Respiratory rate / 呼吸频率 | `respiratory_rate` | breaths/min |
| Systolic pressure / 收缩压 | `blood_pressure_systolic` | mmHg |
| Diastolic pressure / 舒张压 | `blood_pressure_diastolic` | mmHg |
| HbA1c / 糖化血红蛋白 | `hba1c` | % |
| Total cholesterol / 总胆固醇 | `total_cholesterol` | mmol/L |
| Triglycerides / 甘油三酯 | `triglycerides` | mmol/L |
| HDL cholesterol / 高密度脂蛋白胆固醇 | `hdl_cholesterol` | mmol/L |
| LDL cholesterol / 低密度脂蛋白胆固醇 | `ldl_cholesterol` | mmol/L |
| Daily steps / 当日步数 | `steps` | steps |
| Daily active distance / 当日活动距离 | `active_distance` | km |
| Daily active energy / 当日活动能量 | `active_energy` | kcal |
| Daily exercise duration / 当日运动时长 | `exercise_duration` | min |
| Sleep duration / 睡眠时长 | `sleep_duration` | min |
| Deep sleep / 深睡时长 | `sleep_deep` | min |
| Light sleep / 浅睡时长 | `sleep_light` | min |
| REM sleep / 快速眼动睡眠时长 | `sleep_rem` | min |

Additional accepted input units: uric acid `umol/L` and `mg/dL`; glucose `mg/dL`;
height/waist `m` and `in`; weight `g` and `lb`; BMI `kg/m2`; temperature `°F`;
HRV `s`; distance `m` and `mi`; energy `kJ`; durations `s` and `h`.
Lipid values require `mmol/L`, and HbA1c requires `%`; other conventions are not
silently converted. HRV must be SDNN, not RMSSD.

`observed_at` is the actual measurement time, with a time-zone offset. Activity
metrics (`time_kind: daily_snapshot`) are a snapshot of that day's total at that
time, not a delta to add. Sleep metrics (`time_kind: sleep_session`) describe one
sleep session, with its end as `observed_at`. Other metrics use `time_kind: instant`.
Send sleep stages as separate observations. The integration does not infer stages,
sum activity samples, reset daily values, or infer that someone is currently asleep.
Sensors have no `state_class`, so these snapshots are not misreported as cumulative
counters or imported into HA long-term statistics.
Give each distinct snapshot its own `external_id` (or omit it). Reusing one daily
ID with a changed total is a conflict, not an update to the previous observation.

## Send an observation

Send a `POST` request with `Authorization: Bearer <ingest token>` and JSON:

```json
{
  "schema_version": 1,
  "observations": [
    {
      "metric": "uric_acid",
      "value": 426,
      "unit": "µmol/L",
      "observed_at": "2026-09-05T08:30:00+08:00",
      "external_id": "meter-20260905-0830",
      "note": "Before breakfast"
    }
  ]
}
```

`mg/dL` is also accepted and converted to `µmol/L`. `observed_at` must contain a
time-zone offset. Repeating the same `external_id` is safe and does not create a
duplicate record. Reusing it for different content is rejected. Timestamps more
than ten minutes in the future are rejected.

For blood glucose, use `metric: "blood_glucose"` with `mmol/L` or `mg/dL`.
Glucose is stored in `mmol/L`, rounded to two decimal places. The conversion is
`mg/dL / 18`, using the approximate rule documented in the
[FORA glucose meter manual](https://foracare.ch/wp-content/uploads/2021/10/FORA-Diamond-GD50-4286B_meter-manual.pdf).
The caller must explicitly choose the metric and the original measurement unit;
the integration does not classify values by their range. Glucose validation
requires a finite positive value that remains positive after rounding; it does
not classify clinical risk. Text such as `HI` or `LO` is not a numeric observation.

The companion `irminsul-shortcuts` project has a single-record photo OCR template.
The user selects uric acid or blood glucose, corrects the recognized value, chooses
the original unit, and confirms the measurement time before submitting. Only
confirmed fields reach this webhook, not the photo or full OCR text. The template
requires macOS signing. It does not read Apple Health or send the additional metrics
automatically; each data source needs its own adapter.

Example response:

```json
{
  "accepted": 1,
  "duplicates": 0
}
```

## Current scope

- Multiple people through separate config entries and optional HA person links.
- One generic webhook source for each person.
- Exact storage of up to 500 observations per metric per profile.
- Configurable whitelist or blacklist enforced for uploads and sensor creation.
- Latest value and measurement-time sensors for each enabled metric.
- Chinese and English UI text.

Existing uric acid entity IDs, credentials, and stored observations are unchanged.
Each metric has its own 500-record limit, so frequent activity uploads do not evict
lab results. Disabling a metric does not erase its retained records. This store is
independent of Recorder's history retention, but is not an unlimited archive.

High-frequency raw samples, custom dashboard cards, server-side OCR, source subentries, and
long-term-statistics imports are intentionally outside version 0.1.

## Privacy and data lifetime

Health observations are stored as permission-restricted but unencrypted JSON in
Home Assistant's `.storage` directory. Latest values are normal sensor states,
so Home Assistant Recorder, backups, and users who can read states may retain or
view them. Removing an Irminsul Health profile deletes its private observation
store, but it does not erase Recorder history or existing backups.

Person association is metadata, not a per-user access-control boundary. Metric
policies restrict incoming writes and active sensors; they do not hide previously
recorded states or provide separate read permissions for HA users.

Do not log complete `/api/webhook/...` paths in a reverse proxy. If a URL or
ingest token is exposed, rotate the credentials from the integration's
**Reconfigure** flow.

## Development

```powershell
uv sync --group test --group lint
uv run ruff check .
uv run pytest
```
