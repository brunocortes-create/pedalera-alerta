#!/usr/bin/env python3
"""
Pedal Rio — coletor de clima v2.
Roda no GitHub Actions. Busca Open-Meteo para 3 pontos do Rio,
extrai janela 4h-8h de AMANHA + nascer do sol + sensacao termica
+ maxima da manha (para decidir roupa) e grava config/clima-amanha.json.
"""
import urllib.request, json, datetime, zoneinfo

PONTOS = {
    "barra_recreio": {"lat": -23.02, "lon": -43.44, "nome": "Barra/Recreio"},
    "zona_sul":      {"lat": -22.97, "lon": -43.19, "nome": "Zona Sul"},
    "grumari":       {"lat": -23.05, "lon": -43.52, "nome": "Grumari"},
}

TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
HORAS_JANELA = ["04:00", "05:00", "06:00", "07:00", "08:00"]
HORAS_ANTES  = ["00:00", "01:00", "02:00", "03:00"]

def graus_para_cardeal(g):
    if g is None: return "?"
    return ["N","NE","L","SE","S","SO","O","NO"][round(g / 45) % 8]

def coletar(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&hourly=temperature_2m,apparent_temperature,precipitation_probability,"
           "precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
           "&daily=sunrise,sunset"
           "&timezone=America%2FSao_Paulo&forecast_days=2")
    req = urllib.request.Request(url, headers={"User-Agent": "PedalRio/2.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def resumir(data, alvo):
    h = data["hourly"]
    idx_janela = [i for i, t in enumerate(h["time"]) if t.split("T")[0]==alvo and t.split("T")[1] in HORAS_JANELA]
    idx_antes  = [i for i, t in enumerate(h["time"]) if t.split("T")[0]==alvo and t.split("T")[1] in HORAS_ANTES]
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
    # nascer do sol do dia alvo
    nascer = None
    if "daily" in data and "sunrise" in data["daily"]:
        for i, d in enumerate(data["daily"]["time"]):
            if d == alvo:
                nascer = data["daily"]["sunrise"][i].split("T")[1]  # "06:34"
    # sensacao na largada (4h-5h) vs final (7h-8h) para tendencia
    sens_largada = mn("apparent_temperature", [i for i in idx_janela if h["time"][i].split("T")[1] in ["04:00","05:00"]])
    sens_final   = mx("apparent_temperature", [i for i in idx_janela if h["time"][i].split("T")[1] in ["07:00","08:00"]])
    return {
        "temp_min_c": mn("temperature_2m", idx_janela),
        "temp_med_c": med("temperature_2m", idx_janela),
        "sensacao_min_c": mn("apparent_temperature", idx_janela),
        "sensacao_largada_c": sens_largada,
        "sensacao_final_c": sens_final,
        "chuva_prob_max_pct": mx("precipitation_probability", idx_janela),
        "chuva_mm_total": round(sum(h["precipitation"][i] for i in idx_janela if h["precipitation"][i] is not None), 2),
        "chuva_mm_madrugada_antes": round(prec_antes, 2),
        "vento_med_kmh": med("wind_speed_10m", idx_janela),
        "rajada_max_kmh": mx("wind_gusts_10m", idx_janela),
        "vento_dir_graus": dir_g,
        "vento_dir_cardeal": graus_para_cardeal(dir_g),
        "nascer_do_sol": nascer,
    }

def main():
    amanha = (datetime.datetime.now(TZ) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    saida = {"gerado_em": datetime.datetime.now(TZ).isoformat(), "data_alvo": amanha,
             "fonte": "Open-Meteo", "pontos": {}}
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
