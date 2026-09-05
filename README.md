# Irminsul Health

Irminsul Health is a person-centered health data hub for Home Assistant. It
accepts low-frequency health observations through a private webhook, keeps an
exact bounded record, and exposes the latest value as Home Assistant entities.

The current development slice supports uric acid and blood glucose observations. The data contract
is versioned so Apple HealthKit, Android Health Connect, OCR, and device adapters
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
still needs macOS signing and iPhone validation. It does not read Apple Health.

Example response:

```json
{
  "accepted": 1,
  "duplicates": 0
}
```

## Current scope

- Multiple people through separate config entries.
- One generic webhook source for each person.
- Exact storage of up to 500 low-frequency observations per person.
- Latest uric acid and blood glucose values and measurement-time sensors.
- Chinese and English UI text.

Existing uric acid entity IDs, credentials, and stored observations are unchanged.
After updating the integration and restarting HA, a profile also has glucose
entities; their values remain unknown until a glucose observation is submitted.
The 500-record limit is shared across both metrics in a profile, not per metric.

High-frequency raw samples, custom dashboard cards, server-side OCR, source subentries, and
long-term-statistics imports are intentionally outside version 0.1.

## Privacy and data lifetime

Health observations are stored as permission-restricted but unencrypted JSON in
Home Assistant's `.storage` directory. Latest values are normal sensor states,
so Home Assistant Recorder, backups, and users who can read states may retain or
view them. Removing an Irminsul Health profile deletes its private observation
store, but it does not erase Recorder history or existing backups.

Do not log complete `/api/webhook/...` paths in a reverse proxy. If a URL or
ingest token is exposed, rotate the credentials from the integration's
**Reconfigure** flow.

## Development

```powershell
uv sync --group test --group lint
uv run ruff check .
uv run pytest
```
