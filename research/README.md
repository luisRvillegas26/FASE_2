# Experimento de demanda para Opella

Implementación Python ejecutada con **datos sintéticos**, sin datos ni sistemas de Opella.
Complementa el reporte técnico, pero sus resultados se obtienen al ejecutar el código y
no se fuerzan a coincidir con las cifras ilustrativas del PDF.

## Ejecución

Entorno comprobado: Python 3.12.14, NumPy 2.3.5 y pandas 3.0.1.
En un entorno virtual con Python 3.12:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python experimento_demanda.py --seed 20261025 --output evidencia_nueva
```

En macOS/Linux, activar con `source .venv/bin/activate`.
El script no requiere red una vez instaladas las dependencias.
Usar otra carpeta de salida para conservar la evidencia entregada.

## Qué implementa

1. Panel de 36 series, 156 semanas, promociones, precios, estacionalidad, demanda y disponibilidad.
2. Regresión Ridge de cuatro salidas sobre log(1 + demanda), con inversión validada en unidades.
3. Regresión logística L2 mediante Newton/IRLS y comprobación de convergencia.
   El clasificador usa variables conocidas y oferta relativa; no usa predicciones de entrenamiento del Ridge.
4. Cinco folds temporales externos, validación interna para regularización y umbral,
   escalado ajustado solo al entrenamiento y purga de etiquetas de cuatro semanas.
5. Baseline anual estacional y alerta de insuficiencia de oferta.
6. MAE, RMSE, WAPE, sesgo, matriz de confusión, precisión, recall, F1,
   especificidad, AUC, Brier, log loss y métricas por horizonte y segmento.
7. Selección final de umbral con predicciones OOF de desarrollo, costos ilustrativos
   de FN/FP y capacidad máxima de alertas de 45% en validación.
8. Prueba final de orígenes 141–152, con etiquetas completas hasta semana 156.
9. A/B simulado con aleatorización dentro de 100 pares de grupos, bootstrap por pares,
   prueba de aleatorización bilateral, tamaño muestral aproximado y guardrail de inventario.
10. Pruebas numéricas de métricas, separación temporal, reconstrucción de métricas desde CSV
    e inferencia equivalente al recargar parámetros del modelo.

## Guía de archivos de evidencia

| Archivo | Contenido |
|---|---|
| RESULTADOS.md | Interpretación de resultados y limitaciones |
| configuracion_y_entorno.json | Semilla, versiones, variables, parámetros y resumen CV |
| panel_sintetico.csv | Datos semanales generados |
| dataset_modelado.csv | Variables y etiquetas por origen |
| validacion_cruzada.csv | Métricas de cada fold externo |
| fold_*_ridge_inner.csv | Experimentos con regularización Ridge |
| fold_*_umbrales_inner.csv | Búsquedas internas de umbral |
| fold_*_metricas.json | Evaluaciones completas por fold |
| predicciones_oof.csv | Predicciones externas de desarrollo |
| busqueda_umbral_oof.csv | Costos y factibilidad del umbral final |
| seleccion_final_ridge.csv | Regularización seleccionada sin prueba final |
| predicciones_prueba_final.csv | Valores reales, pronósticos, scores y decisiones |
| metricas_prueba_final.json | Resultados finales calculados |
| metricas_segmentos.csv | Error por producto, canal y región |
| roc_prueba_final.csv y .svg | Coordenadas y gráfica ROC |
| costo_umbral_oof.svg | Gráfica de costos de umbral |
| calibracion_prueba_final.csv | Probabilidad media y frecuencia por intervalo |
| ab_grupos.csv | Asignaciones y resultados agregados simulados |
| ab_replicas.csv | 10,000 réplicas bootstrap y de aleatorización |
| ab_resultados.json | Estimaciones, intervalos, p y guardrail |
| criterios_aceptacion.json | Criterios aprobados o incumplidos |
| modelos.npz | Parámetros y escalas, sin objetos pickle |
| verificacion_evidencia.json | Comprobaciones automáticas |
| reproducibilidad.json | Comparación de dos ejecuciones con la misma semilla |
| sha256.json | Integridad de archivos generados |

## Cómo leer el experimento

El pronóstico predice unidades; la alerta predice si la demanda acumulada supera la
oferta congelada. Son objetivos diferentes. Se usa un clasificador auxiliar independiente,
no una distribución probabilística derivada del Ridge.
No se aplica ROC directamente a unidades.

La demanda latente se conoce porque el panel es sintético. Se supone reconstrucción
perfecta de ventas perdidas para etiquetas y demanda histórica anual. En una operación
real este supuesto requiere una metodología de estimación y sensibilidad. Precios y
promociones de las siguientes cuatro semanas se suponen planes conocidos al emitir.
La oferta se genera sin consultar la demanda futura realizada.

El umbral OOF es una selección de política: el costo mínimo de su tabla no es una
evaluación insesgada del umbral elegido. Esa función corresponde a la prueba final.
Las desviaciones entre folds no son intervalos de confianza. Los horizontes se solapan.

En la semilla entregada el WAPE mejora, pero el sesgo absoluto incumple el límite de 5%.
Los umbrales internos también varían. No se usa la prueba final para corregir esos resultados.

El A/B tiene un efecto impuesto por un generador independiente. Verifica el procedimiento
estadístico; **no demuestra que el modelo entrenado reduzca faltantes**. Para demostrarlo,
sustituir los datos simulados por un piloto aleatorizado real con protocolo congelado.
Los costos de error son proxies ilustrativos, no ahorros demostrados.
La guardia de inventario no sustituye seguimiento de caducidad.

## Mapa del código

- `generate`: panel y variables sin futuro realizado en predictores.
- `Scaler`, `Ridge`, `Logistic`: algoritmos y preprocesamiento.
- `tune_inner`: selección temporal interna.
- `evaluate`, `forecast_metrics`, `classification_metrics`: evaluación.
- `threshold_search`: costo y capacidad operativa.
- `ab_experiment`: simulación y análisis de experimento por pares.
- `checks`, `main`: comprobaciones y orquestación.

Referencias metodológicas:
[Forecasting Principles and Practice](https://otexts.com/fpp3/),
[validación temporal](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html),
[métricas](https://scikit-learn.org/stable/modules/model_evaluation.html).
El código no depende de scikit-learn.

