FROM python:3.12-slim
WORKDIR /srv
COPY store.py server.py entrypoint.py ./
COPY web ./web
RUN useradd --system --uid 10001 relay && mkdir /data && chown relay /data
ENV LIVE_DESK_DB=/data/relay.db
EXPOSE 8080
CMD ["python","entrypoint.py"]
