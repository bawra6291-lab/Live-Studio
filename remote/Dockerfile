FROM python:3.12-slim
WORKDIR /srv
COPY store.py server.py ./
COPY web ./web
RUN useradd --system --uid 10001 relay && mkdir /data && chown relay /data
USER 10001
ENV LIVE_DESK_DB=/data/relay.db
EXPOSE 8080
CMD ["python","server.py","serve","--host","0.0.0.0"]
