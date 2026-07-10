FROM postgres:18-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends locales \
    && sed -i '/ru_RU.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen ru_RU.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8 \
    POSTGRES_INITDB_ARGS="--locale-provider=libc --locale=ru_RU.UTF-8 --encoding=UTF8"
