# TLS certificate files

Production Compose expects these files in this directory:

- `fullchain.pem` — server certificate followed by any intermediate certificates
- `privkey.pem` — matching private key

Use a certificate issued by the organisation's trusted internal CA or another
trusted CA. The certificate SAN must contain the DNS name or IP address operators
use to open the dashboard. Do not commit certificate or private-key files.

For a temporary isolated smoke test only, a self-signed certificate can be made
with OpenSSL. Browsers will warn until that certificate is trusted:

```bash
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 \
  -keyout deploy/certs/privkey.pem \
  -out deploy/certs/fullchain.pem \
  -subj "/CN=10.117.10.68" \
  -addext "subjectAltName=IP:10.117.10.68"
chmod 600 deploy/certs/privkey.pem
```

Compose mounts both files into the Nginx container as read-only secrets; the
private key does not need broader host permissions.
