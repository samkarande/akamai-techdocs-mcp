# weather-by-zip — Akamai Functions sample

An HTTP function (Spin component) that takes a US zip code and returns the
current weather as JSON.

```
GET /weather/90210
GET /weather?zip=90210
```

It chains two free, key-less APIs:
1. **Zippopotam** — zip code → latitude/longitude + place name
2. **Open-Meteo** — coordinates → current temperature, humidity, wind, condition

## Create the project from the template (recommended)

The `src/index.ts` and `spin.toml` here drop into a standard `http-ts`
project. To scaffold one from scratch:

```bash
spin templates install --git https://github.com/spinframework/spin-js-sdk --update
spin new -t http-ts weather-by-zip --accept-defaults
# then replace src/index.ts and spin.toml with the files in this folder
npm install
npm install itty-router
```

## Build and run locally

```bash
spin build
spin up        # serves on http://localhost:3000 by default
```

## Try it

```bash
curl -s localhost:3000/weather/90210 | jq
```

```json
{
  "zip": "90210",
  "location": "Beverly Hills, CA",
  "coordinates": { "latitude": 34.0901, "longitude": -118.4065 },
  "weather": {
    "temperature_f": 72.3,
    "humidity_pct": 44,
    "wind_mph": 5.1,
    "condition": "Clear sky",
    "observed_at": "2026-06-01T19:00"
  }
}
```

## Notes

- The two upstream hosts **must** be listed in `allowed_outbound_hosts` in
  `spin.toml`; otherwise `fetch()` fails with "Destination not allowed".
- `fetch` and all Spin SDK calls must run **inside** the `fetch` event
  handler — they don't work at module top level.
