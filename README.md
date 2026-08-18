# Spire Scrims API

A small REST API for managing scrims, lobbies, and lobby players. It includes
interactive Swagger docs so you can inspect the endpoints and try requests from
your browser.

## Use the Swagger docs

Start the docs server:

```bash
python3 scripts/serve_docs.py
```

Open [http://localhost:8000](http://localhost:8000), then:

1. Keep **This docs server** selected in the Servers menu.
2. Open an endpoint and click **Try it out**.

The terminal should show this target:

```text
Proxy: /api/* -> <SCRIMS_API_URL>
```

## Authentication

Every API request needs a bearer token:

```text
Authorization: Bearer <api-key>
```

The docs server reads `SCRIMS_API_KEY` from `scripts/.env` and adds the bearer
token to proxied requests. The key is not exposed to the browser.

## Run the production test

Copy `scripts/.env.example` to `scripts/.env`, then add the production API URL
and key:

```text
SCRIMS_API_URL=https://your-api.example.com
SCRIMS_API_KEY=your-api-key
```

Then run:

```bash
python3 scripts/test_create_scrim.py
```

This creates a real scrim with lobbies and players in production. When it
finishes, it prints the command you can use to delete the test scrim.

## More details

- The OpenAPI source is in [`docs/openapi.yaml`](docs/openapi.yaml).

The documentation must be opened through the docs server. It loads
`docs/openapi.yaml` directly, and the server proxies **Try it out** requests to
the API to avoid browser CORS restrictions.
