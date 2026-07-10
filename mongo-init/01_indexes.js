// mongo-init/01_indexes.js
// Crea indices al iniciar el contenedor de Mongo. Idempotente.

db = db.getSiblingDB("meli_bridge");

// Singleton de tokens (rotacion access_token / refresh_token MELI)
db.tokens.createIndex({ _id: 1 });

// Mapeo id_cms <-> item_id MELI
// Busquedas frecuentes por id_cms y por item_id
db.listings.createIndex({ id_cms: 1 }, { unique: true });
db.listings.createIndex({ item_id: 1 }, { unique: true, sparse: true });

// Log de webhooks (auditoria)
db.webhooks_log.createIndex({ ts: -1 });
db.webhooks_log.createIndex({ id_cms: 1, ts: -1 }, { sparse: true });
