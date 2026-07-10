# meli-bridge

Microservicio **FastAPI** intermediario entre un CMS propio y **Mercado Libre Inmuebles (México, sitio `MLM`)**.

El CMS dispara webhooks cuando se crea/actualiza un inmueble y este microservicio los publica o sincroniza con MELI usando la API premium de Inmuebles. Incluye manejo de OAuth (solo refresh), retry ante errores transitorios de MELI (409/429/500/401), validación estricta del payload con Pydantic (reglas feb-2026) y persistencia del mapeo `id_cms ↔ item_id MELI` en MongoDB.

## Características

- **FastAPI** + **httpx** (HTTP/2 async) + **motor** (Mongo async)
- **OAuth MELI**: solo flujo `refresh_token` (rotación automática atómica en Mongo)
- **Validación previa** con Pydantic v2: regla feb-2026 de mínimo 1 imagen, `address_line` con calle+número, `gold_pro` (no `gold_premium`) en MLM
- **Reintentos** automáticos (tenacity) ante 409 `optimistic_locking`, 429 `too_many_requests`, 500 interne y 401 `invalid_token`
- **Webhook receptor MELI** (`/meli/notifications`) ya listo para topics `items` (recategorización oct-2025), `quotations` y `Leads` — solo hay que suscribirlos en MELI y descomentar el código de manejo.
- **Healthchecks** `/healthz` (liveness) y `/readyz` (readiness con Mongo ping) para Cloud Run
- **Docker** multi-stage + **docker-compose** con MongoDB 7 (imágenes livianas)

## Estructura

```
app/
  main.py                 # FastAPI app + lifespan
  core/
    config.py             # Settings (pydantic-settings, env)
    db.py                 # Motor (Mongo async) singleton
    logging.py            # structlog (JSON en prod)
  auth/
    meli_oauth.py         # refresh automatico (lock + atomic_rotate)
    token_store.py        # persistencia tokens en Mongo (singleton)
  meli/
    client.py             # httpx + Bearer + retry/backoff
    endpoints.py          # URLs MELI (items/locations/categories/packs)
    errors.py             # clasificacion + retryable() por status code
  listings/
    router.py             # endpoints CMS (webhook)
    service.py            # orquesta con MeliClient + persiste en store
    builder.py            # DTO -> JSON MELI
    schema.py             # Pydantic models validados
    store.py              # mapeo id_cms <-> item_id en Mongo
  locations/service.py    # helpers ubicaciones + ocultar direccion
  health/router.py        # /healthz, /readyz
  notifications/router.py # webhook MELI -> (items/quotations/leads)
mongo-init/01_indexes.js  # indices Mongo al arranque
tests/                    # pytest (schema, errors, endpoints)
```

## Endpoints

| Método | Ruta                              | Acción                                                            |
|--------|-----------------------------------|-------------------------------------------------------------------|
| POST   | `/listings`                       | Publica inmueble o desarrollo con variaciones → `POST /items`     |
| PUT    | `/listings/{id_cms}`              | Actualiza → `PUT /items/{item_id}` (retry en 409)                |
| GET    | `/listings/{id_cms}`              | Estado real → `GET /items/{item_id}`                              |
| POST   | `/listings/{id_cms}/upgrade`      | Cambia `listing_type_id` (silver→gold/gold_pro)                   |
| DELETE | `/listings/{id_cms}`              | Elimina de MELI (definitivo)                                       |
| POST   | `/meli/notifications`             | Webhook receptor de MELI (items/leads/quotations)                 |
| GET    | `/meli/notifications/list`        | Listado de notificaciones recibidas (debug)                       |
| GET    | `/healthz` `/readyz`              | Cloud Run healthchecks                                             |

Documentación interactiva: `http://localhost:8000/docs` (Swagger) y `/redoc`.

## Setup rápido (desarrollo local)

```bash
# 1. Crear venv e instalar dependencias
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configurar env vars
cp .env.example .env
# Editar .env con tus credenciales MELI (MELI_CLIENT_ID, MELI_CLIENT_SECRET, MELI_REFRESH_TOKEN, MELI_USER_ID)

# 3. Levantar con Docker (recomendado, levanta Mongo)
docker compose up --build

# 3b. O sin Docker (requiere Mongo en localhost:27017)
uvicorn app.main:app --reload --port 8000

# 4. Tests
pytest -v

# 5. Lint
ruff check app tests
```

## Flujo OAuth (solo `refresh_token`)

El microservicio **no implementa el flujo de autorización completo** (`/authorization`). Solo hace `refresh_token`:

