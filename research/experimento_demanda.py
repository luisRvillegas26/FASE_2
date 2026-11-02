"""Experimento reproducible de demanda para Opella. SOLO DATOS SINTETICOS.
Python >=3.10; numpy y pandas. Ejecutar: python experimento_demanda.py --output evidencia
Los algoritmos Ridge y logisticos se implementan con NumPy sin scikit-learn.
"""
from __future__ import annotations
import argparse, hashlib, json, platform, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 20261025
FEATURES = ["log_reciente", "tendencia", "log_anual", "sin_1", "cos_1",
            "sin_2", "cos_2", "promocion", "log_precio_relativo",
            "log_escala", "canal_farmacia", "canal_ecommerce", "region_norte",
            "region_sur", "disponibilidad"]
RISK_FEATURES = FEATURES + ["log_oferta_relativa"]
RIDGE_GRID = [0.1, 1.0, 10.0]
C_FN, C_FP = 1500.0, 200.0
# Costos residuales ilustrativos; no son costos internos de Opella.
MAX_ALERT_RATE = 0.45


def native(x):
    if isinstance(x, dict): return {str(k): native(v) for k,v in x.items()}
    if isinstance(x, (list, tuple)): return [native(v) for v in x]
    if isinstance(x, np.ndarray): return x.tolist()
    if isinstance(x, np.generic): return x.item()
    return x


def save_json(path, data):
    path.write_text(json.dumps(native(data), indent=2, ensure_ascii=False,
                               allow_nan=False), encoding="utf-8")


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


class Scaler:
    def fit(self, x):
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0)
        self.std[self.std < 1e-10] = 1
        return self

    def transform(self, x):
        z = (x - self.mean) / self.std
        return np.column_stack([np.ones(len(x)), z])


class Ridge:
    def __init__(self, alpha=1.0): self.alpha = alpha

    def fit(self, x, y):
        self.scaler = Scaler().fit(x)
        z = self.scaler.transform(x)
        penalty = np.eye(z.shape[1]) * self.alpha
        penalty[0, 0] = 0
        self.coef = np.linalg.solve(z.T @ z + penalty, z.T @ y)
        return self

    def predict(self, x):
        return self.scaler.transform(x) @ self.coef


class Logistic:
    """IRLS/Newton con regularizacion L2 y busqueda de paso.
    Objetivo: suma de log loss + alpha/2 * ||coef_sin_intercepto||^2.
    """
    def __init__(self, alpha=1.0): self.alpha = alpha

    def fit(self, x, y):
        self.scaler = Scaler().fit(x)
        z = self.scaler.transform(x)
        self.coef = np.zeros(z.shape[1])
        penalty = np.eye(z.shape[1]) * self.alpha
        penalty[0, 0] = 0
        def loss(b):
            v = z @ b
            return np.sum(np.logaddexp(0, v) - y*v) + .5*b @ penalty @ b
        self.converged = False
        for iteration in range(100):
            prob = sigmoid(z @ self.coef)
            weight = np.maximum(prob*(1-prob), 1e-7)
            grad = z.T @ (prob-y) + penalty @ self.coef
            hess = z.T @ (z * weight[:, None]) + penalty + np.eye(z.shape[1])*1e-8
            delta = np.linalg.solve(hess, grad)
            rate, old = 1.0, loss(self.coef)
            while rate > 1e-8:
                candidate = self.coef - rate*delta
                if loss(candidate) <= old + 1e-9: break
                rate *= .5
            self.coef = candidate
            if np.max(np.abs(rate*delta)) < 1e-7:
                self.converged = True
                break
        self.iterations = iteration+1
        if not self.converged:
            raise RuntimeError("La regresion logistica no convergio")
        return self

    def predict_proba(self, x):
        return sigmoid(self.scaler.transform(x) @ self.coef)


