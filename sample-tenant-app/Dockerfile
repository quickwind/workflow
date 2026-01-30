FROM bitnami/python:3.12

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./app.py

EXPOSE 9000

ENV APP_HOST=0.0.0.0
ENV APP_PORT=9000

CMD ["python", "app.py"]
