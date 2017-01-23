FROM python:2.7.13-alpine
MAINTAINER knepperjm@gmail.com

ARG URL
ENV URL ${URL:-"127.0.0.1"}

RUN mkdir /app && \
    pip install awscli

COPY ./* /app/

RUN chmod -R 755 /app

WORKDIR /app

CMD ["/bin/sh", "run.sh"]