def generate(seed):
    """36 series: 4 productos x 3 regiones x 3 canales, 156 semanas.
    Venta observada censurada; demanda latente SOLO conocida por ser simulacion.
    Oferta es plan conocido, calculado sin utilizar demanda futura realizada.
    """
    rng = np.random.default_rng(seed)
    n, weeks = 36, 156
    product = np.repeat(np.arange(4), 9)
    region = np.tile(np.repeat(np.arange(3), 3), 4)
    channel = np.tile(np.arange(3), 12)
    scale = (85 + 35*product) * (1+.12*region) * (1-.13*channel)
    t = np.arange(1, weeks+1)
    promo = (rng.random((n,weeks)) < .16).astype(float)
    price = np.exp(rng.normal(0,.055,(n,weeks)) - .12*promo)
    seasonal = np.exp(.30*np.sin(2*np.pi*t/52)[None,:]
                      + .12*np.cos(4*np.pi*t/52)[None,:])
    expected = scale[:,None] * seasonal * np.exp(.30*promo-.65*np.log(price))
    expected *= (1+.001*t)[None,:]
    demand = rng.poisson(expected * np.exp(rng.normal(-.5*.13**2,.13,(n,weeks))))
    availability = np.where(rng.random((n,weeks)) < .10,
                            rng.uniform(.65,.90,(n,weeks)), 1.0)
    observed = np.floor(demand*availability).astype(int)
    # Las promociones/precios de cuatro semanas se suponen programados y conocidos.
    panel = pd.DataFrame([{
        "series_id":i,"producto":f"P{product[i]+1}","region":f"R{region[i]+1}",
        "canal":f"C{channel[i]+1}","semana":w+1,"demanda_latente":demand[i,w],
        "venta_observada":observed[i,w],"disponibilidad":availability[i,w],
        "promocion":promo[i,w],"precio_relativo":price[i,w]
    } for i in range(n) for w in range(weeks)])
    rows=[]
    for origin in range(56,153):
        k=origin-1
        future=np.arange(k+1,k+5)
        annual=demand[:,future-52]
        # Plan de suministro ruidoso y conocido al emitir. No usa el futuro real.
        supply=annual.sum(axis=1)*rng.uniform(.85,1.45,n)
        for i in range(n):
            # Correccion ilustrativa por disponibilidad; no garantiza recuperar demanda.
            recent=(observed[i,k-3:k+1] / availability[i,k-3:k+1]).mean()
            previous=(observed[i,k-7:k-3] / availability[i,k-7:k-3]).mean()
            ann=annual[i].mean()
            row=dict(series_id=i,producto=f"P{product[i]+1}",region=f"R{region[i]+1}",
                     canal=f"C{channel[i]+1}",origen=origin,etiqueta_hasta=origin+4,
                     oferta=supply[i])
            vals=[np.log1p(recent),np.log((recent+1)/(previous+1)),np.log1p(ann),
                  np.sin(2*np.pi*(origin+2.5)/52),np.cos(2*np.pi*(origin+2.5)/52),
                  np.sin(4*np.pi*(origin+2.5)/52),np.cos(4*np.pi*(origin+2.5)/52),
                  promo[i,future].mean(),np.log(price[i,future]).mean(),
                  np.log(scale[i]),float(channel[i]==0),float(channel[i]==2),
                  float(region[i]==0),float(region[i]==2),availability[i,k-3:k+1].mean()]
            row.update(zip(FEATURES,vals))
            row["log_oferta_relativa"]=np.log((supply[i]+1)/(4*recent+1))
            for h,j in enumerate(future,1):
                row[f"y{h}"]=float(demand[i,j])
                row[f"base{h}"]=float(demand[i,j-52])
            row["y_riesgo"]=int(demand[i,future].sum()>supply[i])
            rows.append(row)
    return panel,pd.DataFrame(rows)


def forecast_metrics(y,p):
    y,p=np.asarray(y).ravel(),np.asarray(p).ravel()
    e=p-y
    return {"n":len(y),"mae":float(np.mean(abs(e))),
            "rmse":float(np.sqrt(np.mean(e**2))),
            "wape":float(abs(e).sum()/y.sum()),
            "sesgo":float(e.sum()/y.sum())}


