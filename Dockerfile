FROM denoland/deno:2.5.2 AS deno

FROM python:3.13-slim

COPY --from=deno /usr/bin/deno /usr/local/bin/deno

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -U "yt-dlp[default]"

RUN pip install --no-cache-dir \
    aiogram \
    aiohttp \
    imageio-ffmpeg \
    bgutil-ytdlp-pot-provider

COPY . .

CMD ["python", "bot.py"]
