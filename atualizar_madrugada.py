#!/usr/bin/env python3
"""
Pedal Rio — atualizacao da madrugada (roda ~03h15 BRT no GitHub Actions).

Re-consulta a Open-Meteo para HOJE (janela 4h-8h, ~1h de antecedencia em vez
de ~9h), tenta ler chuva MEDIDA nos pluviometros do Alerta Rio (0h-3h), compara
com o que o boletim da vespera previu (config/clima-amanha.json) e grava
docs/atualizacao.json com um veredito DETERMINISTICO — sem LLM, sem narrativa.

A pagina (docs/index.html) mostra este arquivo em destaque quando data_alvo
bate com a do boletim. Nunca derruba nada: qualquer falha vira status
"indisponivel" com a causa registrada.

Este arquivo DEVE ficar na raiz (importa buscar_clima da mesma pasta).
"""
import json, datetime, zoneinfo, urllib.request, re, sys
import buscar_clima as bc

TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
ARQ_VESPERA = "config/clima-amanha.json"
ARQ_SAIDA   = "docs/atualizacao.json"

# Pluviometros do Alerta Rio mais proximos de cada ponto (nomes como aparecem
# no sistema; casamento por substring, sem acento e sem caixa).
ESTACOES = {
    "barra_recreio": ["recreio", "barra/barrinha", "barrinha", "barra/riocentro", "riocentro"],
    "zona_sul":      ["copacabana", "jardim botanico", "vidigal", "laranjeiras"],
    "grumari":       ["grota funda", "guaratiba", "recreio"],
}
URLS_ALERTA_RIO = [
    "https://alertario.rio.rj.gov.br/upload/Chuvas.json",
    "http://alertario.rio.rj.gov.br/upload/Chuvas.json",
    "https://websempre.rio.rj.gov.br/json/chuvas",
]

def _norm(s):
    s = s.lower()
    for a, b in (("á","a"),("à","a"),("ã","a"),("â","a"),("é","e"),("ê","e"),("í","i"),("ó","o"),("õ","o"),("ô","o"),("ú","u"),("ç","c")):
        s = s.replace(a, b)
    return s

def ler_alerta_rio():
    """Best-effort. Devolve {chave_ponto: {"estacao": nome, "mm_3h": x, "mm_1h": y}} ou {"erro": ...}.
    O formato do feed nao e documentado oficialmente; o parser e tolerante e,
    se nao reconhecer nada, devolve erro em vez de inventar."""
    ultimo_erro = "nenhuma URL respondeu"
    for url in URLS_ALERTA_RIO:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PedalRio/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                bruto = r.read().decode("utf-8", "ignore")
            dados = json.loads(bruto)
            # formatos vistos historicamente: {"objects":[...]} ou lista direta
            lista = dados.get("objects") if isinstance(dados, dict) else dados
            if not isinstance(lista, list) or not lista:
                ultimo_erro = f"{url}: estrutura inesperada"
                continue
            saida = {}
            for chave, termos in ESTACOES.items():
                # ordem de preferencia: o 1o termo da lista vence se existir no feed
                escolhida = None
                for t in termos:
                    for est in lista:
                        nome = _norm(str(est.get("name") or est.get("nome") or est.get("estacao") or ""))
                        if nome and t in nome:
                            escolhida = est; break
                    if escolhida: break
                if escolhida:
                    est = escolhida
                    d = est.get("data") if isinstance(est.get("data"), dict) else est
                    def num(*ks):
                        for k in ks:
                            v = d.get(k)
                            if v is None: continue
                            try: return float(str(v).replace(",", "."))
                            except ValueError: pass
                        return None
                    saida[chave] = {
                        "estacao": est.get("name") or est.get("nome") or est.get("estacao"),
                        "mm_1h": num("h01", "m60", "mm_1h", "1h"),
                        "mm_3h": num("h03", "mm_3h", "3h"),
                        "mm_24h": num("h24", "mm_24h", "24h"),
                        "lido_em": est.get("read_at") or est.get("data_hora") or d.get("read_at"),
                    }
            if saida:
                saida["_fonte"] = url
                return saida
            ultimo_erro = f"{url}: nenhuma estacao reconhecida"
        except Exception as e:
            ultimo_erro = f"{url}: {e}"
    return {"erro": ultimo_erro}