def confusion(y,p,t):
    pred=p>=t; y=np.asarray(y,dtype=bool)
    return dict(vp=int(np.sum(y&pred)),fn=int(np.sum(y&~pred)),
                fp=int(np.sum(~y&pred)),vn=int(np.sum(~y&~pred)))


def roc_points(y,p):
    # Agrupar empates y usar >= en cada umbral.
    order=np.argsort(-p,kind="stable"); yy=y[order]; pp=p[order]
    ends=np.r_[np.flatnonzero(np.diff(pp)!=0),len(pp)-1]
    tp=np.r_[0,np.cumsum(yy)[ends]]
    fp=np.r_[0,np.cumsum(1-yy)[ends]]
    return pd.DataFrame({"fpr":fp/(1-y).sum(),"tpr":tp/y.sum(),
                         "threshold":np.r_[np.inf,pp[ends]]})


def classification_metrics(y,p,t):
    c=confusion(y,p,t); vp,fn,fp,vn=[c[k] for k in ["vp","fn","fp","vn"]]
    recall=vp/max(1,vp+fn); specificity=vn/max(1,vn+fp)
    roc=roc_points(y,p)
    pr=np.clip(p,1e-10,1-1e-10)
    return {**c,"umbral":float(t),"exactitud":(vp+vn)/len(y),
            "precision":vp/max(1,vp+fp),"recall":recall,
            "especificidad":specificity,"f1":2*vp/max(1,2*vp+fp+fn),
            "exactitud_balanceada":(recall+specificity)/2,
            "auc":float(np.trapezoid(roc.tpr,roc.fpr)),
            "brier":float(np.mean((p-y)**2)),
            "log_loss":float(-np.mean(y*np.log(pr)+(1-y)*np.log(1-pr))),
            "prevalencia":float(y.mean()),"tasa_alertas":(vp+fp)/len(y),
            "costo_proxy":C_FN*fn+C_FP*fp}


def threshold_search(y,p):
    rows=[]
    for t in np.round(np.arange(.02,.981,.01),2):
        c=confusion(y,p,t); alerts=(c["vp"]+c["fp"])/len(y)
        rows.append({"threshold":t,**c,"alert_rate":alerts,
                     "cost":C_FN*c["fn"]+C_FP*c["fp"],
                     "feasible":alerts<=MAX_ALERT_RATE})
    tab=pd.DataFrame(rows)
    eligible=tab[tab.feasible]
    if eligible.empty: raise ValueError("Ningun umbral cumple capacidad")
    # Menor costo, luego menor numero de alertas, luego mayor umbral.
    best=eligible.sort_values(["cost","alert_rate","threshold"],
                             ascending=[True,True,False]).iloc[0]
    return float(best.threshold),tab


def xy(frame):
    return (frame[FEATURES].to_numpy(float),
            frame[[f"y{h}" for h in range(1,5)]].to_numpy(float),
            frame[RISK_FEATURES].to_numpy(float),
            frame.y_riesgo.to_numpy(int))


def fit_models(train,alpha):
    x,y,xr,yr=xy(train)
    return Ridge(alpha).fit(x,np.log1p(y)),Logistic().fit(xr,yr)


def predict(models,frame):
    x,_,xr,_=xy(frame)
    # Se valida expm1(log pred); no se interpreta como media insesgada.
    return np.maximum(0,np.expm1(models[0].predict(x))),models[1].predict_proba(xr)


