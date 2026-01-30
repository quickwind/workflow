FROM bitnami/python:3.12

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Dev-friendly defaults. Override in docker run / compose.
ENV DJANGO_DEBUG=true
ENV DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
