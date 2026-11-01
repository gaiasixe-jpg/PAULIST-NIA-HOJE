#!/usr/bin/env python3
"""Robô do Paulistânia Hoje.

Lê os feeds RSS dos jornais listados em scripts/fontes.json, guarda título,
data, trecho publicado pelo jornal e link, marca as cidades paulistas citadas
e grava tudo em data/feed.json. Usa só a biblioteca padrão do Python.
"""
import email.utils
import html
import html.entities
import io
import json
import zipfile
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
FORA = re.compile(r"futebol|Palmeiras|Corinthians|Santos FC|Vasco|Flamengo|Fluminense|Botafogo|Grêmio|Copa do Brasil|Brasileirão|Libertadores|Sul-Americana|Série [AB]\b|\bF1\b|Fórmula 1|novela|\bBBB\b|celebridade|\bcantor|\bcantora|\bator\b|\batriz\b|\bfilme\b|horóscopo|Messi|jogador|técnico do|\bgol\b|Palavra do Leitor|receita de|\brugby\b|\bjogos? (?:regionais|abertos)\b", re.I)
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


XML_BASICAS = {"amp", "lt", "gt", "quot", "apos"}


def trocar_entidades(conteudo):
    """Alguns jornais (ex.: Gazeta de S.Paulo) põem &nbsp; e outras entidades de HTML
    no feed, o que é inválido em XML. Troca por caracteres numéricos."""
    texto = conteudo.decode("utf-8", "replace")

    def troca(m):
        nome = m.group(1)
        if nome in XML_BASICAS:
            return m.group(0)
        cod = html.entities.name2codepoint.get(nome)
        return f"&#{cod};" if cod else ""

    texto = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", troca, texto)
    texto = re.sub(r"&(?![A-Za-z#][A-Za-z0-9]*;)", "&amp;", texto)
    return texto.encode("utf-8")


def ler_feed(conteudo):
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError:
        raiz = ET.fromstring(trocar_entidades(conteudo))
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
    # "Estado de São Paulo", "Governo de São Paulo" etc. falam do Estado, não da capital
    texto = re.sub(r"\b(Estado|estado|Governo|governo|governador|Governador|Tribunal de Justiça|interior)\s+(?:do\s+|de\s+)São\s+Paulo", r"\1", texto)
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


# ---------- Atos oficiais do Estado (base de legislação da Alesp, dados abertos) ----------
ALESP_ZIP = "https://www.al.sp.gov.br/repositorioDados/legislacao/legislacao_normas.zip"
ALESP_TIPOS = {"3": "Decreto", "9": "Lei", "2": "Lei Complementar"}
ALESP_DIAS = 60
CREDITO = re.compile(r"abertura de crédito suplementar", re.I)


def numero_bonito(n):
    return f"{int(n):,}".replace(",", ".") if (n or "").isdigit() else (n or "")


def item_alesp(n, regras):
    texto = n["ementa"]
    dd = f"{n['d'][8:10]}/{n['d'][5:7]}/{n['d'][:4]}"
    return {
        "d": n["d"], "h": "00:00",
        "t": texto[:200] + ("…" if len(texto) > 200 else ""),
        "p": f"{n['tipo']} estadual nº {numero_bonito(n['num'])}, de {dd}, publicad{'a' if n['tipo'].startswith('Lei') else 'o'} no Diário Oficial do Estado. O texto completo está na base de legislação da Alesp.",
        "tema": classificar(texto, [t for t in TEMAS if t[0] != "Decretos"], "Decretos"),
        "s": "decreto", "org": "Estado", "num": f"{n['tipo'].replace('Lei Complementar', 'LC')} nº {numero_bonito(n['num'])}",
        "c": achar_cidades(texto, regras),
        "src": "Diário Oficial (via Alesp)", "u": n["u"], "auto": True,
    }


