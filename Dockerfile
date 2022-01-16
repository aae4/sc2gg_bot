# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster as sc2ggbot

WORKDIR /workspace/app

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY . .

ADD ./config.ini.example /workspace/app/config.ini

CMD [ "python3", "main.py"]
