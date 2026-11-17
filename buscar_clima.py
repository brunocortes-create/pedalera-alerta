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

v5.1 (16/11/2026): a Open-Meteo passou a falhar de forma intermitente a partir
do GitHub Actions ("SSL handshake timed out" nos 3 pontos — 14/11 23h07,
15/11 23h23, 16/11 03h15 e 20h30), sempre em runners do oeste dos EUA
(westus2/westus3). Agora: (1) cada chamada tenta 3 vezes (espera 5 s e 15 s),
com corte rapido depois que a rede cai; (2) se TODOS os pontos falharem, nao
apaga a previsao boa da coleta principal (>= 20h da vespera) para o mesmo dia.
O workflow confere o resultado e, sem Open-Meteo, dispara nova execucao (outro
runner), ate 5 tentativas.

Este arquivo DEVE ficar na raiz do repositorio (o workflow chama sem caminho).
"""
import urllib.request, urllib.error, json, datetime, zoneinfo, time

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

TENTATIVAS = 3          # por chamada a Open-Meteo
ESPERAS_S = (5, 15)     # pausa antes da 2a e da 3a tentativa
_REDE = {"fora": False} # vira True quando uma chamada esgota as 3 tentativas

def _get(url, timeout=20):
    """GET com retentativa. Falha de rede, timeout (inclusive o handshake SSL),
    HTTP 429 ou 5xx -> tenta de novo. Outros HTTP 4xx (pedido errado) sobem na
    hora, sem repetir. Pior caso por chamada: 3 x 20 s + 20 s de pausa = 80 s.
    Corte rapido: depois que uma chamada esgota as tentativas, as seguintes
    tentam 1 vez so (ate alguma responder). Em 16/11 22h21 (runner westus3) as
    3 tentativas falharam nos 3 pontos — a falha e do runner, nao um soluco; o
    remedio e o workflow redisparar em outro runner, entao nao vale gastar
    4 min aqui."""
    ultimo = None
    tentativas = 1 if _REDE["fora"] else TENTATIVAS
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PedalRio/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = json.loads(r.read().decode())
            _REDE["fora"] = False
            return dados
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            ultimo = e
        except OSError as e:    # URLError, TimeoutError, ssl.SSLError, ConnectionError
            ultimo = e
        if n < tentativas - 1:
            time.sleep(ESPERAS_S[n])
    _REDE["fora"] = True
    raise RuntimeError(f"{ultimo} ({tentativas} tentativa{'s' if tentativas > 1 else ''})") from ultimo

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

ARQ_SAIDA = "config/clima-amanha.json"

def manter_arquivo_bom(saida, caminho=ARQ_SAIDA):
    """True quando esta coleta falhou em TODOS os pontos e o arquivo atual ja tem
    previsao boa para o MESMO dia, feita pela coleta principal (>= 20h da
    vespera). Nesse caso o arquivo fica como esta: o backup das ~23h nao pode
    apagar a previsao que o boletim das 21h usou. Uma previsao boa mais antiga
    (ex.: backup das ~10h) NAO e protegida — melhor a Routine abortar avisando
    do que publicar previsao velha sem aviso (doc 06, item 15)."""
    if any(p.get("ok") for p in saida["pontos"].values()):
        return False
    try:
        with open(caminho, encoding="utf-8") as f:
            atual = json.load(f)
        if atual.get("data_alvo") != saida["data_alvo"]:
            return False
        if not any(p.get("ok") for p in atual.get("pontos", {}).values()):
            return False
        gerado = datetime.datetime.fromisoformat(atual["gerado_em"])
        alvo = datetime.date.fromisoformat(saida["data_alvo"])
        limite = datetime.datetime.combine(alvo - datetime.timedelta(days=1),
                                           datetime.time(20, 0), TZ)
        return gerado >= limite
    except Exception:
        return False

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
    if manter_arquivo_bom(saida):
        print("Open-Meteo nao respondeu em nenhum ponto. Mantido o " + ARQ_SAIDA +
              " da coleta principal (mesmo data_alvo, gerado depois das 20h).")
        print(json.dumps(saida["pontos"], ensure_ascii=False, indent=2))
        return
    with open(ARQ_SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(json.dumps(saida, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
