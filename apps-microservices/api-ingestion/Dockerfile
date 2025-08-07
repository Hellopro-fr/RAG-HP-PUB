FROM python:3.13

WORKDIR /app

COPY . /app 

RUN chmod +x init.sh
RUN chmod +x run.sh

RUN ./init.sh

EXPOSE 8509


CMD ["./run.sh"]