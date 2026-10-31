#!/usr/bin/env python3
"""Robô do Paulistânia Hoje.

Lê os feeds RSS dos jornais listados em scripts/fontes.json, guarda título,
data, trecho publicado pelo jornal e link, marca as cidades paulistas citadas
e grava tudo em data/feed.json. Usa só a biblioteca padrão do Python.
"""
import email.utils
import html
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "scripts" / "fontes.json"
MUNICIPIOS = RAIZ / "data" / "municipios.json"
SAIDA = RAIZ / "data" / "feed.json"
DIAS_GUARDADOS = 120
MAXIMO_ITENS = 4000
UA = "Mozilla/5.0 (compatible; PaulistaniaHojeBot/1.0; +https://github.com)"
BRT = timezone(timedelta(hours=-3))

# Nomes de cidade que também são palavras comuns, nomes ou sobrenomes.
# Só contam quando vêm depois de "em", "de", "Prefeitura de" etc.
AMBIGUOS = {
    "São Paulo", "Santos", "Bastos", "Barbosa", "Cardoso", "Marília", "Cunha", "Lorena", "Cruzeiro",
    "Aparecida", "Piedade", "Socorro", "Salto", "Pedreira", "Amparo", "Alumínio", "Planalto", "Pontal",
    "Dourado", "Paraíso", "Oriente", "Promissão", "Garça", "Quadra", "Platina", "Restinga", "Serrana",
    "Bálsamo", "Monções", "Areias", "Bananal", "Canas", "Piquete", "Eldorado", "Colômbia", "Valparaíso",
    "Guararapes", "Queluz", "Castilho", "Sales", "Novais", "Uchoa", "Queiroz", "Mendonça", "Rosana",
    "Sabino", "Lavínia", "Lourdes", "Olímpia", "Clementina", "Adolfo", "Zacarias", "Taquaral", "Vargem",
    "Indiana", "Avaí", "Bilac", "Dumont", "José Bonifácio", "Monteiro Lobato", "Júlio Mesquita", "Fernão",
    "Pedro de Toledo", "Elias Fausto", "Artur Nogueira", "Cândido Rodrigues", "Fernando Prestes",
    "Bento de Abreu", "Sud Mennucci", "Gabriel Monteiro", "Anhembi", "Tremembé", "Lins", "Vera Cruz",
    "Assis", "Registro", "Agudos", "Conchas", "Pereiras", "Tietê", "Óleo", "Fartura", "Brotas", "Bocaina",
    "Rincão", "Américo Brasiliense", "Gavião Peixoto", "Presidente Alves", "Oscar Bressane", "Cândido Mota",
    "Bernardino de Campos", "Coronel Macedo", "Barão de Antonina", "São Pedro", "São Roque", "São Simão",
    "São Manuel", "São Vicente", "São Sebastião", "Mirassol", "Itapura", "Arco-Íris", "Jaci", "Guaíra",
    "Pracinha", "Ribeira", "Lucélia", "Glicério", "Severínia", "Embaúba", "Ipiguá", "Torre de Pedra",
    "Salto Grande", "Praia Grande", "Capivari", "Boracéia", "Iracemápolis", "Jambeiro", "Lagoinha", "Potim", "Roseira",
}
CUE = r"(?:\bem|\bde|\bda|\bdo|\bpara|\bcidade de|\bmunicípio de|\bPrefeitura de|\bprefeito de|\bprefeita de|\bCâmara de)\s+"
CAPITAL = re.compile(r"capital paulista|cidade de São Paulo|Prefeitura de São Paulo|prefeito Ricardo Nunes|Câmara Municipal de São Paulo|Câmara de São Paulo", re.I)
APELIDOS = {
    r"São Bernardo(?! do Campo)": "São Bernardo do Campo",
    r"São Caetano(?! do Sul)": "São Caetano do Sul",
    r"(?<!São José do )Rio Preto": "São José do Rio Preto",
    r"Santa Bárbara(?! d)": "Santa Bárbara d'Oeste",
    r"Embu(?![\w-])(?! das Artes)": "Embu das Artes",
    r"Pinda(?![\w])": "Pindamonhangaba",
    r"Itaquá(?![\w])": "Itaquaquecetuba",
}
# Só entra no site o que é de interesse público...
INTERESSE = re.compile(r"prefeit|câmara|vereador|governo|governador|secretári|decreto|\blei\b|projeto de lei|orçamento|obra|licitação|contrat|concurso|saúde|hospital|\bUBS\b|\bUPA\b|escola|educação|ensino|creche|transporte|ônibus|trânsito|rodovia|ped[aá]gio|segurança|polícia|\bGCM\b|Defesa Civil|chuva|\bágua\b|Sabesp|esgoto|imposto|IPTU|ICMS|tarifa|Alesp|Tarcísio|Ricardo Nunes|serviço|programa|investiment|moradia|habitação|assistência|vacina|dengue|eleiç|Cantareira|Ministério Público|\bMP\b|Gaeco|TCE|Justiça|Poupatempo|Fatec|Etec|Provão", re.I)
# ...e fica de fora esporte, celebridade e entretenimento.
FORA = re.compile(r"futebol|Palmeiras|Corinthians|Santos FC|Vasco|Flamengo|Fluminense|Botafogo|Grêmio|Copa do Brasil|Brasileirão|Libertadores|Sul-Americana|Série [AB]\b|\bF1\b|Fórmula 1|novela|\bBBB\b|celebridade|\bcantor|\bcantora|\bator\b|\batriz\b|\bfilme\b|horóscopo|Messi|jogador|técnico do|\bgol\b|Palavra do Leitor|receita de", re.I)
SP_TEXTO = re.compile(r"São Paulo|paulista|\bSP\b|Alesp|Tarcísio", re.I)