1. **Primer arranque**: lee `MELI_REFRESH_TOKEN` desde env y lo persiste en `tokens` Mongo (singleton `_id=meli_account`).
2. **Cada request**: lee el access_token de Mongo. Si `expires_at < now`, llama `POST /oauth/token` con `grant_type=refresh_token`, persiste el nuevo par atomically (findAndModify condicional por `refresh_token` conocido — previene doble-refresh concurrente).
3. **401 invalid_token** desde MELI: fuerza un refresh `force_refresh()` y reintenta una vez la llamada original.

El `refresh_token` es **de uso único** → cada renovación devuelve uno nuevo que se persiste. Si no usas la app por 4 meses se invalida (regla MELI).

## Ejemplo: webhook de publicacion

```bash
curl -X POST http://localhost:8000/listings \
  -H "Content-Type: application/json" \
  -d @examples/publish_inmueble.json
```

Ver [`examples/publish_inmueble.json`](examples/publish_inmueble.json) y [`examples/publish_desarrollo.json`](examples/publish_desarrollo.json).

## Manejo de errores (de la guía API)

| Status | Detalle                                                                                       | Accion                                   |
|--------|----------------------------------------------------------------------------------------------|------------------------------------------|
| 400 `validation_error` | Atributos obligatorios ausentes (TOTAL_AREA, OPERATION, etc.) o JSON invalido | Pre-validamos con Pydantic: MELI no recibe el request |
| 400 error 173         | Sin imágenes (regla feb 2026 silver+)                          | Schema exige `min_length=1`              |
| 401 `invalid_token`   | Token expirado/invalido                        | Refresh + 1 reintento automatico         |
| 409 `optimistic_locking` | MELI aun procesa el item                       | Retry con backoff (3 intentos)           |
| 429 `too_many_requests` | Rate limit                                      | Backoff exponencial (3 intentos)         |
| 500 `internal_server_error` | Falla MELI                                  | Retry hasta 4 intentos                   |
| `pack_quota_exceeded` (substatus) | Cupo del paquete agotado          | Log warn + guarda estado en Mongo        |
| `seller.unable_to_list` | Validaciones pendientes en cuenta MELI          | HTTP 403 al CMS (request a soporte)      |

## Reglas implementadas (específicas México/MLM)

- `Site_id=MLM`, monedas `MXN`/`USD`
- `channels=["marketplace"]` (también aparecen en `metroscubicos.com` automáticamente)
- `listing_type_id` permitidos: `silver`, `gold`, `gold_pro` (NO `gold_premium`)
- `address_line` en formato `calle + número` (regla jul-2024, validado en schema)
- Imágenes en el mismo `POST /items` (regla feb-2026, mínimo 1)
- `available_quantity=1` (`classified`)
- `buying_mode="classified"`
- Verificación de recategorización automática MELI (oct-2025) en `get_status` (`recategorized: bool`)

## Deploy en GCP (Cloud Run + MongoDB Atlas)

1. Build & push a Artifact Registry:
   ```bash
   gcloud builds submit --tag <region>-docker.pkg.dev/<project>/meli-bridge:latest
   ```
2. Deploy a Cloud Run:
   ```bash
   gcloud run deploy meli-bridge \
     --image <region>-docker.pkg.dev/<project>/meli-bridge:latest \
     --region us-central1 \
     --port 8000 \
     --set-env-vars "MELI_SITE_ID=MLM,ENV=prod,LOG_LEVEL=INFO" \
     --set-secrets "MELI_CLIENT_ID=meli_client_id:latest,MELI_CLIENT_SECRET=meli_client_secret:latest,MELI_REFRESH_TOKEN=meli_refresh_token:latest,MONGO_URI=mongo_uri:latest"
   ```
3. MongoDB Atlas (M0 free tier) - suficient para 20 inmuebles. Whitelist de IP en Atlas.
4. Configura `MELI_REDIRECT_URI` en Dev Center (no se usa flujo OAuth aqui, pero documentado).

## To-do / Futuro

- [ ] Multiples cuentas (multi-vendedor): convertir `tokens` singleton en collection con `user_id` Int64 como PK
- [ ] Procesar notificaciones MELI (`items`, `leads_questions`): descomentar handler en `notifications/router.py` para refrescar `category_id` en Mongo cuando MELI recategorice
- [ ] Implementar cola dead-letter en retries fallidos (persistir en `listings.error`)
- [ ] Endpoint GET `/listings` con paginacion (listar todos los mapeos)
- [ ] Cachear catalogos MELI Mexico (categorías, ubicaciones, attributes required) en Mongo para acelerar validación
