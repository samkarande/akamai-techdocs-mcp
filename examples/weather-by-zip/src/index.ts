import { AutoRouter, error, json } from 'itty-router';

let router = AutoRouter();

router
    // GET /weather/90210   or   GET /weather?zip=90210
    .get('/weather/:zip', ({ zip }) => getWeather(zip))
    .get('/weather', (request) => getWeather(new URL(request.url).searchParams.get('zip')))
    .all('*', () => error(404, 'Try GET /weather/<zipcode>'));

/**
 * Look up a US zip code -> coordinates (Zippopotam), then fetch the
 * current weather for those coordinates (Open-Meteo). Both APIs are
 * free and require no key.
 */
async function getWeather(zip: string | null) {
    if (!zip || !/^\d{5}$/.test(zip)) {
        return error(400, 'Provide a valid 5-digit US zip code, e.g. /weather/90210');
    }

    // 1. Zip code -> latitude / longitude / place name
    const geoResp = await fetch(`https://api.zippopotam.us/us/${zip}`);
    if (geoResp.status === 404) {
        return error(404, `Unknown zip code: ${zip}`);
    }
    if (!geoResp.ok) {
        return error(502, 'Geocoding service unavailable');
    }
    const geo = await geoResp.json();
    const place = geo.places[0];
    const lat = place.latitude;
    const lon = place.longitude;

    // 2. Coordinates -> current weather
    const wxResp = await fetch(
        `https://api.open-meteo.com/v1/forecast` +
        `?latitude=${lat}&longitude=${lon}` +
        `&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code` +
        `&temperature_unit=fahrenheit&wind_speed_unit=mph`,
    );
    if (!wxResp.ok) {
        return error(502, 'Weather service unavailable');
    }
    const wx = await wxResp.json();
    const c = wx.current;

    // 3. Shape a tidy JSON response
    return json({
        zip,
        location: `${place['place name']}, ${place['state abbreviation']}`,
        coordinates: { latitude: Number(lat), longitude: Number(lon) },
        weather: {
            temperature_f: c.temperature_2m,
            humidity_pct: c.relative_humidity_2m,
            wind_mph: c.wind_speed_10m,
            condition: describe(c.weather_code),
            observed_at: c.time,
        },
    });
}

// Minimal WMO weather-code -> text mapping (subset).
function describe(code: number): string {
    const table: Record<number, string> = {
        0: 'Clear sky',
        1: 'Mainly clear',
        2: 'Partly cloudy',
        3: 'Overcast',
        45: 'Fog',
        51: 'Light drizzle',
        61: 'Light rain',
        63: 'Rain',
        65: 'Heavy rain',
        71: 'Light snow',
        73: 'Snow',
        75: 'Heavy snow',
        80: 'Rain showers',
        95: 'Thunderstorm',
    };
    return table[code] ?? `Code ${code}`;
}

//@ts-ignore  -- `fetch` event is provided by the Spin JS runtime
addEventListener('fetch', async (event: FetchEvent) => {
    event.respondWith(router.fetch(event.request));
});