TEMAS = [
    ("Decretos", r"\bdecreto"),
    ("Segurança", r"polícia|\bPM\b|\bGCM\b|crime|preso|presa|homicíd|roubo|furto|tráfico|Gaeco|esfaque|assalt"),
    ("Saúde", r"saúde|hospital|\bUBS\b|\bUPA\b|vacina|dengue|médic|mamografia|diabetes"),
    ("Educação", r"escola|educação|ensino|aluno|professor|creche|vestibul|Etec|Fatec"),
    ("Transporte", r"ônibus|metrô|trem|rodovia|trânsito|\bBRT\b|ped[aá]gio|mobilidade"),
    ("Saneamento", r"Sabesp|esgoto|saneamento"),
    ("Água", r"\bágua\b|estiagem|racionamento|reservatório"),
    ("Meio ambiente", r"chuva|enchente|alagamento|queimada|incêndio|Defesa Civil|desliza"),
    ("Habitação", r"moradia|habitação|\bCDHU\b|casas populares"),
    ("Contas públicas", r"orçamento|ICMS|IPTU|imposto|tribut|arrecada|dívida|déficit|LDO|\bLOA\b"),
    ("Investimentos", r"investiment|milhões|bilhões|convênio|obra"),
    ("Assistência social", r"assistência social|Cadastro Único|CadÚnico|\bCras\b|Bolsa Família|vulnerab"),
    ("Eleições", r"eleição|eleições|\bvoto\b|candidat|\bTSE\b|\bTRE\b"),
    ("Política", r"prefeit|vereador|Câmara|deputad|governador|Alesp|secretári|Tarcísio"),
]
STATUS = [
    ("decreto", r"\bdecreto"),
    ("alerta", r"investiga|preso|presa|prisão|denúncia|irregular|fraude|crise|alagamento|deslizamento|morte|morre|acidente|interdit|suspens|atraso|atrasad|falta de|protesto"),
    ("entregue", r"inaugur|\bentrega\b|\bentregou\b|\bentregues?\b|começa a funcionar|passa a funcionar|recebe [0-9]"),
    ("obra", r"licitação|\bcontrato\b|contrata empresa|obras? (?:começa|começam|avança|avançam|em andamento)|ordem de serviço"),
    ("anunciado", r"anuncia|vai investir|prevê|promete|projeto prevê|lança programa"),
]


def norm(s):
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


def limpar(texto):
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"\s*(The post|O post|Leia mais|Continue lendo).*$", "", texto)
    texto = re.sub(r"\((?:Foto|Imagem|Crédito)s?:[^)]*\)\s*", "", texto, flags=re.I)
    return texto


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def ler_feed(conteudo):
    raiz = ET.fromstring(conteudo)
    itens = []
    for it in raiz.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        campos = {}
        for filho in it:
            nome = filho.tag.split("}")[-1]
            if nome == "link":
                campos["link"] = (filho.text or filho.get("href") or "").strip()
            elif nome in ("title", "description", "summary", "pubDate", "published", "updated", "date"):
                campos.setdefault(nome, filho.text or "")
        itens.append(campos)
    return itens


def data_iso(campos):
    bruto = campos.get("pubDate") or campos.get("published") or campos.get("updated") or campos.get("date") or ""
    dt = None
    try:
        dt = email.utils.parsedate_to_datetime(bruto)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT)