def tune_inner(train):
    # Ultimos ocho origenes maduros: validacion interna; purga por horizonte.
    start=int(train.origen.max())-7
    fit=train[train.etiqueta_hasta<start]
    val=train[train.origen>=start]
    assert fit.etiqueta_hasta.max()<val.origen.min()
    x,y,_,_=xy(fit); xv,yv,_,yv_r=xy(val)
    trials=[]
    for alpha in RIDGE_GRID:
        m=Ridge(alpha).fit(x,np.log1p(y))
        pr=np.maximum(0,np.expm1(m.predict(xv)))
        trials.append({"alpha":alpha,**forecast_metrics(yv,pr)})
    best=min(trials,key=lambda r:r["wape"])["alpha"]
    models=fit_models(fit,best)
    _,prob=predict(models,val)
    threshold,thresholds=threshold_search(yv_r,prob)
    return best,threshold,trials,thresholds,start


def evaluate(models,frame,t):
    y=xy(frame)[1]; yr=frame.y_riesgo.to_numpy(int)
    pred,prob=predict(models,frame)
    base=frame[[f"base{h}" for h in range(1,5)]].to_numpy(float)
    base_alert=(base.sum(axis=1)>frame.oferta.to_numpy()).astype(float)
    # AUC de baseline binario se omite: solo un punto operativo.
    cls_base=classification_metrics(yr,base_alert,.5)
    for key in ["auc","brier","log_loss"]: cls_base.pop(key)
    metrics={"modelo":forecast_metrics(y,pred),"baseline":forecast_metrics(y,base),
             "alerta_modelo":classification_metrics(yr,prob,t),
             "alerta_baseline":cls_base,
             "por_horizonte":{f"h{h+1}":forecast_metrics(y[:,h],pred[:,h]) for h in range(4)},
             "acumulado_4_semanas":forecast_metrics(y.sum(axis=1),pred.sum(axis=1))}
    evidence=frame[["series_id","producto","region","canal","origen","etiqueta_hasta","oferta","y_riesgo"]].copy()
    for h in range(4):
        evidence[f"real_h{h+1}"]=y[:,h]
        evidence[f"pred_h{h+1}"]=pred[:,h]
        evidence[f"base_h{h+1}"]=base[:,h]
    evidence["probabilidad"]=prob
    evidence["umbral"]=t
    evidence["alerta"]=(prob>=t).astype(int)
    evidence["alerta_base"]=base_alert.astype(int)
    return metrics,evidence


def ab_experiment(seed):
    """Simula experimento por pares de conglomerados. No usa predicciones ML.
    Es prueba del procedimiento estadistico, no prueba causal del modelo entrenado.
    """
    rng=np.random.default_rng(seed+10)
    pairs,weeks=100,12
    common=rng.uniform(.06,.11,pairs)
    records=[]
    for pair in range(pairs):
        treated=int(rng.integers(2))
        for cluster in range(2):
            arm=int(cluster==treated)
            # Beneficio impuesto por el generador, no aprendido del forecast.
            p0=float(np.clip(common[pair]+rng.normal(0,.008),.01,.20))
            prob=p0*(.75 if arm else 1)
            days=int(rng.binomial(7*weeks,prob))
            inv=100*(1+.03*arm)+rng.normal(0,1)
            records.append(dict(pair=pair,cluster=2*pair+cluster,tratamiento=arm,
                                dias_faltante=days,dias_totales=7*weeks,
                                proporcion_faltante=days/(7*weeks),inventario=inv))
    frame=pd.DataFrame(records)
    wide=frame.pivot(index="pair",columns="tratamiento",values="proporcion_faltante")
    delta=(wide[1]-wide[0]).to_numpy()
    n_boot=10000
    idx=rng.integers(0,pairs,(n_boot,pairs))
    boot=delta[idx].mean(axis=1)
    signs=rng.choice([-1,1],size=(n_boot,pairs))
    perm=(signs*delta).mean(axis=1)
    pval=(1+np.sum(abs(perm)>=abs(delta.mean())))/(n_boot+1)
    inv=frame.pivot(index="pair",columns="tratamiento",values="inventario")
    inv_a,inv_b=inv[0].to_numpy(),inv[1].to_numpy()
    inv_boot=(inv_b[idx].mean(axis=1)/inv_a[idx].mean(axis=1)-1)
    means=frame.groupby("tratamiento").proporcion_faltante.mean()
    ci=np.quantile(boot,[.025,.975]); ici=np.quantile(inv_boot,[.025,.975])
    summary={"naturaleza":"simulacion independiente con efecto impuesto; no valida el modelo",
             "pares":pairs,"grupos_por_brazo":pairs,"semanas":weeks,
             "control":float(means[0]),"tratamiento":float(means[1]),
             "diferencia_absoluta":float(delta.mean()),
             "reduccion_relativa":float(1-means[1]/means[0]),
             "ic95_bootstrap_pares":ci,"p_aleatorizacion_bilateral":float(pval),
             "inventario_incremento_relativo":float(inv_b.mean()/inv_a.mean()-1),
             "ic95_inventario":ici,
             "guardrail_inventario_5pct":bool(ici[1]<.05),
             "n_aproximado_por_brazo_para_2pp_sd4pp":
                 int(np.ceil(2*(1.96+.8416)**2*.04**2/.02**2)),
             "decision":"No desplegar: simulacion y sin seguimiento real de caducidad"}
    return frame,summary,pd.DataFrame({"replica":np.arange(n_boot),
                                     "diferencia_bootstrap":boot,"diferencia_permutada":perm})


