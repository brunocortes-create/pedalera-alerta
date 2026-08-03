# CONFIG: Rotas Canônicas do Ciclismo de Estrada — Rio de Janeiro

Cada bloco tem: trechos, ponto de previsão do tempo e azimute aproximado
(rumo da via em graus, 0=Norte, 90=Leste). O azimute serve para traduzir a
direção do vento em "contra / a favor / lateral" por sentido de pedalada.
Valores aproximados, calibrados pela geografia da orla — ajustar conforme feedback.

## 🌊 Bloco 1 — Orla Barra–Recreio
- Trechos: Av. Lúcio Costa (Recreio ↔ Alvorada ↔ Quebra-Mar), retorno pela
  Av. das Américas / Reserva
- Ponto de clima: -23.02, -43.44 (Barra/Recreio)
- Eixo da via: ~70° / ~250°
  - Sentido Recreio → Quebra-Mar (ida): rumo ~70° (ENE)
  - Sentido Quebra-Mar → Recreio (volta, via Reserva): rumo ~250° (OSO)
- Observação: vento de E/NE = contra na ida; vento de SO/O = contra na volta;
  vento de S/SE = lateral com componente. É a rota de maior volume de ciclistas.

## 🏖️ Bloco 2 — Grumari–Prainha–Grota Funda
- Trechos: Recreio → Pontal → Prainha → Grumari (Av. Estado da Guanabara /
  Estrada do Grumari); variante Grota Funda (Estrada Vereador Alceu de Carvalho)
- Ponto de clima: -23.05, -43.52 (Grumari)
- Eixo costeiro: ~65° / ~245°; subidas curtas onde rajada importa mais que direção
- Observação: trecho com menos iluminação e apoio — chuva e rajada pesam mais aqui.

## ⛰️ Bloco 3 — Joá
- Trechos: Quebra-Mar ↔ Elevado do Joá ↔ São Conrado (Av. Niemeyer não — bloco 4)
- Ponto de clima: -23.02, -43.44 (usar Barra)
- Eixo: ~85° / ~265°, com subida; em subida, reporte rajadas e piso molhado,
  não contra/favor
- Observação: ponto crítico de vento lateral nas partes altas do elevado.
- Nota: Bloco Joá = SUBIDA do elevado (Estrada do Joá), não o túnel. Ciclistas usam ciclovia própria, separada da via de veículos. O fechamento do Túnel do Joá para carros (madrugadas de quarta, até 4h30, fonte COR) NÃO afeta ciclistas — NÃO citar como alerta/interdição no boletim. Confirmado por observação de rua do Bruno em 09/07/2026.

## 🏙️ Bloco 4 — Orla Zona Sul + Aterro
- Trechos: Leblon → Ipanema (eixo ~85°/265°), Copacabana/Leme (eixo ~45°/225°),
  Aterro do Flamengo (eixo ~15°/195°)
- Ponto de clima: -22.97, -43.19 (Copacabana)
- Observação: reportar os 3 sub-trechos quando o vento for forte, porque a
  orientação muda; Aterro tem ativações de lazer/APCC próprias.

## 🚵 Bloco 5 — Subidas Zona Sul
- Trechos: Lagoa (volta, plano), Horto, Vista Chinesa, Mesa do Imperador,
  Paineiras/Cristo, Canoas
- Ponto de clima: -22.97, -43.19 (usar Zona Sul)
- Em subida de mata: o que importa é chuva, piso molhado e neblina — não direção
  de vento. Reportar nesses termos.

## ⚓ Bloco 6 — Centro/Porto
- Trechos: Orla Conde / Museu do Amanhã / Av. Rodrigues Alves —
  APCC Porto (Circuito Marcos Hama)
- Ponto de clima: -22.97, -43.19 (usar Zona Sul)
- Observação: bloco fortemente dependente de ativação de APCC e de eventos no
  Centro (provas largam/chegam muito por aqui).

## Fora de cobertura (por enquanto)
Zona Norte, Niterói/Região Oceânica e Baixada ficam fora da v1 do boletim.
Niterói está fora do município (COR não cobre). Avaliar inclusão conforme
o canal crescer e aparecerem pedidos.

## Exemplos resolvidos de vento (conferidos — NÃO inverter)

REGRA (idêntica à do prompt-mestre da Routine; em caso de divergência, o prompt vence): vento_dir_graus é a direção DE ONDE o vento vem.
diff = menor ângulo entre vento_dir_graus e o rumo do trecho (0-180°).
- diff < 45°  → CONTRA (vento de proa)
- diff > 135° → A FAVOR (vento de popa)
- 45°-135°    → LATERAL

Exemplo 1 — Orla ZS, Leblon→Ipanema→Copacabana→Leme, ida rumo ~85°. Vento de SO (225°): diff = |225-85| = 140° → maior que 135° → A FAVOR na ida (rumo Leme). Na volta (rumo 265°): diff = |225-265| = 40° → CONTRA.

Exemplo 2 — Barra-Recreio, ida Recreio→Quebra-Mar, rumo ~70°. Vento de E/NE (60°): diff = 10° → CONTRA na ida. Volta (rumo 250°): diff = 170° → A FAVOR. Confere com a Observação do Bloco 1.

Exemplo 3 — Barra-Recreio, ida rumo ~70°. Vento de SO (225°): diff = 155° → A FAVOR na ida. Volta (rumo 250°): diff = 25° → CONTRA. Confere com a Observação do Bloco 1 ("vento de SO/O = contra na volta").

⚠️ HISTÓRICO — não reintroduzir: até 03/08/2026 esta seção continha a regra INVERTIDA ("diff < 90° = A FAVOR"), que contradizia as Observações de cada bloco deste mesmo arquivo e foi a causa raiz de 3 inversões de vento em boletins publicados. Qualquer edição futura desta seção deve ser conferida contra as Observações dos blocos antes de commitar.

# ───────────────────────────────────────────────────────────
# NOTAS DE MICROCLIMA (conhecimento local — vantagem do Pedal Rio)
# ───────────────────────────────────────────────────────────

# COMO FUNCIONA:
# Trechos específicos que se comportam diferente da média da região.
# Cada nota tem um STATUS:
#   - ATIVA: confirmada por observação repetida. O boletim SEMPRE a inclui
#     quando a CONDIÇÃO-GATILHO for verdadeira.
#   - CANDIDATA: observada uma vez, ainda não confirmada. O boletim NÃO usa.
#     Fica aqui aguardando o editor confirmar com mais observações.
#
# O editor (Bruno) promove CANDIDATA → ATIVA quando vir o padrão se repetir.

## CANDIDATA — Estrada do Pontal: pé da Grota Funda até a rotatória da Prainha
- Status: CANDIDATA (observado 1x em 27/06 — molhado com resto da região seco)
- Hipótese: trecho sombreado, baixo, sem sol direto e muito úmido; retém umidade
  e seca devagar. Pode estar molhado mesmo com a previsão geral seca.
- Condição-gatilho (quando confirmar): se chuva_mm_madrugada_antes > 0 em grumari
  OU choveu nas 24h anteriores → incluir aviso no bloco Grumari.
- Texto do aviso (quando ATIVA): "⚠️ Pé da Grota até a rotatória da Prainha:
  trecho sombreado e úmido, costuma amanhecer molhado mesmo com o resto seco —
  atenção ao piso."
- AÇÃO DO EDITOR: confirmar em 2-3 madrugadas se o padrão se repete. Se sim,
  mudar Status para ATIVA.