def classificar(vesp, agora, medido):
    """Compara vespera x agora para UM ponto. Devolve (status, motivos[])."""
    if not vesp or not vesp.get("ok"):
        return "sem_vespera", ["boletim da vespera nao tinha este ponto"]
    if not agora or not agora.get("ok"):
        return "indisponivel", ["Open-Meteo nao respondeu agora"]
    vp, vm = vesp.get("chuva_prob_max_pct") or 0, vesp.get("chuva_mm_total") or 0
    ap, am = agora.get("chuva_prob_max_pct") or 0, agora.get("chuva_mm_total") or 0
    mm3 = (medido or {}).get("mm_3h")
    antes = agora.get("chuva_mm_madrugada_antes") or 0
    motivos = []
    vesp_seco  = vp < 30 and vm < 0.5
    vesp_chuva = vp >= 50 or vm >= 2
    agora_chuva = ap >= 60 or am >= 1 or (mm3 is not None and mm3 >= 1)
    agora_seco  = ap < 30 and am < 0.5 and (mm3 is None or mm3 < 0.5)
    if agora_chuva and not vesp_chuva:
        status = "piorou"
        motivos.append(f"modelos das 3h: {ap:.0f}% e {am:.1f} mm na janela (a noite dizia {vp:.0f}%)")
    elif vesp_chuva and agora_seco:
        status = "melhorou"
        motivos.append(f"modelos das 3h: {ap:.0f}% e {am:.1f} mm (a noite dizia {vp:.0f}%)")
    else:
        status = "confirmado"
    if mm3 is not None and mm3 >= 0.5:
        motivos.append(f"choveu {mm3:.1f} mm nas ultimas 3h ({(medido or {}).get('estacao')}, Alerta Rio)")
    elif antes >= 0.5:
        motivos.append(f"modelo indica {antes:.1f} mm entre 0h e 3h — pista pode estar molhada")
    return status, motivos

