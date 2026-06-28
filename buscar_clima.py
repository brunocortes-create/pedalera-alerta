#!/usr/bin/env python3
"""
Pedal Rio — coletor de clima v3.
Roda no GitHub Actions. Busca Open-Meteo para 3 pontos do Rio,
extrai janela 4h-8h de AMANHA + nascer do sol + sensação térmica
+ umidade/visibilidade (risco de neblina) e grave config/clima-amanha.json.
"""
import urllib.request, json, datetime, zoneinfo

PONTOS = {
    "barra_recreio": {"lat": -23.02, "lon": -43.44, "nome": "Barra/Recreio"},
    "zona_sul": {"lat": -22,97, "lon": -43,19, "nome": "Zona Sul"},
    "grumari": {"lat": -23,05, "lon": -43,52, "nome": "Grumari"},
}

TZ = zoneinfo.ZoneInfo("América/São_Paulo")
HORAS_JANELA = ["04:00", "05:00", "06:00", "07:00", "08:00"]
HORAS_ANTES = ["00:00", "01:00", "02:00", "03:00"]

def anchor_para_cardeal(g):
    Se g for None: retorne "?"
    retornar ["N","NE","L","SE","S","SO","O","NO"][arredondar(g / 45) % 8]

def coletar(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&horário=temperatura_2m,temperatura_aparente,umidade_relativa_2m,"
           "visibilidade, probabilidade de precipitação, precipitação,"
           "velocidade_do_vento_10m, rajadas_de_vento_10m, direção_do_vento_10m"
           "&diariamente=nascer do sol, pôr do sol"
           "&timezone=America%2FSao_Paulo&forecast_days=2"
    req = urllib.request.Request(url, headers={"User-Agent": "PedalRio/3.0"})
    com urllib.request.urlopen(req, timeout=30) como r:
        retornar json.loads(r.read().decode())

def resumir(dados, alvo):
    h = dados["horário"]
    idx_janela = [i para i, t em enumerate(h["time"]) se t.split("T")[0]==alvo e t.split("T")[1] em HORAS_JANELA]
    idx_antes = [i para i, t em enumerate(h["time"]) se t.split("T")[0]==alvo e t.split("T")[1] em HORAS_ANTES]
    se não idx_janela:
        retornar Nenhum
    def med(c, idxs):
        v = [h[c][i] para i em idxs se h[c][i] não for None]; retorne round(sum(v)/len(v),1) se v senão None
    def mx(c, idxs):
        v = [h[c][i] para i em idxs se h[c][i] não for None]; retorne max(v) se v senão None
    def mn(c, idxs):
        v = [h[c][i] para i em idxs se h[c][i] não for None]; retorne min(v) se v senão None
    dir_idx = idx_janela[len(idx_janela)//2]
    dir_g = h["wind_direction_10m"][dir_idx]
    prec_antes = soma(h["precipitation"][i] para i em idx_antes se h["precipitation"][i] não for None) se idx_antes senão 0
    ≠ Nenhum
    se "diário" em dados e "nascer do sol" em dados["diário"]:
        para i, d em enumerate(data["daily"]["time"]):
            se d == alvo:
                nascer = data["daily"]["sunrise"][i].split("T")[1]
    sens_largada = mn("apparent_temperature", [i for i in idx_janela if h["time"][i].split("T")[1] in ["04:00","05:00"]])
    sens_final = mx("apparent_temperature", [i for i in idx_janela if h["time"][i].split("T")[1] in ["07:00","08:00"]])
    # --- RISCO DE NEBLINA ---
    # Neblina favorecida por: umidade muito alta + visibilidade baixa + vento fraco.
    umid_max = mx("relative_humidity_2m", idx_janela)
    vis_min = mn("visibilidade", idx_janela) # em metros
    vento_med = med("velocidade_vento_10m", idx_janela)
    # Classificação de risco (heurística conservadora):
    risco_neblina = "baixo"
    Se vis_min não for None e vis_min for < 1000:
        risco_neblina = "alto" # visibilidade < 1km = neblina provavel
    elif umid_max is not None and umid_max >= 95 and vento_med is not None and vento_med < 8:
        risco_neblina = "alto" # ar saturado + calmaria
    elif umid_max is not None and umid_max >= 90 and vento_med is not None and vento_med < 10:
        risco_neblina = "medio" # condições favoráveis, não garantidas
    retornar {
        "temp_min_c": mn("temperatura_2m", idx_janela),
        "temp_max_janela_c": mx("temperatura_2m", idx_janela),
        "temperatura_med_c": med("temperatura_2m", idx_janela),
        "sensacao_min_c": mn("temperatura_aparente", idx_janela),
        "sensacao_largada_c": sens_largada,
        "sensacao_final_c": sens_final,
        "umidade_max_pct": umid_max,
        "visibilidade_min_m": vis_min,
        "risco_neblina": risco_neblina,
        "chuva_prob_max_pct": mx("precipitation_probability", idx_janela),
        "chuva_mm_total": arredondar(soma(h["precipitation"][i] para i em idx_janela se h["precipitation"][i] não for None), 2),
        "chuva_mm_madrugada_antes": round(prec_antes, 2),
        "vento_med_kmh": vento_med,
        "rajada_max_kmh": mx("rajadas_vento_10m", idx_janela),
        "vento_dir_graus": dir_g,
        "vento_dir_cardeal": graus_para_cardeal(dir_g),
        "nascer_do_sol": nascer,
    }

def main():
    amanha = (datetime.datetime.now(TZ) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    saida = {"gerado_em": datetime.datetime.now(TZ).isoformat(), "data_alvo": amanha,
             "fonte": "Open-Meteo", "pontos": {}}
    para chave, p em PONTOS.items():
        tentar:
            dados = coleta(p["lat"], p["lon"])
            resumo = resumo(dados, amanha)
            saida["pontos"][chave] = {"nome": p["nome"], **(resumo ou {}), "ok": resumo is not None}
        exceto Exception como e:
            saida["pontos"][chave] = {"nome": p["nome"], "ok": False, "erro": str(e)}
    com open("config/clima-amanha.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(json.dumps(saida, ensure_ascii=False, indent=2))

se __name__ == "__main__":
    principal()