def coletar_alesp(regras, agora):
    """Lê os decretos e leis estaduais publicados no Diário Oficial e cadastrados pela Alesp.
    Decretos de crédito suplementar do mesmo dia viram um item só, para não lotar o site."""
    bruto = baixar(ALESP_ZIP)
    limite = (agora - timedelta(days=ALESP_DIAS)).strftime("%Y-%m-%d")
    normas = {}
    with zipfile.ZipFile(io.BytesIO(bruto)) as z:
        nome = [n for n in z.namelist() if n.endswith(".xml")][0]
        with z.open(nome) as arq:
            for _, el in ET.iterparse(arq):
                if el.tag != "LegislacaoNorma":
                    continue
                data = (el.findtext("Data") or "")[:10]
                tipo = el.findtext("IdTipo") or ""
                if data >= limite and tipo in ALESP_TIPOS:
                    idn = el.findtext("IdNorma")
                    normas[idn] = {
                        "d": data, "tipo": ALESP_TIPOS[tipo], "num": el.findtext("Numero") or "",
                        "ementa": re.sub(r"\s+", " ", el.findtext("Ementa") or "").strip(),
                        "u": (el.findtext("URLFicha") or f"http://www.al.sp.gov.br/norma/{idn}").replace("http://", "https://"),
                    }
                el.clear()

    itens, creditos = [], {}
    for n in normas.values():
        if not n["ementa"]:
            continue
        if n["tipo"] == "Decreto" and CREDITO.search(n["ementa"]):
            creditos.setdefault(n["d"], []).append(n)
            continue
        itens.append(item_alesp(n, regras))
    for data, lista in list(creditos.items()):
        if len(lista) == 1:  # um só decreto de crédito no dia: entra normal
            itens.append(item_alesp(lista[0], regras))
            del creditos[data]
    for data, lista in creditos.items():
        lista.sort(key=lambda x: x["num"])
        orgaos = []
        for n in lista:
            m = re.search(r"(?:Orçamento [^,]*?) (?:na|no|da|do|nas|nos) (.+?)(?:,| visando|$)", n["ementa"])
            if m and m.group(1) not in orgaos:
                orgaos.append(m.group(1))
        dd = f"{data[8:10]}/{data[5:7]}"
        nums = ", ".join(numero_bonito(n["num"]) for n in lista[:12]) + ("…" if len(lista) > 12 else "")
        itens.append({
            "d": data, "h": "00:00",
            "t": f"{len(lista)} decreto{'s' if len(lista) > 1 else ''} de crédito suplementar no Orçamento do Estado ({dd})",
            "p": "Reforço de verbas (crédito suplementar) para: " + "; ".join(orgaos[:8]) + ("…" if len(orgaos) > 8 else "") + f". Decretos nº {nums}.",
            "tema": "Contas públicas", "s": "decreto", "org": "Estado",
            "num": f"Nº {numero_bonito(lista[0]['num'])}" + (f" a {numero_bonito(lista[-1]['num'])}" if len(lista) > 1 else ""),
            "c": [], "src": "Diário Oficial (via Alesp)", "u": lista[0]["u"], "auto": True,
        })
    return itens


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
            if FORA.search(titulo) or not (f.get("oficial") or INTERESSE.search(texto)):
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

    # Atos oficiais do Estado: a Alesp atualiza a base uma vez por dia, de madrugada,
    # então o robô só baixa o arquivo (10 MB) três vezes ao dia.
    tem_alesp = any(i.get("src", "").startswith("Diário Oficial") for i in por_link.values())
    try:
        if tem_alesp and agora.hour not in (7, 13, 19) and "--alesp" not in sys.argv:
            raise StopIteration
        for item in coletar_alesp(regras, agora):
            k = chave(item["u"])
            if k not in por_link:
                novos += 1
            por_link[k] = item  # sobrescreve: o grupo de créditos do dia pode crescer
        ok.append("Diário Oficial (via Alesp)")
    except StopIteration:
        ok.append("Diário Oficial (via Alesp)")
    except Exception as e:
        erros.append({"fonte": "Diário Oficial (via Alesp)", "erro": str(e)[:160]})

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
