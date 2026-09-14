#!/usr/bin/env python3
"""
Pedal Rio — coletor de clima v5.
Roda no GitHub Actions (~20h30 BRT). Busca Open-Meteo para 3 pontos do Rio,
extrai janela 4h-8h de AMANHA + nascer do sol + sensacao termica
+ umidade/visibilidade (risco de neblina) e grava config/clima-amanha.json.

v5 (13/09/2026): consulta VARIOS modelos (best_match, ECMWF, GFS, ICON, GEM)
e calcula `confianca` por divergencia de chuva na janela. Adiciona
`chuva_prob_largada_pct` (max 4h-6h). Campos novos sao ADITIVOS — todos os
campos da v4 continuam existindo com o mesmo significado.

Este arquivo DEVE ficar na raiz do repositorio (o workflow chama sem caminho).
"""
import urllib.request, json, datetime, zoneinfo

PONTOS = {
    "barra_recreio": {"lat": -23.02, "lon": -43.44, "nome": "Barra/Recreio"},
    "zona_sul":      {"lat": -22.97, "lon": -43.19, "nome": "Zona Sul"},
    "grumari":       {"lat": -23.05, "lon": -43.52, "nome": "Grumari"},
}

TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
HORAS_JANELA  = ["04:00", "05:00", "06:00", "07:00", "08:00"]
HORAS_LARGADA = ["04:00", "05:00", "06:00"]
HORAS_ANTES   = ["00:00", "01:00", "02:00", "03:00"]

# Modelos consultados para medir divergencia. best_match e o que a v4 usava
# (mantem os campos principais identicos). Os outros so alimentam `confianca`.
MODELOS = ["best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless"]
LIMIAR_CHUVA_MM = 0.5   # mm na janela que um modelo precisa somar para "ver chuva"

def graus_para_cardeal(g):
    if g is None: return "?"
    return ["N","NE","L","SE","S","SO","O","NO"][round(g / 45) % 8]

def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "PedalRio/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def coletar(lat, lon, forecast_days=2):
    """Chamada principal (best_match), identica a v4 — campos sem sufixo."""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&hourly=temperature_2m,apparent_temperature,relative_humidity_2m,"
           "visibility,precipitation_probability,precipitation,"
           "wind_speed_10m,wind_gusts_10m,wind_direction_10m"
           "&daily=sunrise,sunset"
           f"&timezone=America%2FSao_Paulo&forecast_days={forecast_days}")
    return _get(url)

def coletar_modelos(lat, lon, forecast_days=2):
    """Chamada multi-modelo: so precipitacao. Com varios modelos a Open-Meteo
    sufixa cada variavel com o nome do modelo (precipitation_gfs_seamless...)."""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&hourly=precipitation,precipitation_probability"
           f"&models={','.join(MODELOS)}"
           f"&timezone=America%2FSao_Paulo&forecast_days={forecast_days}")
    return _get(url)

def _idx(h, alvo, horas):
    return [i for i, t in enumerate(h["time"]) if t.split("T")[0]==alvo and t.split("T")[1] in horas]

def divergencia(data_modelos, alvo):
    """Le a resposta multi-modelo e devolve o bloco `modelos` + `confianca`.
    Tolerante: modelos sem dado (null) sao ignorados; se so 1 modelo responder,
    confianca = "indefinida" (o prompt trata como "media")."""
    h = data_modelos["hourly"]
    idx_j = _idx(h, alvo, HORAS_JANELA)
    idx_l = _idx(h, alvo, HORAS_LARGADA)
    detalhe = {}
    # chaves podem vir "precipitation_<modelo>" ou, se um unico modelo, "precipitation"
    chaves = [k for k in h if k.startswith("precipitation") and not k.startswith("precipitation_probability")]
    for k in chaves:
        nome = k[len("precipitation"):].lstrip("_") or "best_match"
        vals_j = [h[k][i] for i in idx_j if h[k][i] is not None]
        vals_l = [h[k][i] for i in idx_l if h[k][i] is not None]
        if not vals_j:
            continue
        kp = f"precipitation_probability_{nome}"
        if kp not in h and nome == "best_match":
            kp = "precipitation_probability"
        probs = [h[kp][i] for i in idx_j if kp in h and h[kp][i] is not None]
        detalhe[nome] = {
            "mm_janela": round(sum(vals_j), 2),
            "mm_largada": round(sum(vals_l), 2) if vals_l else None,
            "prob_max_pct": max(probs) if probs else None,
            "chove": sum(vals_j) >= LIMIAR_CHUVA_MM,
        }
    total = len(detalhe)
    com_chuva = sum(1 for d in detalhe.values() if d["chove"])
    if total < 2:
        conf = "indefinida"
    else:
        f = com_chuva / total
        if f == 0 or f == 1:            conf = "alta"    # unanimes
        elif f <= 0.25 or f >= 0.75:    conf = "media"   # um dissidente
        else:                            conf = "baixa"   # rachados
    mm_max = max((d["mm_janela"] for d in detalhe.values()), default=None)
    return {
        "modelos_total": total,
        "modelos_com_chuva": com_chuva,
        "chuva_mm_max_modelos": mm_max,
        "detalhe": detalhe,
    }, conf