def main():
    agora_dt = datetime.datetime.now(TZ)
    hoje = agora_dt.strftime("%Y-%m-%d")
    saida = {
        "gerado_em": agora_dt.isoformat(),
        "hora_local": agora_dt.strftime("%H:%M"),
        "data_alvo": hoje,
        "status": "indisponivel",
        "titulo": "",
        "resumo": "",
        "avisos": [],
        "pontos": {},
        "fontes": {"open_meteo": False, "alerta_rio": False},
    }
    # 1. vespera
    try:
        with open(ARQ_VESPERA, encoding="utf-8") as f:
            vesp = json.load(f)
        saida["vespera"] = {"gerado_em": vesp.get("gerado_em"), "data_alvo": vesp.get("data_alvo"),
                            "confianca_geral": vesp.get("confianca_geral")}
        if vesp.get("data_alvo") != hoje:
            saida["avisos"].append(f"boletim da vespera e de {vesp.get('data_alvo')}, nao de hoje ({hoje}) — comparacao desativada")
            vesp = {"pontos": {}}
    except Exception as e:
        vesp = {"pontos": {}}
        saida["avisos"].append(f"nao consegui ler a vespera: {e}")

    # 2. agora (Open-Meteo, 1 dia = hoje)
    agora = {}
    for chave, p in bc.PONTOS.items():
        try:
            agora[chave] = bc.coletar_ponto(chave, p, hoje, forecast_days=1)
        except Exception as e:
            agora[chave] = {"nome": p["nome"], "ok": False, "erro": str(e)}
    saida["fontes"]["open_meteo"] = any(v.get("ok") for v in agora.values())

    # 3. medido (Alerta Rio) — best-effort
    medido = ler_alerta_rio()
    if "erro" in medido:
        saida["fontes"]["alerta_rio"] = False
        saida["fontes"]["alerta_rio_erro"] = medido["erro"]
    else:
        saida["fontes"]["alerta_rio"] = True
        saida["fontes"]["alerta_rio_url"] = medido.pop("_fonte", None)

    # 4. comparar
    piorou, melhorou, vento = [], [], []
    for chave, p in bc.PONTOS.items():
        v, a, m = vesp.get("pontos", {}).get(chave), agora.get(chave), (medido.get(chave) if "erro" not in medido else None)
        status, motivos = classificar(v, a, m)
        if status == "piorou": piorou.append(p["nome"])
        if status == "melhorou": melhorou.append(p["nome"])
        raj_a, raj_v = (a or {}).get("rajada_max_kmh") or 0, (v or {}).get("rajada_max_kmh") or 0
        if raj_a >= 40 and raj_v < 30:
            vento.append(f"{p['nome']} ~{raj_a:.0f} km/h")
        saida["pontos"][chave] = {
            "nome": p["nome"], "status": status, "motivos": motivos,
            "agora": {k: a.get(k) for k in ("chuva_prob_max_pct","chuva_prob_largada_pct","chuva_mm_total",
                                             "chuva_mm_madrugada_antes","vento_med_kmh","rajada_max_kmh",
                                             "vento_dir_cardeal","temp_min_c","temp_max_janela_c",
                                             "sensacao_largada_c","confianca","ok")} if a else None,
            "vespera": {k: v.get(k) for k in ("chuva_prob_max_pct","chuva_mm_total","rajada_max_kmh","confianca")} if v else None,
            "medido_alerta_rio": m,
        }

    # 5. veredito geral (determinístico, templates fixos)
    sem_vespera = all(saida["pontos"][k]["status"] == "sem_vespera" for k in saida["pontos"])
    if not saida["fontes"]["open_meteo"]:
        saida["status"] = "indisponivel"
        saida["titulo"] = "⚠️ Atualização das 3h não rodou"
        saida["resumo"] = "A fonte de clima não respondeu. Vale o boletim da noite — e confira o céu e a câmera do seu trecho antes de sair."
    elif sem_vespera:
        # sem boletim da vespera para comparar: so reporta a leitura, sem dizer que "nada mudou"
        saida["status"] = "leitura"
        saida["titulo"] = f"🕒 LEITURA DAS {saida['hora_local']}"
        det = "; ".join(f"{saida['pontos'][k]['nome']}: {saida['pontos'][k]['agora']['chuva_prob_max_pct']:.0f}%"
                        for k in saida["pontos"] if saida["pontos"][k]["agora"] and saida["pontos"][k]["agora"].get("ok"))
        saida["resumo"] = f"Sem boletim da véspera pra comparar. Modelos agora, janela 4h–8h: {det}."
    elif piorou:
        saida["status"] = "mudou_pior"
        saida["titulo"] = "⚠️ MUDOU PRA PIOR"
        det = "; ".join(f"{saida['pontos'][k]['nome']}: {saida['pontos'][k]['agora']['chuva_prob_max_pct']:.0f}%"
                        for k in saida["pontos"] if saida["pontos"][k]["status"] == "piorou")
        saida["resumo"] = (f"Às {saida['hora_local']} os modelos passaram a indicar chuva na janela 4h–8h ({det}). "
                           "Road: não vai. MTB: pista molhada, avalie com cuidado.")
    elif melhorou and not piorou:
        saida["status"] = "mudou_melhor"
        saida["titulo"] = "🌤️ MELHOROU"
        det = "; ".join(f"{saida['pontos'][k]['nome']}: {saida['pontos'][k]['agora']['chuva_prob_max_pct']:.0f}%"
                        for k in saida["pontos"] if saida["pontos"][k]["status"] == "melhorou")
        saida["resumo"] = (f"A chuva prevista à noite não aparece mais nos modelos das {saida['hora_local']} ({det}). "
                           "Pista pode estar úmida — confira a câmera do seu trecho antes de sair.")
    else:
        saida["status"] = "confirmado"
        saida["titulo"] = "✅ CONFIRMADO"
        saida["resumo"] = f"Leitura das {saida['hora_local']}: nada mudou de relevante desde o boletim da noite. Vale o que está escrito abaixo."
    # avisos transversais
    molhada = [saida["pontos"][k]["nome"] for k in saida["pontos"]
               if any("mm" in mo for mo in saida["pontos"][k]["motivos"])]
    if molhada and saida["status"] == "confirmado":
        saida["avisos"].append("💧 Pista pode estar molhada em: " + ", ".join(molhada) + ".")
    if vento:
        saida["avisos"].append("💨 Rajadas mais fortes que o previsto: " + ", ".join(vento) + ". Atenção no Joá e na orla.")

    with open(ARQ_SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(json.dumps(saida, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
