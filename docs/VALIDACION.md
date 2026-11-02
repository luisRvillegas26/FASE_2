# Estado de validacion — 2 de noviembre de 2026

## Ejecutado y comprobado

- Python 3.12.14 y NumPy 2.3.5.
- 11 pruebas pytest aprobadas: `evidence/local-tests.xml`.
- Equivalencia de 432 probabilidades/decisiones y 1,728 pronosticos contra los
  CSV originales, tolerancia relativa 1e-12 para pronosticos.
- Salud, metadata, esquema OpenAPI, prediccion HTTP y error 422: seis pruebas
  HTTP aprobadas contra Uvicorn local; `evidence/http-smoke.json`.
- Autenticacion con API key y rechazo de campos/valores invalidos comprobados.
- Corrupcion de artefacto detectada antes de servir predicciones.
- `docker compose config` valido.
- Imagen Docker construida y contenedor ejecutado desde PowerShell del usuario.
  Evidencia: `evidence/docker-build.txt`, `docker-version.txt`, `image-inspect.json`
  y `container-inspect.json`.
- Integracion HTTP contra el contenedor: 6/6 comprobaciones aprobadas, incluyendo
  prediccion HTTP 200 y rechazo de lote vacio con HTTP 422.
  Respuestas completas en `evidence/container-http.json`; logs en `container.log`.
- El script retira el contenedor temporal al terminar; la imagen permanece local.

Docker mostro una advertencia al capturar el commit Git del build. No afecta al
resultado de build/inferencia. Para capturar procedencia Git, extraer o clonar el
proyecto en una ruta sin el segmento reservado `con` y construir desde un checkout
Git normal. `docker-attempt.txt` conserva el intento inicial bloqueado por el
aislamiento de la sesion, anterior a la validacion satisfactoria del usuario.

## Pendiente de comprobacion

- GitHub: cuenta destino `luisRvillegas26`; falta conexion/publicacion. Se entrega
  repositorio Git local y script de publicacion privada. No existe URL verificada.
- Actions: configurado, no ejecutado hasta publicar.
- Nube: scripts e instrucciones preparados; no se creo infraestructura.

Se observa una advertencia de deprecacion de la integracion Starlette/AnyIO en las
pruebas. No invalida las pruebas; evaluar actualizar dependencias en otro ciclo.
Las versiones transitivas estan fijadas para repetir este entorno.
