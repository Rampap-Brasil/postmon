FROM ubuntu:18.04
MAINTAINER Bluesoft Fire <devops@bluesoft.com.br>

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get -y update && \
    apt-get -y install \
        gcc \
        python2.7 \
        python2.7-dev \
        python-pip \
        libz-dev \
        libxml2-dev \
        libxslt1-dev \
        libyaml-dev \
        libpython2.7-dev

# Versões específicas para compatibilidade com Python 2.7
RUN pip install --upgrade pip==20.3.4
RUN pip install setuptools==44.1.1 wheel==0.37.1

ENV APP_DIR /srv/postmon

RUN mkdir -p $APP_DIR
WORKDIR $APP_DIR

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 9876

ENTRYPOINT ["python2.7", "PostmonServer.py"]