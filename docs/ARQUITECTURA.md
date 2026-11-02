# Arquitectura y contrato del modelo

Cliente → FastAPI/Pydantic → escalado original → Ridge + logistica → JSON.
El proceso carga los parametros una sola vez al iniciar y verifica SHA-256. Si un
archivo no coincide, el servicio no inicia. No entrena ni descarga modelos en runtime.
NPZ se abre sin pickle. Las predicciones no se persisten ni se envian a terceros.

Ridge aplica `expm1([1, (x-media)/std] @ coef)` con limite inferior cero.
La logistica aplica sigmoid al predictor lineal con clipping [-35,35].
Alerta = probabilidad >= 0.28. Los modelos son independientes.
La respuesta conserva `synthetic=true` y `operationally_approved=false`.

## Entradas

El endpoint recibe variables YA transformadas, en el orden definido por metadata;
el JSON usa nombres, por lo que el orden de claves del cliente es irrelevante.
No es una API para ventas crudas. Debe existir una capa de preparacion de datos
antes de usarla con otra fuente. Definiciones del experimento:

| Variable | Definicion |
|---|---|
| log_reciente | log1p de la media de ventas/disponibilidad de las ultimas 4 semanas |
| tendencia | log((media reciente+1)/(media de las 4 semanas previas+1)) |
| log_anual | log1p de demanda media de las 4 semanas equivalentes del ano previo |
| sin_1, cos_1 | seno/coseno de 2*pi*(origen+2.5)/52 |
| sin_2, cos_2 | seno/coseno de 4*pi*(origen+2.5)/52 |
| promocion | media del indicador promocional planeado para las siguientes 4 semanas |
| log_precio_relativo | media del log del precio relativo planeado |
| log_escala | log de la escala sintetica de la serie; no estimada de datos reales |
| canal_farmacia, canal_ecommerce | indicadores C1 y C3; C2 es referencia |
| region_norte, region_sur | indicadores R1 y R3; R2 es referencia |
| disponibilidad | media de disponibilidad de las ultimas 4 semanas |
| log_oferta_relativa | log((oferta acumulada+1)/(4*media reciente+1)) |

Las etiquetas de canal/region son nombres del codigo, no correspondencias
verificadas con una estructura real de Opella. La demanda anual se supone reconstruida.
El cuerpo acepta entre 1 y 100 casos; cada caso produce 4 unidades semanales,
total acumulado, probabilidad de insuficiencia de oferta y decision de alerta.
Campos extra, categorias contradictorias y entradas fuera de limites se rechazan
con 422. Los limites son defensas numericas, no validacion de dominio real.

## Operacion

`PORT`, `LOG_LEVEL`, `MODEL_DIR` y `API_KEY` se configuran por entorno.
Compose publica solo en localhost. Con API_KEY vacia es una demo sin autenticacion.
Con API_KEY configurada, /v1/model y /v1/predict requieren X-API-Key.
Salud y OpenAPI permanecen accesibles; no contienen secretos. No se activa CORS.
En Cloud Run se requiere IAM y HTTPS. Para acceso mas amplio se necesita un gateway
con limites de cuerpo, cuotas y control de identidad. La validacion de lotes limita
casos, pero no reemplaza un limite de bytes del proxy.

Los logs de Uvicorn registran solicitudes y estado del servicio, no el cuerpo de
entrada. La imagen ejecuta como UID 10001, y Compose elimina capacidades y usa
filesystem de solo lectura. Cambiar modelos requiere una nueva imagen/version.
La integridad del manifiesto detecta cambios accidentales; no es una firma digital.

## Limites conservados

WAPE 15.41%, sesgo -5.48%; incumple el criterio de sesgo <5%.
Contenerizar no corrige ni valida el modelo con datos reales. No incluye reposicion,
reentrenamiento automatico ni evidencia causal: el A/B original es independiente.
Antes de uso operativo: validacion de datos, calibracion, nuevo holdout, monitoreo
de deriva, piloto real y seguimiento de caducidad.
