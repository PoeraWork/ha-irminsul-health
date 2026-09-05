# Irminsul Health

Irminsul Health is a person-centered health data hub for Home Assistant. It
accepts low-frequency health observations through a private webhook, keeps an
exact bounded record, and exposes the latest value as Home Assistant entities.

The first development slice supports uric acid observations. The data contract
is versioned so Apple HealthKit, Android Health Connect, OCR, and device adapters
can be added without making Home Assistant depend on one mobile platform.

## Status

This repository is an early development version. Do not use it as the only copy
of medical data. It is not a medical device and does not provide medical advice.

## Install for development

Copy `custom_components/irminsul_health` into the Home Assistant `config`
directory, restart Home Assistant, then add **Irminsul Health** from
**Settings → Devices & services**.

The setup result displays a private webhook URL. Treat the URL as a password.
Use HTTPS or a trusted VPN when calling it remotely.

Open **Reconfigure** on the integration entry to view the current URL or generate
a new one. Rotating it invalidates the old URL after the integration reloads.

## Send an observation

Send a `POST` request with JSON:

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
duplicate record.

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
- Latest uric acid value and measurement-time sensors.
- Chinese and English UI text.

High-frequency raw samples, custom dashboard cards, OCR, source subentries, and
long-term-statistics imports are intentionally outside version 0.1.

## Development

```powershell
uv sync --group test --group lint
uv run ruff check .
uv run pytest
```
