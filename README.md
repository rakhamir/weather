# Sergeli Weather Telegram Bot

Daily Telegram weather update for Sergeli, Tashkent.

This version is designed for GitHub Actions so it can run in the cloud even when
your PC is asleep or offline. It uses Open-Meteo for weather and air quality, so
there is no weather API key.

## What it sends

- Current temperature and feels-like temperature
- Today's high/low
- Rain probability and expected rain
- Wind, humidity, and cloud cover
- Air quality when Open-Meteo has data
- One practical note for the day

## Telegram setup

1. In Telegram, message `@BotFather` and create a bot.
2. Save the bot token.
3. Open a chat with your new bot and send `/start`.
4. Get your numeric chat ID:
   - Temporarily set the token in PowerShell:
     ```powershell
     $env:TELEGRAM_BOT_TOKEN="123456789:replace-with-your-token"
     ```
   - Then run:
     ```powershell
     Invoke-RestMethod "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/getUpdates" | ConvertTo-Json -Depth 20
     ```
   - Look for `message.chat.id`.

For a private user, Telegram bots usually cannot send to `@rakh95` directly by
username. They need the numeric `chat.id` after you start the bot. If `@rakh95`
is a public channel or group instead, add the bot there and use that chat ID or
channel handle.

## GitHub Actions setup

1. Create a GitHub repository and push this folder.
2. In the repository, open **Settings -> Secrets and variables -> Actions**.
3. Add these repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Open **Actions -> Daily Sergeli weather -> Run workflow** once to test.

If you want to deploy with the GitHub API instead of pushing with `git`, set
`GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID`, then run:

```powershell
python -m pip install pynacl
python .\deploy_to_github.py
```

The schedule is in `.github/workflows/daily-weather.yml`. It runs at `02:05 UTC`,
which is `07:05` in Tashkent. It is intentionally five minutes after the hour
because GitHub says scheduled workflows can be delayed or dropped during heavy
start-of-hour load. Change the cron to `0 2 * * *` if you prefer exactly 07:00.

## Local test

Run a dry test without Telegram:

```powershell
python .\weather_to_telegram.py --dry-run
```

Send a real Telegram message from your PC:

```powershell
$env:TELEGRAM_BOT_TOKEN="123456789:replace-with-your-token"
$env:TELEGRAM_CHAT_ID="123456789"
python .\weather_to_telegram.py
```

## Limitations

- GitHub Actions is cloud-hosted, so your PC does not need to be on.
- GitHub scheduled workflows run from the default branch only.
- GitHub scheduled workflows are best-effort: they can be late and, under enough
  load, dropped.
- In a public inactive repository, GitHub can disable scheduled workflows after
  60 days without repository activity.
- Telegram delivery requires a bot token and a reachable chat ID.
- Open-Meteo can occasionally be unavailable or return incomplete air quality
  data; the script still sends weather if air quality is missing.
- The Tashkent schedule assumes UTC+5. If Uzbekistan ever changes time zone
  rules, update the cron schedule.
