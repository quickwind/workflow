#!/usr/bin/env sh
set -eu

API_BASE_URL_VALUE="${API_BASE_URL:-}"

cat > /usr/share/nginx/html/app-config.js <<EOF
window.__APP_CONFIG__ = {
  apiBaseUrl: "${API_BASE_URL_VALUE}"
};
EOF

exec "$@"
