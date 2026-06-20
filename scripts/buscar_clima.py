#!/usr/bin/env python3

"""

Pedal Rio — coletor de clima.

Roda no GitHub Actions (que NAO tem o bloqueio de rede do ambiente da rotina).

Busca Open-Meteo para 3 pontos do Rio, extrai a janela 4h-8h de AMANHA

e grava config/clima-amanha.json no repositorio.

"""

import urllib.request, json, datetime, sys, zoneinfo

PONTOS = {

    "barra_recreio": {"lat": -23.02, "lon": -43.44, "nome": "Barra/Recreio"},

    "zona_sul":      {"lat": -22.97, "lon": -43.19, "nome": "Zona Sul"},

    "grumari":       {"lat": -23.05, "lon": -43.52, "nome": "Grumari"},

}

TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")

HORAS_JANELA = ["04:00", "05:00", "06:00", "07:00", "08:00"]

HORAS_ANTES  = ["00:00", "01:00", "02:00", "03:00"]  # para avaliar pista molhada

def graus_para_cardeal(g):

    if g is None: return "?"

    dirs = ["N","NE","L","SE","S","SO","O","NO"]

    return dirs[round(g / 45) % 8]

def coletar(lat, lon):

    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"

           "&hourly=temperature_2m,precipitation_probability,precipitation,"

           "wind_speed_10m,wind_gusts_10m,wind_direction_10m"

           "&timezone=America%2FSao_Paulo&forecast_days=2")

    req = urllib.request.Request(url, headers={"User-Agent": "PedalRio/1.0"})

    with urllib.request.urlopen(req, timeout=30) as r:

        return json.loads(r.read().decode())

def resumir(data, alvo):

    h = data["hourly"]

    idx_janela, idx_antes = [], []

    for i, t in enumerate(h["time"]):

        dia, hora = t.split("T")

        if dia == alvo and hora in HORAS_JANELA: idx_janela.append(i)

        if dia == alvo and hora in HORAS_ANTES:  idx_antes.append(i)

    if not idx_janela:

        return None

    def med(campo, idxs): 

        vals = [h[campo][i] for i in idxs if h[campo][i] is not None]

        return round(sum(vals)/len(vals), 1) if vals else None

    def mx(campo, idxs):

        vals = [h[campo][i] for i in idxs if h[campo][i] is not None]

        return max(vals) if vals else None

    # direcao do vento: pega a hora central (06:00) se houver, senao a primeira

    dir_idx = idx_janela[len(idx_janela)//2]

    dir_g = h["wind_direction_10m"][dir_idx]

    prec_antes = sum(h["precipitation"][i] for i in idx_antes if h["precipitation"][i] is not None) if idx_antes else 0

    return {

        "temp_min_c": min(h["temperature_2m"][i] for i in idx_janela),

        "temp_med_c": med("temperature_2m", idx_janela),

        "chuva_prob_max_pct": mx("precipitation_probability", idx_janela),

        "chuva_mm_total": round(sum(h["precipitation"][i] for i in idx_janela if h["precipitation"][i] is not None), 2),

        "chuva_mm_madrugada_antes": round(prec_antes, 2),

        "vento_med_kmh": med("wind_speed_10m", idx_janela),

        "rajada_max_kmh": mx("wind_gusts_10m", idx_janela),

        "vento_dir_graus": dir_g,

        "vento_dir_cardeal": graus_para_cardeal(dir_g),

    }

def main():

    amanha = (datetime.datetime.now(TZ) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    saida = {

        "gerado_em": datetime.datetime.now(TZ).isoformat(),

        "data_alvo": amanha,

        "fonte": "Open-Meteo",

        "pontos": {}

    }

    for chave, p in PONTOS.items():

        try:

            data = coletar(p["lat"], p["lon"])

            resumo = resumir(data, amanha)

            saida["pontos"][chave] = {"nome": p["nome"], **(resumo or {}), "ok": resumo is not None}

        except Exception as e:

            saida["pontos"][chave] = {"nome": p["nome"], "ok": False, "erro": str(e)}

    with open("config/clima-amanha.json", "w", encoding="utf-8") as f:

        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(json.dumps(saida, ensure_ascii=False, indent=2))

if __name__ == "__main__":

    main()