def svg_line(path,frame,xcol,ycol,title,xlabel,ylabel):
    from html import escape
    xx=frame[xcol].to_numpy(); yy=frame[ycol].to_numpy()
    xmax=max(float(xx.max()),1e-9); ymax=max(float(yy.max()),1e-9)
    points=" ".join(f"{65+620*x/xmax:.2f},{330-270*y/ymax:.2f}" for x,y in zip(xx,yy))
    content=f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="410" viewBox="0 0 760 410"><rect width="760" height="410" fill="white"/><g font-family="Arial" fill="#172b3a"><text x="65" y="28" font-size="19">{escape(title)}</text><text x="280" y="395">{escape(xlabel)}</text><text x="65" y="49">{escape(ylabel)}</text><path d="M65 60 V330 H685" fill="none" stroke="#555"/><polyline points="{points}" fill="none" stroke="#246480" stroke-width="2"/>'
    for i in range(6):
        content+=f'<text x="{65+124*i}" y="354" font-size="11">{xmax*i/5:.2f}</text><text x="8" y="{334-54*i}" font-size="11">{ymax*i/5:.2f}</text>'
    path.write_text(content+'</g></svg>',encoding="utf-8")


def checks():
    y=np.array([1,1,0,0]); p=np.array([.9,.8,.4,.1])
    m=classification_metrics(y,p,.5)
    assert m["vp"]==2 and m["vn"]==2 and m["auc"]==1
    assert abs(classification_metrics(y,np.ones(4)*.5,.5)["auc"]-.5)<1e-12
    fm=forecast_metrics([100,200,150,50],[110,180,160,50])
    assert fm["mae"]==10 and abs(fm["wape"]-.08)<1e-12
    assert abs(fm["rmse"]-np.sqrt(150))<1e-12
    rng=np.random.default_rng(9); x=rng.normal(size=(50,3))
    target=3+x@np.array([1,2,-1])
    assert np.max(abs(Ridge(0).fit(x,target).predict(x)-target))<1e-10


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path(__file__).parent/"evidencia")
    parser.add_argument("--seed",type=int,default=SEED)
    args=parser.parse_args(); out=args.output; out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter(); checks()
    panel,data=generate(args.seed)
    panel.to_csv(out/"panel_sintetico.csv",index=False)
    data.to_csv(out/"dataset_modelado.csv",index=False)
    folds=[(85,92),(97,104),(109,116),(121,128),(129,136)]
    cv_rows=[]; oof=[]
    for fold,(start,end) in enumerate(folds,1):
        train=data[data.etiqueta_hasta<start]
        val=data[data.origen.between(start,end)]
        assert train.etiqueta_hasta.max()<val.origen.min()
        alpha,t,trials,thresholds,inner=tune_inner(train)
        pd.DataFrame(trials).to_csv(out/f"fold_{fold}_ridge_inner.csv",index=False)
        thresholds.to_csv(out/f"fold_{fold}_umbrales_inner.csv",index=False)
        models=fit_models(train,alpha)
        metrics,evidence=evaluate(models,val,t)
        save_json(out/f"fold_{fold}_metricas.json",metrics)
        evidence["fold"]=fold; oof.append(evidence)
        cv_rows.append(dict(fold=fold,inicio=start,fin=end,n_train=len(train),
                            n_valid=len(val),max_etiqueta_train=int(train.etiqueta_hasta.max()),
                            inner_start=inner,alpha=alpha,umbral=t,
                            wape_modelo=metrics["modelo"]["wape"],
                            wape_base=metrics["baseline"]["wape"],
                            auc=metrics["alerta_modelo"]["auc"],
                            recall=metrics["alerta_modelo"]["recall"],
                            precision=metrics["alerta_modelo"]["precision"],
                            costo=metrics["alerta_modelo"]["costo_proxy"]))
    cv=pd.DataFrame(cv_rows); cv.to_csv(out/"validacion_cruzada.csv",index=False)
    oof=pd.concat(oof,ignore_index=True); oof.to_csv(out/"predicciones_oof.csv",index=False)
    # Umbral de politica final solo con predicciones OOF de desarrollo.
    threshold,tab=threshold_search(oof.y_riesgo.to_numpy(),oof.probabilidad.to_numpy())
    tab.to_csv(out/"busqueda_umbral_oof.csv",index=False)
    train=data[data.etiqueta_hasta<141]
    final_alpha,_,trials,_,_=tune_inner(train)
    pd.DataFrame(trials).to_csv(out/"seleccion_final_ridge.csv",index=False)
    test=data[data.origen.between(141,152)]
    assert train.etiqueta_hasta.max()<test.origen.min()
    assert test.etiqueta_hasta.max()<=156
    models=fit_models(train,final_alpha)
    metrics,pred=evaluate(models,test,threshold)
    save_json(out/"metricas_prueba_final.json",metrics)
    pred.to_csv(out/"predicciones_prueba_final.csv",index=False)
    roc=roc_points(pred.y_riesgo.to_numpy(),pred.probabilidad.to_numpy())
    roc.to_csv(out/"roc_prueba_final.csv",index=False)
    svg_line(out/"roc_prueba_final.svg",roc,"fpr","tpr","ROC en prueba final sintetica","Falsos positivos","Sensibilidad")
    svg_line(out/"costo_umbral_oof.svg",tab,"threshold","cost","Costo proxy en validacion OOF","Umbral","Costo MXN")
    calib=pd.DataFrame({"real":pred.y_riesgo,"prob":pred.probabilidad})
    calib["bin"]=pd.cut(calib.prob,bins=np.linspace(0,1,11),include_lowest=True)
    calib.groupby("bin",observed=True).agg(n=("real","size"),prob_media=("prob","mean"),frecuencia=("real","mean")).to_csv(out/"calibracion_prueba_final.csv")
    seg=[]
    for column in ["region","canal","producto"]:
        for group,part in pred.groupby(column):
            yy=part[[f"real_h{h}" for h in range(1,5)]].to_numpy()
            pp=part[[f"pred_h{h}" for h in range(1,5)]].to_numpy()
            seg.append({"dimension":column,"segmento":group,**forecast_metrics(yy,pp)})
    pd.DataFrame(seg).to_csv(out/"metricas_segmentos.csv",index=False)
    frame,ab,replicas=ab_experiment(args.seed)
    frame.to_csv(out/"ab_grupos.csv",index=False)
    replicas.to_csv(out/"ab_replicas.csv",index=False)
    save_json(out/"ab_resultados.json",ab)
    # Persistencia parametrica segura, sin pickle.
    np.savez(out/"modelos.npz",ridge_coef=models[0].coef,ridge_mean=models[0].scaler.mean,
             ridge_std=models[0].scaler.std,logistic_coef=models[1].coef,
             logistic_mean=models[1].scaler.mean,logistic_std=models[1].scaler.std)
    stored=np.load(out/"modelos.npz")
    xt=xy(test)[0]; xrt=xy(test)[2]
    zr=np.column_stack([np.ones(len(xt)),(xt-stored["ridge_mean"])/stored["ridge_std"]])
    zl=np.column_stack([np.ones(len(xrt)),(xrt-stored["logistic_mean"])/stored["logistic_std"]])
    assert np.allclose(np.maximum(0,np.expm1(zr@stored["ridge_coef"])),
                       pred[[f"pred_h{h}" for h in range(1,5)]].to_numpy())
    assert np.allclose(sigmoid(zl@stored["logistic_coef"]),pred.probabilidad)
    gates={"mejora_wape_relativa_minima_15pct":
           bool(1-metrics["modelo"]["wape"]/metrics["baseline"]["wape"]>=.15),
           "sesgo_absoluto_menor_5pct":bool(abs(metrics["modelo"]["sesgo"])<.05),
           "datos_reales_validados":False,"piloto_real_completado":False,
           "despliegue_aprobado":False}
    save_json(out/"criterios_aceptacion.json",gates)
    cv_summary={col:{"media":float(cv[col].mean()),"sd_entre_folds":float(cv[col].std(ddof=1))}
                for col in ["wape_modelo","wape_base","auc","recall"]}
    meta={"seed":args.seed,"utc":datetime.now(timezone.utc).isoformat(),
          "python":sys.version,"numpy":np.__version__,"pandas":pd.__version__,
          "plataforma":platform.platform(),"features":FEATURES,"risk_features":RISK_FEATURES,
          "ridge_alpha":final_alpha,"umbral_final_oof":threshold,
          "max_alert_rate_validacion":MAX_ALERT_RATE,"cost_fn":C_FN,"cost_fp":C_FP,
          "n_train_final":len(train),"n_test":len(test),"cv_resumen":cv_summary,
          "logistic_converged":models[1].converged,"logistic_iterations":models[1].iterations,
          "segundos":time.perf_counter()-started,"checks":"passed"}
    save_json(out/"configuracion_y_entorno.json",meta)
    # Comprobacion independiente de evidencia CSV exportada.
    reopened=pd.read_csv(out/"predicciones_prueba_final.csv")
    recomputed=classification_metrics(reopened.y_riesgo.to_numpy(),reopened.probabilidad.to_numpy(),threshold)
    for key in ["vp","fp","fn","vn","auc","brier"]:
        assert np.isclose(recomputed[key],metrics["alerta_modelo"][key])
    save_json(out/"verificacion_evidencia.json",{"metricas_recalculadas_desde_csv":True,
                                               "pruebas_unitarias_minimas":True,
                                               "separacion_temporal":True,"inferencia_modelos_recargados":True})
    improvement=1-metrics["modelo"]["wape"]/metrics["baseline"]["wape"]
    report=f"""# Resultados de ejecucion con datos sinteticos

No son datos ni resultados de Opella. No se fuerzan a coincidir con el reporte PDF.
El generador conoce demanda latente completa: entrenamiento y evaluacion suponen
demanda perdida reconstruida perfectamente. En datos reales este supuesto no se cumple
automaticamente y puede sobrestimar el desempeno. Las variables recientes usan ventas
y disponibilidad; la demanda anual historica se supone reconstruida. Promociones y
precios futuros se consideran planes conocidos. Oferta se calcula sin demanda futura real.

## Prueba final intacta
- Registros: {len(test)}; origenes 141 a 152; etiquetas observadas hasta 156.
- WAPE ML: {metrics['modelo']['wape']:.2%}; baseline: {metrics['baseline']['wape']:.2%}.
- Mejora relativa WAPE: {improvement:.2%}.
- MAE: {metrics['modelo']['mae']:.2f}; RMSE: {metrics['modelo']['rmse']:.2f}.
- Sesgo: {metrics['modelo']['sesgo']:.2%}.
- Umbral seleccionado OOF: {threshold:.2f}; AUC final: {metrics['alerta_modelo']['auc']:.4f}.
- Precision: {metrics['alerta_modelo']['precision']:.2%}; recall: {metrics['alerta_modelo']['recall']:.2%}.
- Matriz: VP {metrics['alerta_modelo']['vp']}, FN {metrics['alerta_modelo']['fn']},
  FP {metrics['alerta_modelo']['fp']}, VN {metrics['alerta_modelo']['vn']}.
- Costo proxy: MXN {metrics['alerta_modelo']['costo_proxy']:,.0f}.
- Brier: {metrics['alerta_modelo']['brier']:.4f}.

## Validacion
Cinco folds externos con ajuste interno temporal y purga de etiquetas inmaduras.
Los umbrales propios de cada fold se eligen solo dentro de su entrenamiento.
El umbral final se selecciona con probabilidades externas OOF de desarrollo.
El costo OOF minimo es una cifra de seleccion, no una estimacion insesgada de ese umbral.
La prueba final se consulta despues de congelar modelo y politica.
Las desviaciones entre folds no son intervalos de confianza.
Ridge predice log(1+demanda); la inversion sin correccion de retransfomacion no es
una estimacion insesgada de la media: se valida en unidades y se reporta el sesgo.

## Criterios y estabilidad
Mejora relativa WAPE >= 15%: {gates['mejora_wape_relativa_minima_15pct']}.
Sesgo absoluto < 5%: {gates['sesgo_absoluto_menor_5pct']}.
Sesgo observado: {metrics['modelo']['sesgo']:.2%}.
No se reajusta el modelo usando la prueba final; cualquier correccion exige un
nuevo ciclo de desarrollo y otra prueba intacta.
Los umbrales internos de folds varian fuertemente: revisar calibracion, ventanas
y prevalencia antes de convertir alertas en decisiones. Consultar criterios_aceptacion.json.
No hay aprobacion de despliegue aunque el AUC sintetico sea alto.

## A/B independiente simulado
- Control: {ab['control']:.2%}; tratamiento: {ab['tratamiento']:.2%}.
- Diferencia: {100*ab['diferencia_absoluta']:.2f} puntos porcentuales.
- IC bootstrap por pares: [{100*ab['ic95_bootstrap_pares'][0]:.2f}, {100*ab['ic95_bootstrap_pares'][1]:.2f}] puntos.
- p bilateral de aleatorizacion: {ab['p_aleatorizacion_bilateral']:.4f}.
El generador impone el efecto del tratamiento. Este experimento comprueba la
implementacion del analisis A/B, NO demuestra impacto causal del modelo entrenado.
No hay seguimiento de caducidad ni ahorro real. No desplegar con esta evidencia.

## Alcance
Los costos son supuestos residuales, no flujo de caja. La restriccion de alertas solo
rige validacion; puede incumplirse en prueba o produccion. No se ejecuta reposicion.
No se calculan intervalos de error predictivo con independencia ficticia entre filas:
los horizontes se solapan. Se requiere bootstrap por bloques temporales para inferencia.
No se demuestra generalizacion a nuevos productos, paises o temporadas no simuladas.
"""
    (out/"RESULTADOS.md").write_text(report,encoding="utf-8")
    files=[Path(__file__),*sorted(out.glob("*"))]
    manifest={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in files if p.is_file() and p.name!="sha256.json"}
    save_json(out/"sha256.json",manifest)
    print(json.dumps(native({"wape":metrics["modelo"]["wape"],"baseline_wape":metrics["baseline"]["wape"],
                             "auc":metrics["alerta_modelo"]["auc"],"threshold":threshold,
                             "ab_p":ab["p_aleatorizacion_bilateral"],"output":str(out)}),indent=2))


if __name__=="__main__":
    main()

