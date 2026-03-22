FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update \
	&& apt-get install -y --no-install-recommends ca-certificates curl gnupg \
	&& install -d /usr/share/postgresql-common/pgdg \
	&& curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
	   | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
	&& echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
	   > /etc/apt/sources.list.d/pgdg.list \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends postgresql-client-17 \
	&& rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=run.py
ENV PG_DUMP_BIN=/usr/lib/postgresql/17/bin/pg_dump
ENV PSQL_BIN=/usr/lib/postgresql/17/bin/psql
CMD ["gunicorn", "run:app", "-b", "0.0.0.0:8000"]
