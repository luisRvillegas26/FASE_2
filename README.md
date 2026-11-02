# Opella: API de demanda y alerta de faltantes

Entrega de Actividad 1: codigo fuente, Dockerfile, configuracion, API y evidencia
de integracion. Proyecto academico basado exclusivamente en datos sinteticos.
El modelo conserva sus parametros originales; no esta aprobado para uso operativo.

## Inicio con Docker

Requisitos: Docker Desktop con motor Linux iniciado y acceso al daemon.
Desde la raiz:

```powershell
docker compose up --build -d
Invoke-RestMethod http://localhost:8080/health/ready
Invoke-RestMethod http://localhost:8080/v1/predict -Method Post -ContentType 'application/json' -Body (Get-Content examples/predict.json -Raw)
docker compose logs api
docker compose down
```

Documentacion interactiva: http://localhost:8080/docs
Contrato OpenAPI: http://localhost:8080/openapi.json
No se necesita un volumen de datos ni entrenamiento para iniciar.

## API

| Metodo | Endpoint | Funcion |
|---|---|---|
| GET | /health/live | Proceso disponible |
| GET | /health/ready | Modelo cargado |
| GET | /v1/model | Version, variables, metricas y criterios |
| POST | /v1/predict | Pronostico y alerta de 1 a 100 casos |
| GET | /docs | Swagger UI |
| GET | /openapi.json | Contrato machine-readable |

El ejemplo completo esta en `examples/predict.json`. Recibe variables transformadas
del experimento, no ventas crudas. Las definiciones y supuestos estan en
`docs/ARQUITECTURA.md`. El endpoint devuelve 4 valores semanales, total,
probabilidad, alerta, umbral y version del modelo.

Errores: 422 por datos invalidos, 401 por API key ausente/incorrecta cuando se
configura, 503 si el modelo no esta disponible. Si falla la integridad al iniciar,
el proceso termina y no expone un servicio listo.

## Desarrollo y pruebas sin Docker

Python 3.12 y acceso a PyPI:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q --junitxml=evidence/local-tests.xml
python -m app.serve
```

En otra terminal:

```powershell
python scripts/smoke.py
```

`API_KEY` es opcional en localhost; `.env.example` documenta configuracion.
Compose lee `.env`; al ejecutar Python directamente exportar variables en la shell.
No subir claves al repositorio.

## Validacion del contenedor

```powershell
.\scripts\validate-docker.ps1
```

Usa puerto 8081 para no interferir con el servidor local. Construye la imagen,
ejecuta el contenedor restringido, comprueba HTTP y exporta logs/inspect. Elimina
su contenedor temporal al terminar. No ejecutar si ya existe un contenedor llamado
`opella-demanda-validation`; renombrarlo o retirarlo primero.
GitHub Actions repite pruebas Python, build y smoke HTTP en Linux al hacer push.

## GitHub

Cuenta indicada: `luisRvillegas26`. Nombre propuesto: `opella-demanda-api`, privado.
El directorio se entrega como repositorio Git local. Para publicarlo con GitHub CLI:
Extraer primero el ZIP en una ruta habitual, por ejemplo
`C:\Users\lrvil\Documents\opella-demanda-api`: el directorio generado de este chat
incluye `con`, nombre reservado en Windows que puede impedir a Git operar.
El ZIP contiene el codigo versionado sin `.git`; inicializarlo al extraer:

```powershell
gh auth login
git init -b main
git add .
git commit -m "API de demanda con Docker y pruebas de integracion"
.\scripts\publish-github.ps1
```

El script requiere un commit existente y un nombre remoto libre. Si el repositorio
ya existe, configurar su URL como origin y hacer push en lugar de crearlo.
No hay URL verificada hasta completar la publicacion. Revisar Actions despues
del push y descargar el artefacto `integration-evidence`.

## Contenido

- `app/`: API, contrato Pydantic e inferencia NumPy.
- `model/`: parametros NPZ, metadata, metricas, criterios y hashes originales.
- `research/`: codigo completo original, README y dependencias de entrenamiento.
- `tests/`: equivalencia de los 432 casos, salud, contrato, autenticacion y errores.
- `examples/`: entrada reproducible.
- `scripts/`: validacion HTTP, Docker, GitHub y Cloud Run.
- `.github/workflows/ci.yml`: pipeline de integracion.
- `docs/`: arquitectura, nube y estado de validacion.
- `evidence/`: resultados reales de la validacion realizada.

Reproducir el experimento original:
instalar `research/requirements.txt` y ejecutar
`python research/experimento_demanda.py --output research/evidencia`.
No reemplazar artefactos del servicio sin validar una nueva version y regenerar
el manifiesto. Los archivos de referencia proceden de la evidencia original,
semilla 20261025, y permiten detectar cambios en resultados de inferencia.

La preparacion de nube esta en `docs/NUBE.md`; el estado exacto de las pruebas
esta en `docs/VALIDACION.md`. Un contenedor desplegable no acredita que el modelo
haya superado sus criterios de negocio.
