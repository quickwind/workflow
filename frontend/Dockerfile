FROM bitnami/node:20 AS build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
COPY bpmn-instance-viewer-js /app/bpmn-instance-viewer-js
RUN npm ci

COPY frontend .
RUN npm run build -- --configuration production

FROM bitnami/nginx:1.27

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV API_BASE_URL=

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
