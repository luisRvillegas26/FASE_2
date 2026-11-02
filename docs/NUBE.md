# Preparacion de despliegue: Google Cloud Run

Ruta elegida para esta entrega: contenedor Linux/amd64 en Artifact Registry y
servicio privado en Cloud Run. Este documento prepara el despliegue; no acredita
recursos creados ni un endpoint en nube. Ejecutar genera consumo facturable.

1. Tener proyecto con facturacion, Docker y gcloud autenticados. Elegir region
   permitida por la organizacion. El valor del script es solo un ejemplo.
2. Habilitar servicios y crear el repositorio una sola vez:

```powershell
gcloud auth login
gcloud services enable run.googleapis.com artifactregistry.googleapis.com --project TU_PROYECTO
gcloud artifacts repositories create opella --repository-format=docker --location=us-central1 --project TU_PROYECTO
```

3. El usuario de despliegue requiere permisos para publicar imagenes, administrar
   Cloud Run y usar su cuenta de servicio. Alinear IAM con la politica del proyecto;
   la API no necesita permisos de acceso a datos o a otros servicios.
4. Desde la raiz del repositorio, construir, publicar y desplegar:

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId TU_PROYECTO -Tag v1.0.0
```

El proceso falla si falla cualquier paso. Mantiene el servicio privado, maximo
2 instancias y escucha 0.0.0.0 en PORT. No incluye credenciales en la imagen.
Si el servicio ya existia con permisos publicos, revisar y retirar sus bindings
`allUsers`/`allAuthenticatedUsers`: no asumir que un flag revoca toda politica previa.

5. Validar acceso autorizado:

```powershell
$url = gcloud run services describe opella-demanda-demo --region us-central1 --project TU_PROYECTO --format='value(status.url)'
$token = gcloud auth print-identity-token
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "$url/health/ready" -Headers $headers
Invoke-RestMethod "$url/v1/predict" -Method Post -Headers $headers -ContentType 'application/json' -Body (Get-Content examples/predict.json -Raw)
```

Registrar URL, revision, digest de imagen, commit, fecha, HTTP y logs. Verificar que
una solicitud sin token no pueda usar la API. Abrir `/docs` requiere acceso IAM;
para probar en navegador se puede usar `gcloud run services proxy` autenticado.

Rollback: listar revisiones con `gcloud run revisions list`, y asignar 100% del
trafico a la revision anterior con `gcloud run services update-traffic`.
Eliminar la demo al terminar: `gcloud run services delete opella-demanda-demo` con
proyecto y region; revisar tambien imagenes almacenadas en Artifact Registry.

Referencias oficiales:
- https://docs.cloud.google.com/run/docs/reference/container-contract
- https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy
- https://docs.cloud.google.com/run/docs/configuring/services/environment-variables
- https://fastapi.tiangolo.com/deployment/docker/
