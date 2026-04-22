#!/usr/bin/env python3
"""Send a daily Sergeli weather update to Telegram.

Uses Open-Meteo APIs, so no weather API key is required. Telegram delivery needs
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_LATITUDE = 41.19833
DEFAULT_LONGITUDE = 69.22222
DEFAULT_LOCATION = "Sergeli, Tashkent"
TIMEZONE = "Asia/Tashkent"

WEATHER_CODE_LABELS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def request_json(url: str, data: dict[str, str] | None = None) -> dict[str, Any]:
    encoded_data = None
    if data is not None:
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=encoded_data,
        headers={"User-Agent": "sergeli-weather-bot/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {body[:200]}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected response from {url}: {body[:200]}")
    return parsed


def fetch_weather(latitude: float, longitude: float) -> dict[str, Any]:
    params = {
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
            ]
        ),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "precipitation_sum",
                "wind_speed_10m_max",
            ]
        ),
        "forecast_days": "1",
        "timezone": TIMEZONE,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    return request_json(url)


def fetch_air_quality(latitude: float, longitude: float) -> dict[str, Any] | None:
    params = {
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "current": "us_aqi,pm2_5",
        "timezone": TIMEZONE,
    }
    url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode(params)
    try:
        return request_json(url)
    except RuntimeError as exc:
        print(f"Air quality unavailable: {exc}", file=sys.stderr)
        return None


def first_daily_value(payload: dict[str, Any], key: str) -> Any:
    daily = payload.get("daily", {})
    values = daily.get(key, [])
    if not isinstance(values, list) or not values:
        return None
    return values[0]


def current_value(payload: dict[str, Any], key: str) -> Any:
    current = payload.get("current", {})
    if not isinstance(current, dict):
        return None
    return current.get(key)


def weather_label(code: Any) -> str:
    try:
        return WEATHER_CODE_LABELS[int(code)]
    except (TypeError, ValueError, KeyError):
        return "Unknown"


def wind_direction_label(degrees: Any) -> str:
    try:
        value = float(degrees) % 360
    except (TypeError, ValueError):
        return "unknown"

    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = int((value + 22.5) // 45) % 8
    return labels[index]


def format_number(value: Any, decimals: int = 0) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "n/a"


def practical_note(
    temp_max: Any,
    precip_probability: Any,
    wind_max: Any,
    aqi: Any,
) -> str:
    try:
        high = float(temp_max)
    except (TypeError, ValueError):
        high = None
    try:
        rain_chance = float(precip_probability)
    except (TypeError, ValueError):
        rain_chance = None
    try:
        peak_wind = float(wind_max)
    except (TypeError, ValueError):
        peak_wind = None
    try:
        us_aqi = float(aqi)
    except (TypeError, ValueError):
        us_aqi = None

    notes: list[str] = []
    if rain_chance is not None and rain_chance >= 45:
        notes.append("take an umbrella")
    if peak_wind is not None and peak_wind >= 35:
        notes.append("expect strong wind")
    if high is not None and high >= 34:
        notes.append("plan for heat and drink extra water")
    elif high is not None and high <= 5:
        notes.append("dress warmly")
    if us_aqi is not None and us_aqi >= 101:
        notes.append("air quality may bother sensitive people")

    if not notes:
        return "Looks manageable for normal plans."
    return "Practical note: " + "; ".join(notes) + "."


def build_message(location: str, weather: dict[str, Any], air_quality: dict[str, Any] | None) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))

    current_code = current_value(weather, "weather_code")
    daily_code = first_daily_value(weather, "weather_code")
    code = current_code if current_code is not None else daily_code

    temp = current_value(weather, "temperature_2m")
    feels_like = current_value(weather, "apparent_temperature")
    humidity = current_value(weather, "relative_humidity_2m")
    wind = current_value(weather, "wind_speed_10m")
    wind_direction = current_value(weather, "wind_direction_10m")
    cloud_cover = current_value(weather, "cloud_cover")

    temp_max = first_daily_value(weather, "temperature_2m_max")
    temp_min = first_daily_value(weather, "temperature_2m_min")
    precip_probability = first_daily_value(weather, "precipitation_probability_max")
    precip_sum = first_daily_value(weather, "precipitation_sum")
    wind_max = first_daily_value(weather, "wind_speed_10m_max")

    aqi = None
    pm25 = None
    if air_quality:
        current_air = air_quality.get("current", {})
        if isinstance(current_air, dict):
            aqi = current_air.get("us_aqi")
            pm25 = current_air.get("pm2_5")

    lines = [
        f"{location} weather - {now:%a, %d %b %Y, %H:%M}",
        f"Now: {weather_label(code)}, {format_number(temp, 1)} C (feels {format_number(feels_like, 1)} C)",
        f"Today: {format_number(temp_min, 0)}-{format_number(temp_max, 0)} C, rain chance {format_number(precip_probability, 0)}%, expected rain {format_number(precip_sum, 1)} mm",
        f"Wind: {format_number(wind, 0)} km/h {wind_direction_label(wind_direction)} now, up to {format_number(wind_max, 0)} km/h",
        f"Humidity/clouds: {format_number(humidity, 0)}% / {format_number(cloud_cover, 0)}%",
    ]

    if aqi is not None or pm25 is not None:
        lines.append(f"Air: AQI {format_number(aqi, 0)}, PM2.5 {format_number(pm25, 1)} ug/m3")

    lines.append(practical_note(temp_max, precip_probability, wind_max, aqi))
    return "\n".join(lines)


def send_telegram(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
    }
    response = request_json(url, payload)
    if not response.get("ok"):
        raise RuntimeError(f"Telegram rejected the message: {response}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Sergeli weather to Telegram.")
    parser.add_argument("--dry-run", action="store_true", help="Print the update without sending Telegram.")
    parser.add_argument("--location", default=os.getenv("WEATHER_LOCATION", DEFAULT_LOCATION))
    parser.add_argument("--latitude", type=float, default=float(os.getenv("WEATHER_LATITUDE", DEFAULT_LATITUDE)))
    parser.add_argument("--longitude", type=float, default=float(os.getenv("WEATHER_LONGITUDE", DEFAULT_LONGITUDE)))
    parser.add_argument("--bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--chat-id", default=os.getenv("TELEGRAM_CHAT_ID"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    weather = fetch_weather(args.latitude, args.longitude)
    air_quality = fetch_air_quality(args.latitude, args.longitude)
    message = build_message(args.location, weather, air_quality)

    if args.dry_run:
        print(message)
        return 0

    if not args.bot_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN. Create a bot with @BotFather and add the token as a secret.")
    if not args.chat_id:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID. For a private chat, this must be your numeric Telegram chat ID.")

    send_telegram(args.bot_token, args.chat_id, message)
    print("Weather update sent to Telegram.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