def resumir(data, alvo):
    h = data["hourly"]
    idx_janela = _idx(h, alvo, HORAS_JANELA)
    idx_antes  = _idx(h, alvo, HORAS_ANTES)
    idx_larg   = _idx(h, alvo, HORAS_LARGADA)
    if not idx_janela:
        return None
    def med(c, idxs):
        v=[h[c][i] for i in idxs if h[c][i] is not None]; return round(sum(v)/len(v),1) if v else None
    def mx(c, idxs):
        v=[h[c][i] for i in idxs if h[c][i] is not None]; return max(v) if v else None
    def mn(c, idxs):
        v=[h[c][i] for i in idxs if h[c][i] is not None]; return min(v) if v else None
    dir_idx = idx_janela[len(idx_janela)//2]
    dir_g = h["wind_direction_10m"][dir_idx]
    prec_antes = sum(h["precipitation"][i] for i in idx_antes if h["precipitation"][i] is not None) if idx_antes else 0
    nascer = None
    if "daily" in data and "sunrise" in data["daily"]:
        for i, d in enumerate(data["daily"]["time"]):
            if d == alvo:
                nascer = data["daily"]["sunrise"][i].split("T")[1]
    sens_largada = mn("apparent_temperature", [i for i in idx_janela if h["time"][i].split("T")[1] in ["04:00","05:00"]])
    sens_final   = mx("apparent_temperature", [i for i in idx_janela if h["time"][i].split("T")[1] in ["07:00","08:00"]])
    # --- RISCO DE NEBLINA ---
    umid_max = mx("relative_humidity_2m", idx_janela)
    vis_min = mn("visibility", idx_janela)  # em metros
    vento_med = med("wind_speed_10m", idx_janela)
    risco_neblina = "baixo"
    if vis_min is not None and vis_min < 1000:
        risco_neblina = "alto"
    elif umid_max is not None and umid_max >= 95 and vento_med is not None and vento_med < 8:
        risco_neblina = "alto"
    elif umid_max is not None and umid_max >= 90 and vento_med is not None and vento_med < 10:
        risco_neblina = "medio"
    def r(x): return round(x) if x is not None else None
    return {
        "temp_min_c": r(mn("temperature_2m", idx_janela)),
        "temp_max_janela_c": r(mx("temperature_2m", idx_janela)),
        "temp_med_c": r(med("temperature_2m", idx_janela)),
        "sensacao_min_c": r(mn("apparent_temperature", idx_janela)),
        "sensacao_largada_c": r(sens_largada),
        "sensacao_final_c": r(sens_final),
        "umidade_max_pct": umid_max,
        "visibilidade_min_m": vis_min,
        "risco_neblina": risco_neblina,
        "chuva_prob_max_pct": mx("precipitation_probability", idx_janela),
        "chuva_prob_largada_pct": mx("precipitation_probability", idx_larg),
        "chuva_mm_total": round(sum(h["precipitation"][i] for i in idx_janela if h["precipitation"][i] is not None), 2),
        "chuva_mm_madrugada_antes": round(prec_antes, 2),
        "vento_med_kmh": vento_med,
        "rajada_max_kmh": mx("wind_gusts_10m", idx_janela),
        "vento_dir_graus": dir_g,
        "vento_dir_cardeal": graus_para_cardeal(dir_g),
        "nascer_do_sol": nascer,
    }

def coletar_ponto(chave, p, alvo, forecast_days=2):
    """Coleta completa de um ponto: best_match + divergencia multi-modelo.
    Reutilizado por atualizar_madrugada.py."""
    data = coletar(p["lat"], p["lon"], forecast_days)
    resumo = resumir(data, alvo)
    if resumo is None:
        return {"nome": p["nome"], "ok": False, "erro": "janela nao encontrada"}
    saida = {"nome": p["nome"], **resumo, "ok": True}
    try:
        modelos, conf = divergencia(coletar_modelos(p["lat"], p["lon"], forecast_days), alvo)
        saida["modelos"] = modelos
        saida["confianca"] = conf
    except Exception as e:
        saida["modelos"] = {"erro": str(e)}
        saida["confianca"] = "indefinida"
    return saida

def main():
    agora = datetime.datetime.now(TZ)
    amanha = (agora + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    saida = {"gerado_em": agora.isoformat(), "data_alvo": amanha,
             "fonte": "Open-Meteo", "versao_coletor": 5, "pontos": {}}
    for chave, p in PONTOS.items():
        try:
            saida["pontos"][chave] = coletar_ponto(chave, p, amanha)
        except Exception as e:
            saida["pontos"][chave] = {"nome": p["nome"], "ok": False, "erro": str(e)}
    # confianca geral = a pior entre os pontos (baixa < indefinida < media < alta)
    ordem = {"baixa": 0, "indefinida": 1, "media": 2, "alta": 3}
    confs = [pt.get("confianca") for pt in saida["pontos"].values() if pt.get("ok")]
    saida["confianca_geral"] = min(confs, key=lambda c: ordem.get(c, 1)) if confs else "indefinida"
    with open("config/clima-amanha.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(json.dumps(saida, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