def preparar_cidades(municipios):
    regras = []
    for m in municipios:
        nome = m["n"]
        alvo = re.escape(nome).replace("\\ ", r"\s+").replace("'", "['’]")
        if nome in AMBIGUOS:
            padrao = re.compile(CUE + "(" + alvo + r")(?![\w-])")
        else:
            padrao = re.compile(r"(?<![\w-])" + alvo + r"(?![\w-])")
        regras.append((nome, padrao))
    # nomes mais longos primeiro, para "Santa Bárbara d'Oeste" vencer "Santa Bárbara"
    regras.sort(key=lambda x: -len(x[0]))
    return regras


def achar_cidades(texto, regras):
    achadas, ocupado = [], []
    for nome, padrao in regras:
        for m in padrao.finditer(texto):
            ini, fim = m.span(1) if m.groups() else m.span()
            if any(a < fim and ini < b for a, b in ocupado):
                continue
            ocupado.append((ini, fim))
            if nome not in achadas:
                achadas.append(nome)
            break
    for padrao, nome in APELIDOS.items():
        if nome not in achadas and re.search(r"(?<![\w-])" + padrao, texto):
            achadas.append(nome)
    if "São Paulo" not in achadas and CAPITAL.search(texto):
        achadas.append("São Paulo")
    return achadas[:20]


def classificar(texto, lista, padrao_final):
    for valor, regex in lista:
        if re.search(regex, texto, re.I):
            return valor
    return padrao_final


def chave(url):
    return re.sub(r"[?#].*$", "", url.strip().lower()).rstrip("/")


def main():
    fontes = json.loads(FONTES.read_text(encoding="utf-8"))["fontes"]
    municipios = json.loads(MUNICIPIOS.read_text(encoding="utf-8"))
    regras = preparar_cidades(municipios)
    nomes = {m["n"] for m in municipios}

    anterior = {"itens": []}
    if SAIDA.exists():
        anterior = json.loads(SAIDA.read_text(encoding="utf-8"))
    por_link = {chave(i["u"]): i for i in anterior.get("itens", [])}

    ok, erros, novos = [], [], 0
    agora = datetime.now(BRT)
    for f in fontes:
        try:
            itens = ler_feed(baixar(f["feed"]))
        except Exception as e:  # um jornal fora do ar não pode parar os outros
            erros.append({"fonte": f["nome"], "erro": str(e)[:160]})
            continue
        ok.append(f["nome"])
        for campos in itens:
            titulo = limpar(campos.get("title"))
            link = (campos.get("link") or "").strip()
            if not titulo or not link.startswith("https://"):
                continue
            k = chave(link)
            if k in por_link:
                continue
            trecho = limpar(campos.get("description") or campos.get("summary"))
            if trecho.startswith(titulo):
                trecho = trecho[len(titulo):].strip(" -–:")
            if len(trecho) > 320:
                trecho = trecho[:317].rsplit(" ", 1)[0] + "…"
            texto = titulo + " . " + trecho
            if FORA.search(titulo) or not INTERESSE.search(texto):
                continue
            cidades = achar_cidades(texto, regras)
            if not cidades and f.get("cidade") in nomes:
                cidades = [f["cidade"]]
            if f.get("so_sp") and not cidades and not SP_TEXTO.search(texto):
                continue
            dt = data_iso(campos)
            if dt < agora - timedelta(days=DIAS_GUARDADOS):
                continue
            item = {
                "d": dt.strftime("%Y-%m-%d"),
                "h": dt.strftime("%H:%M"),
                "t": titulo[:220],
                "p": trecho,
                "tema": classificar(texto, TEMAS, "Geral"),
                "s": classificar(texto, STATUS, "fato"),
                "c": cidades,
                "src": f["nome"],
                "u": link,
                "auto": True,
            }
            if item["s"] == "decreto":
                item["org"] = "Estado" if re.search(r"governador|Governo do Estado|estadual", texto, re.I) else "Prefeitura"
            por_link[k] = item
            novos += 1

    limite = (agora - timedelta(days=DIAS_GUARDADOS)).strftime("%Y-%m-%d")
    itens = [i for i in por_link.values() if i["d"] >= limite]
    itens.sort(key=lambda i: (i["d"], i.get("h", "")), reverse=True)
    itens = itens[:MAXIMO_ITENS]

    saida = {
        "atualizado": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "novos_nesta_coleta": novos,
        "fontes_ok": ok,
        "fontes_com_erro": erros,
        "itens": itens,
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{novos} notícias novas · {len(itens)} no total · {len(ok)} jornais lidos · {len(erros)} com erro")
    for e in erros:
        print("  erro:", e["fonte"], "-", e["erro"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
