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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "scripts" / "fontes.json"
MUNICIPIOS = RAIZ / "data" / "municipios.json"
SAIDA = RAIZ / "data" / "feed.json"
DEPUTADOS = RAIZ / "data" / "deputados.json"
FEDERAIS = RAIZ / "data" / "federais.json"
GASTOS = RAIZ / "data" / "gastos.json"
ARQUIVO = RAIZ / "data" / "arquivo"
RSS = RAIZ / "data" / "rss"
SITE = "https://gaiasixe-jpg.github.io/PAULIST-NIA-HOJE/"
VIDEOS = RAIZ / "data" / "videos.json"
VOTACOES = RAIZ / "data" / "votacoes.json"
YOUTUBE_CANAL = "UCaMYzI56lfmcMxRbO1B5EXQ"  # canal do YouTube (@aranellliz)
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


# ---------- Deputados estaduais (dados abertos da Alesp) ----------
ALESP_DADOS = "https://www.al.sp.gov.br/repositorioDados/"
NAT_GRUPO = {  # natureza -> grupo mostrado no site
    "Projeto de lei": "pl", "Projeto de lei Complementar": "pl", "Proposta de emenda à Constituição": "pl",
    "Projeto de decreto legislativo": "pl", "Projeto de resolução": "pl",
    "Indicação": "ind", "Requerimento": "req", "Requerimento de Informação": "req", "Moção": "moc",
}
NAT_SIGLA = {"Projeto de lei": "PL", "Projeto de lei Complementar": "PLC", "Proposta de emenda à Constituição": "PEC",
             "Projeto de decreto legislativo": "PDL", "Projeto de resolução": "PR"}


def baixar_alesp(caminho):
    for tentativa in range(4):
        try:
            return baixar(ALESP_DADOS + caminho)
        except Exception:
            if tentativa == 3:
                raise
            import time
            time.sleep(8)


def xml_do_zip(bruto):
    z = zipfile.ZipFile(io.BytesIO(bruto))
    return z.open([n for n in z.namelist() if n.endswith(".xml")][0])


def coletar_deputados(regras, agora):
    """Para cada deputado em exercício: partido, base eleitoral, áreas de atuação,
    quanto apresentou nos últimos 12 meses, os últimos projetos de lei e as cidades
    que mais aparecem nas suas indicações, requerimentos e projetos."""
    deps = {}
    for d in ET.fromstring(baixar_alesp("deputados/deputados.xml")):
        if d.findtext("Situacao") != "EXE":
            continue
        limpa = lambda t: [x.strip(" ;.") for x in re.split(r"[;\n]+", t or "") if x.strip(" ;.")]
        deps[d.findtext("IdSPL")] = {
            "id": d.findtext("IdDeputado"), "n": (d.findtext("NomeParlamentar") or "").strip(),
            "p": (d.findtext("Partido") or "").strip(), "email": (d.findtext("Email") or "").strip(),
            "base": limpa(d.findtext("txtBaseEleitoral"))[:6], "areas": limpa(d.findtext("txtAreaAtuacao"))[:10],
            "u": f"https://www.al.sp.gov.br/deputado/?matricula={(d.findtext('Matricula') or '').strip()}",
            "tot": {"pl": 0, "ind": 0, "req": 0, "moc": 0}, "pls": [], "cid": {},
        }
    nat = {x.findtext("idNatureza"): x.findtext("nmNatureza") for x in ET.fromstring(baixar_alesp("processo_legislativo/naturezasSpl.xml"))}
    limite = (agora - timedelta(days=365)).strftime("%Y-%m-%d")
    docs, ultima = {}, ""
    with xml_do_zip(baixar_alesp("processo_legislativo/proposituras.zip")) as arq:
        for _, el in ET.iterparse(arq):
            if el.tag != "propositura":
                continue
            data = (el.findtext("DtPublicacao") or "")[:10]
            nome_nat = nat.get(el.findtext("IdNatureza"), "")
            if data >= limite and nome_nat in NAT_GRUPO:
                docs[el.findtext("IdDocumento")] = (data, nome_nat, el.findtext("NroLegislativo") or "", el.findtext("AnoLegislativo") or "",
                                                     re.sub(r"\s+", " ", el.findtext("Ementa") or "").strip())
                ultima = max(ultima, data)
            el.clear()
    autoria = {}
    with xml_do_zip(baixar_alesp("processo_legislativo/documento_autor.zip")) as arq:
        for _, el in ET.iterparse(arq):
            if el.tag != "DocumentoAutor":
                continue
            i, a = el.findtext("IdDocumento"), el.findtext("IdAutor")
            if i in docs and a in deps:
                autoria.setdefault(i, []).append(a)
            el.clear()
    cache_cid = {}
    for i, autores in autoria.items():
        data, nome_nat, num, ano, ementa = docs[i]
        grupo = NAT_GRUPO[nome_nat]
        if ementa not in cache_cid:
            cache_cid[ementa] = [c for c in achar_cidades(ementa, regras) if c != "São Paulo" or "capital" in ementa.lower()]
        for a in autores:
            dep = deps[a]
            dep["tot"][grupo] += 1
            for c in cache_cid[ementa]:
                dep["cid"][c] = dep["cid"].get(c, 0) + 1
            if grupo == "pl":
                dep["pls"].append({"d": data, "s": f"{NAT_SIGLA.get(nome_nat, 'PL')} {num}/{ano}", "e": ementa[:260],
                                   "u": f"https://www.al.sp.gov.br/propositura/?id={i}"})
    por_cidade = {}
    lista = []
    for dep in deps.values():
        dep["pls"].sort(key=lambda x: x["d"], reverse=True)
        dep["pls"] = dep["pls"][:12]
        top = sorted(dep["cid"].items(), key=lambda x: -x[1])
        for c, n in top:
            por_cidade.setdefault(c, []).append([dep["id"], n])
        dep["cid"] = top[:12]
        lista.append(dep)
    for c in por_cidade:
        por_cidade[c] = sorted(por_cidade[c], key=lambda x: -x[1])[:6]
    lista.sort(key=lambda d: norm(d["n"]))
    return {"atualizado": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"), "dados_ate": ultima,
            "deputados": lista, "por_cidade": por_cidade}


# ---------- Gastos de gabinete (Câmara e Alesp) e deputados federais de SP ----------
import csv


def limpa_tipo(t):
    t = re.sub(r"^[A-Z]\s*-\s*", "", (t or "").strip()).rstrip(". ")
    t = re.sub(r"\s+,", ",", re.sub(r"\s+", " ", t)).replace(",", ", ").replace(",  ", ", ")
    return t[:1].upper() + t[1:].lower() if t.isupper() else t


def resumir(gastos):
    """gastos: dict id -> {n, p, itens: [(tipo, fornecedor, mes, valor)]}"""
    saida = {}
    for k, g in gastos.items():
        cat, forn, mes = {}, {}, [0] * 12
        for tipo, f, m, v in g["itens"]:
            cat[tipo] = cat.get(tipo, 0) + v
            forn[f] = forn.get(f, 0) + v
            if 1 <= m <= 12:
                mes[m - 1] += v
        saida[k] = {"n": g["n"], "p": g["p"], "t": round(sum(cat.values())),
                    "cat": [[c, round(v)] for c, v in sorted(cat.items(), key=lambda x: -x[1])[:8]],
                    "forn": [[f, round(v)] for f, v in sorted(forn.items(), key=lambda x: -x[1])[:6]],
                    "mes": [round(v) for v in mes]}
    return saida


def coletar_gastos(agora):
    ano = agora.year
    cam, ate_c = {}, 0
    bruto = baixar(f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip")
    with zipfile.ZipFile(io.BytesIO(bruto)) as z:
        with z.open([n for n in z.namelist() if n.endswith(".csv")][0]) as arq:
            for r in csv.DictReader(io.TextIOWrapper(arq, encoding="utf-8-sig"), delimiter=";"):
                if r.get("sgUF") != "SP" or not r.get("ideCadastro"):
                    continue
                g = cam.setdefault(r["ideCadastro"], {"n": r["txNomeParlamentar"].strip(), "p": r["sgPartido"].strip(), "itens": []})
                m = int(r.get("numMes") or 0)
                ate_c = max(ate_c, m)
                g["itens"].append((limpa_tipo(r["txtDescricao"]), (r["txtFornecedor"] or "").strip()[:60], m, float(r["vlrLiquido"] or 0)))
    ale, ate_a = {}, 0
    for el in ET.fromstring(baixar_alesp(f"deputados/despesas_gabinetes_{ano}.xml")):
        mat = (el.findtext("Matricula") or "").strip()
        if not mat:
            continue
        g = ale.setdefault(mat, {"n": (el.findtext("Deputado") or "").strip(), "p": "", "itens": []})
        m = int(el.findtext("Mes") or 0)
        ate_a = max(ate_a, m)
        g["itens"].append((limpa_tipo(el.findtext("Tipo")), (el.findtext("Fornecedor") or "").strip()[:60], m, float(el.findtext("Valor") or 0)))
    return {"atualizado": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"), "ano": ano,
            "camara": {"ate_mes": ate_c, "fonte": f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip", "deps": resumir(cam)},
            "alesp": {"ate_mes": ate_a, "fonte": f"https://www.al.sp.gov.br/repositorioDados/deputados/despesas_gabinetes_{ano}.xml", "deps": resumir(ale)}}


CAMARA_API = "https://dadosabertos.camara.leg.br/api/v2/"


def camara_get(caminho):
    for tentativa in range(3):
        try:
            req = urllib.request.Request(CAMARA_API + caminho, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if tentativa == 2:
                raise
            import time
            time.sleep(5)


def contar_proposicoes(dep_id, inicio, tipos, guardar=False):
    itens, pagina = [], 1
    while pagina <= 6:
        d = camara_get(f"proposicoes?idDeputadoAutor={dep_id}&dataApresentacaoInicio={inicio}&siglaTipo={tipos}&itens=100&pagina={pagina}&ordem=DESC&ordenarPor=id")
        itens += d.get("dados", [])
        if not any(l.get("rel") == "next" for l in d.get("links", [])):
            break
        pagina += 1
    return itens


def coletar_federais(regras, agora, gastos):
    """Deputados federais de SP: projetos e requerimentos dos últimos 12 meses e cidades citadas."""
    deps = {}
    try:
        for x in camara_get("deputados?siglaUf=SP&itens=100&ordem=ASC&ordenarPor=nome").get("dados", []):
            deps[str(x["id"])] = {"n": x["nome"], "p": x["siglaPartido"]}
    except Exception:
        pass  # a lista da API às vezes cai; usa quem tem gasto lançado no ano
    for k, g in (gastos or {}).get("camara", {}).get("deps", {}).items():
        deps.setdefault(k, {"n": g["n"].title() if g["n"].isupper() else g["n"], "p": g["p"]})
    inicio = (agora - timedelta(days=365)).strftime("%Y-%m-%d")
    lista, por_cidade, ultima = [], {}, ""
    for dep_id, info in deps.items():
        try:
            pls = contar_proposicoes(dep_id, inicio, "PL,PEC,PLP,PDL")
            reqs = contar_proposicoes(dep_id, inicio, "REQ,RIC,INC")
        except Exception:
            continue
        cid = {}
        for p in pls:
            for c in achar_cidades(p.get("ementa") or "", regras):
                if c != "São Paulo":
                    cid[c] = cid.get(c, 0) + 1
        pls.sort(key=lambda p: p.get("dataApresentacao") or "", reverse=True)
        if pls:
            ultima = max(ultima, (pls[0].get("dataApresentacao") or "")[:10])
        top = sorted(cid.items(), key=lambda x: -x[1])
        for c, n in top:
            por_cidade.setdefault(c, []).append([dep_id, n])
        lista.append({"id": dep_id, "n": info["n"], "p": info["p"],
                      "tot": {"pl": len(pls), "req": len(reqs)},
                      "pls": [{"d": (p.get("dataApresentacao") or "")[:10], "s": f"{p.get('siglaTipo')} {p.get('numero')}/{p.get('ano')}",
                               "e": re.sub(r"\s+", " ", p.get("ementa") or "").strip()[:260],
                               "u": f"https://www.camara.leg.br/propostas-legislativas/{p.get('id')}"} for p in pls[:12]],
                      "cid": top[:12], "u": f"https://www.camara.leg.br/deputados/{dep_id}"})
    for c in por_cidade:
        por_cidade[c] = sorted(por_cidade[c], key=lambda x: -x[1])[:6]
    lista.sort(key=lambda d: norm(d["n"]))
    return {"atualizado": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"), "dados_ate": ultima or agora.strftime("%Y-%m-%d"),
            "deputados": lista, "por_cidade": por_cidade}


# ---------- Arquivo mensal e RSS ----------
def gravar_se_mudou(caminho, texto):
    if caminho.exists() and caminho.read_text(encoding="utf-8") == texto:
        return False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return True


def atualizar_arquivo(itens):
    """Guarda tudo, mês a mês, para sempre (o feed principal guarda só 120 dias)."""
    por_mes = {}
    for i in itens:
        por_mes.setdefault(i["d"][:7], []).append(i)
    for mes, novos in por_mes.items():
        arq = ARQUIVO / f"{mes}.json"
        velhos = json.loads(arq.read_text(encoding="utf-8"))["itens"] if arq.exists() else []
        junta = {chave(i["u"]) + "|" + i["t"]: i for i in velhos}
        for i in novos:
            junta[chave(i["u"]) + "|" + i["t"]] = i
        lista = sorted(junta.values(), key=lambda i: (i["d"], i.get("h", "")), reverse=True)
        gravar_se_mudou(arq, json.dumps({"mes": mes, "itens": lista}, ensure_ascii=False, indent=0))
    meses = []
    for arq in sorted(ARQUIVO.glob("????-??.json"), reverse=True):
        meses.append({"mes": arq.stem, "n": len(json.loads(arq.read_text(encoding="utf-8"))["itens"])})
    gravar_se_mudou(ARQUIVO / "index.json", json.dumps({"meses": meses}, ensure_ascii=False))


def rss_xml(titulo, link, descricao, itens):
    def data_rfc(i):
        dt = datetime.fromisoformat(f"{i['d']}T{i.get('h') or '12:00'}:00-03:00")
        return email.utils.format_datetime(dt)
    partes = [f"<item><title>{html.escape(i['t'])}</title><link>{html.escape(i['u'])}</link>"
              f"<guid isPermaLink=\"false\">{html.escape(chave(i['u']) + '|' + i['t'][:60])}</guid>"
              f"<pubDate>{data_rfc(i)}</pubDate><source url=\"{SITE}\">{html.escape(i.get('src', ''))}</source>"
              f"<description>{html.escape(i.get('p', ''))}</description></item>" for i in itens]
    ultima = data_rfc(itens[0]) if itens else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>{html.escape(titulo)}</title><link>{html.escape(link)}</link><description>{html.escape(descricao)}</description>"
            f"<language>pt-br</language><lastBuildDate>{ultima}</lastBuildDate>" + "".join(partes) + "</channel></rss>\n")


def atualizar_rss(itens, municipios):
    gravar_se_mudou(RSS / "estado.xml", rss_xml("Paulistânia Hoje — Estado de São Paulo", SITE,
                                                "Notícias, decretos e atos de todo o estado, com link para a fonte.", itens[:60]))
    por_cid = {}
    for i in itens:
        for c in i["c"]:
            por_cid.setdefault(c, []).append(i)
    for m in municipios:
        lista = por_cid.get(m["n"])
        if lista:
            gravar_se_mudou(RSS / f"{m['i']}.xml", rss_xml(f"Paulistânia Hoje — {m['n']}", f"{SITE}#c-{m['i']}",
                                                         f"Notícias e atos sobre {m['n']} (SP), com link para a fonte.", lista[:40]))


def atualizar_videos():
    """Últimos vídeos do canal do YouTube (o feed do próprio YouTube)."""
    raiz = ET.fromstring(baixar(f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CANAL}"))
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    itens = []
    for e in raiz.findall("a:entry", ns)[:9]:
        vid = e.findtext("yt:videoId", default="", namespaces=ns)
        if re.fullmatch(r"[\w-]{6,20}", vid or ""):
            itens.append({"id": vid, "t": (e.findtext("a:title", default="", namespaces=ns) or "").strip()[:160],
                          "d": (e.findtext("a:published", default="", namespaces=ns) or "")[:10]})
    gravar_se_mudou(VIDEOS, json.dumps({"itens": itens}, ensure_ascii=False))


# ---------- Decretos das prefeituras (Diários Oficiais municipais via Querido Diário) ----------
QD_API = "https://api.queridodiario.ok.org.br/gazettes"
QD_DEC = re.compile(r"\bDECRETO\s+(?:MUNICIPAL\s+|EXECUTIVO\s+)?(?:N[º°o]\.?|NUMERO|NÚMERO|N\.)\s*([0-9][0-9.]*(?:/[0-9]{2,4})?)", re.I)
QD_EMENTA = re.compile(r"\b((?:Disp[õo]e|Abre|Regulamenta|Declara|Institui|Altera|Nomeia|Exonera|Fixa|Aprova|Homologa|Convoca|Prorroga|Estabelece|Autoriza|Cria|Revoga|Decreta|Denomina|Suspende|Designa|Concede)\b[^;]{15,260}?)(?:\.\s|;|\s+O\s+PREFEITO|\s+[A-ZÁÉÍÓÚ]{2,}\s+[A-ZÁÉÍÓÚ]{2,}\s+[A-ZÁÉÍÓÚ]{3,}|$)", re.S)
QD_CREDITO = re.compile(r"cr[ée]dito (?:adicional )?suplementar|abre (?:no or[çc]amento|cr[ée]dito)", re.I)
QD_ROTINA = re.compile(r"\b(nomeia|exonera|designa|concede (?:f[ée]rias|licen[çc]a)|aposenta|readapta|promove servidor)", re.I)
QD_DIAS = 4
QD_POR_CIDADE = 4


def limpar_trecho(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def qd_contextos():
    import ssl
    yield None
    c = ssl.create_default_context()
    c.set_ciphers("DEFAULT:@SECLEVEL=0")
    c.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    c.minimum_version = ssl.TLSVersion.TLSv1
    yield c
    c = ssl.create_default_context()
    c.maximum_version = ssl.TLSVersion.TLSv1_2
    c.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:RSA+AESGCM:RSA+AES:@SECLEVEL=0")
    yield c


QD_CTX = []


def qd_get(params):
    url = QD_API + "?" + urllib.parse.urlencode(params)
    erros = []
    ctxs = QD_CTX or list(qd_contextos())
    for ctx in ctxs:
        for tentativa in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                    dados = json.loads(r.read().decode("utf-8"))
                if not QD_CTX:
                    QD_CTX.append(ctx)
                return dados
            except Exception as e:
                erros.append(str(e)[:80])
                if "handshake" in str(e).lower() or "ssl" in str(e).lower():
                    break
                import time
                time.sleep(5)
    # último recurso: curl do sistema
    import subprocess
    try:
        saida = subprocess.run(["curl", "-sS", "--max-time", "60", "-H", "Accept: application/json", url],
                               capture_output=True, timeout=90)
        if saida.returncode == 0 and saida.stdout.strip().startswith(b"{"):
            return json.loads(saida.stdout.decode("utf-8"))
        erros.append("curl: " + saida.stderr.decode("utf-8", "replace")[:80])
    except Exception as e:
        erros.append("curl: " + str(e)[:60])
    raise RuntimeError(" | ".join(erros))


def coletar_diarios(municipios, agora):
    """Decretos publicados nos Diários Oficiais das prefeituras paulistas indexados pelo Querido Diário
    (Open Knowledge Brasil). Cobre todas as cidades de SP que o projeto já lê, de todas as regiões."""
    nome = {m["i"]: m["n"] for m in municipios}
    ids = list(nome)
    desde = (agora - timedelta(days=QD_DIAS)).strftime("%Y-%m-%d")
    por_cidade, cobertas = {}, set()
    for k in range(0, len(ids), 60):
        base = [("territory_ids", i) for i in ids[k:k + 60]]
        offset = 0
        while offset < 600:
            d = qd_get(base + [("querystring", "decreto"), ("published_since", desde), ("excerpt_size", 700),
                               ("number_of_excerpts", 6), ("size", 100), ("offset", offset), ("sort_by", "descending_date")])
            gs = d.get("gazettes", [])
            for g in gs:
                cid = nome.get(str(g.get("territory_id")))
                url = g.get("url") or g.get("txt_url") or ""
                if not cid or not url.startswith("http"):
                    continue
                cobertas.add(cid)
                data = str(g.get("date") or "")[:10]
                creditos = 0
                for ex in g.get("excerpts") or []:
                    tx = limpar_trecho(ex)
                    for mt in QD_DEC.finditer(tx):
                        num = mt.group(1).rstrip(".")
                        resto = tx[mt.end():mt.end() + 700]
                        em = QD_EMENTA.search(resto)
                        if not em:
                            continue
                        ementa = re.sub(r"\s+", " ", em.group(1)).strip(" ,.-–")
                        ementa = re.sub(r",?\s*e d[áa] outras provid[êe]ncias$", "", ementa, flags=re.I).strip(" ,.-–")
                        if QD_CREDITO.search(ementa):
                            creditos += 1
                            continue
                        if QD_ROTINA.match(ementa):
                            continue
                        ementa = ementa[0].upper() + ementa[1:]
                        if len(ementa) > 200:
                            ementa = ementa[:197].rsplit(" ", 1)[0] + "…"
                        lst = por_cidade.setdefault(cid, {})
                        if num not in lst:
                            lst[num] = {"d": data, "h": "06:00", "t": f"{cid}: {ementa}", "p": f"Decreto nº {num}, publicado no Diário Oficial do município em {data[8:10]}/{data[5:7]}/{data[:4]}.",
                                        "tema": "Decretos", "s": "decreto", "c": [cid], "src": f"Diário Oficial de {cid}",
                                        "u": url, "auto": True, "org": "Prefeitura", "num": f"Nº {num}", "qd": True, "mun": True}
                if creditos:
                    lst = por_cidade.setdefault(cid, {})
                    kk = "cred-" + data
                    if kk not in lst:
                        lst[kk] = {"d": data, "h": "06:00", "t": f"{cid}: prefeitura abre créditos suplementares no orçamento",
                                   "p": f"O Diário Oficial do município de {data[8:10]}/{data[5:7]}/{data[:4]} traz decreto(s) de crédito suplementar, que remanejam dinheiro entre áreas do orçamento.",
                                   "tema": "Contas públicas", "s": "decreto", "c": [cid], "src": f"Diário Oficial de {cid}",
                                   "u": url, "auto": True, "org": "Prefeitura", "num": "Créditos " + data[8:10] + "/" + data[5:7], "qd": True, "mun": True}
            if len(gs) < 100:
                break
            offset += 100
    itens = []
    for cid, lst in por_cidade.items():
        itens += sorted(lst.values(), key=lambda i: i["d"], reverse=True)[:QD_POR_CIDADE]
    return itens, len(cobertas)


def chave_item(i):
    return chave(i["u"]) + ("|" + i.get("num", "") if i.get("qd") else "")


VOT_PULAR = re.compile(r"Reda[cç][aã]o Final|Requerimento|Mantido|Emenda de Reda|pressupostos|Regime de Tramita", re.I)
VOT_MAX = 40


def coletar_votacoes(agora):
    """Votações nominais do plenário da Câmara (últimos 12 meses) e o voto de cada deputado de SP.
    Incremental: cada votação é consultada uma vez; as já vistas ficam em "checadas"."""
    anterior = {}
    if VOTACOES.exists():
        try:
            anterior = json.loads(VOTACOES.read_text(encoding="utf-8"))
        except Exception:
            anterior = {}
    lista = {v["id"]: v for v in anterior.get("votacoes", [])}
    checadas = set(anterior.get("checadas", []))
    inicio = agora - timedelta(days=365)
    candidatas = []
    fim = agora
    while fim > inicio:  # a API aceita no máximo ~3 meses por consulta
        ini = max(inicio, fim - timedelta(days=88))
        pagina = 1
        while pagina <= 10:
            d = camara_get(f"votacoes?idOrgao=180&dataInicio={ini:%Y-%m-%d}&dataFim={fim:%Y-%m-%d}&itens=200&pagina={pagina}&ordem=DESC&ordenarPor=dataHoraRegistro")
            candidatas += d.get("dados", [])
            if not any(l.get("rel") == "next" for l in d.get("links", [])):
                break
            pagina += 1
        fim = ini - timedelta(days=1)
    candidatas.sort(key=lambda v: v.get("dataHoraRegistro") or v.get("data") or "", reverse=True)
    consultas = 0
    for v in candidatas:
        vid = v.get("id")
        if not vid or vid in checadas or VOT_PULAR.search(v.get("descricao") or ""):
            continue
        if consultas >= 160:  # limite por rodada; o resto fica para o dia seguinte
            break
        consultas += 1
        try:
            votos = camara_get(f"votacoes/{vid}/votos").get("dados", [])
        except Exception:
            continue
        checadas.add(vid)
        if not votos or not any((x.get("tipoVoto") or "").strip() for x in votos):
            continue  # votação simbólica ou secreta: não há voto individual público
        placar, sp = {}, {}
        for x in votos:
            tipo = (x.get("tipoVoto") or "").strip() or "Outro"
            placar[tipo] = placar.get(tipo, 0) + 1
            dep = x.get("deputado_") or {}
            if dep.get("siglaUf") == "SP" and dep.get("id"):
                sp[str(dep["id"])] = tipo
        prop = {}
        try:
            det = camara_get(f"votacoes/{vid}").get("dados", {})
            afet = (det.get("proposicoesAfetadas") or det.get("objetosPossiveis") or [{}])[0]
            if afet.get("id"):
                prop = {"s": afet.get("siglaTipo", ""), "n": afet.get("numero"), "a": afet.get("ano"),
                        "e": limpar(afet.get("ementa") or "")[:400],
                        "u": f"https://www.camara.leg.br/propostas-legislativas/{afet['id']}"}
        except Exception:
            pass
        lista[vid] = {"id": vid, "d": v.get("data", ""), "desc": limpar(v.get("descricao") or "")[:400],
                      "ap": v.get("aprovacao"), "prop": prop, "pl": placar, "sp": sp}
    votacoes = sorted(lista.values(), key=lambda v: (v["d"], v["id"]), reverse=True)
    votacoes = [v for v in votacoes if v["d"] >= inicio.strftime("%Y-%m-%d")][:VOT_MAX]
    recentes = {v["id"] for v in candidatas}
    return {
        "atualizado": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "fonte": "Dados Abertos da Câmara dos Deputados (votações nominais do plenário)",
        "votacoes": votacoes,
        "checadas": sorted(checadas & recentes),
    }


def main():
    fontes = json.loads(FONTES.read_text(encoding="utf-8"))["fontes"]
    municipios = json.loads(MUNICIPIOS.read_text(encoding="utf-8"))
    regras = preparar_cidades(municipios)
    nomes = {m["n"] for m in municipios}

    anterior = {"itens": []}
    if SAIDA.exists():
        anterior = json.loads(SAIDA.read_text(encoding="utf-8"))
    por_link = {chave_item(i): i for i in anterior.get("itens", [])}

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

    # Decretos das prefeituras de todo o estado (Querido Diário): 3 vezes ao dia.
    tem_qd = any(i.get("qd") for i in por_link.values())
    if not tem_qd or agora.hour in (8, 14, 20) or "--diarios" in sys.argv:
        try:
            qd, cobertas = coletar_diarios(municipios, agora)
            for item in qd:
                k = chave_item(item)
                if k not in por_link:
                    novos += 1
                    por_link[k] = item
            ok.append(f"Diários Oficiais municipais (Querido Diário, {cobertas} cidades com edição recente)")
            print(f"diários municipais: {len(qd)} decretos de {cobertas} cidades")
        except Exception as e:
            erros.append({"fonte": "Diários Oficiais municipais (Querido Diário)", "erro": str(e)[:160]})
    else:
        ok.append("Diários Oficiais municipais (Querido Diário)")

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

    for tarefa, funcao in (("arquivo", lambda: atualizar_arquivo(itens)), ("rss", lambda: atualizar_rss(itens, municipios)), ("videos", atualizar_videos)):
        try:
            funcao()
        except Exception as e:
            print(f"  erro no {tarefa}:", str(e)[:160])

    # Deputados: a Alesp atualiza de madrugada; o robô refaz uma vez por dia (ou se faltar o arquivo).
    if not DEPUTADOS.exists() or agora.hour == 7 or "--deputados" in sys.argv:
        try:
            dados = coletar_deputados(regras, agora)
            DEPUTADOS.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"deputados: {len(dados['deputados'])} em exercício · proposituras até {dados['dados_ate']}")
        except Exception as e:
            print("  erro nos deputados:", str(e)[:160])

    # Gastos de gabinete e deputados federais: uma vez por dia (ou se faltar o arquivo).
    gastos = None
    if not GASTOS.exists() or agora.hour == 7 or "--gastos" in sys.argv:
        try:
            gastos = coletar_gastos(agora)
            GASTOS.write_text(json.dumps(gastos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"gastos: {len(gastos['camara']['deps'])} federais e {len(gastos['alesp']['deps'])} estaduais")
        except Exception as e:
            print("  erro nos gastos:", str(e)[:160])
    if not FEDERAIS.exists() or agora.hour == 7 or "--federais" in sys.argv:
        try:
            if gastos is None and GASTOS.exists():
                gastos = json.loads(GASTOS.read_text(encoding="utf-8"))
            fed = coletar_federais(regras, agora, gastos)
            if fed["deputados"]:
                FEDERAIS.write_text(json.dumps(fed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"federais: {len(fed['deputados'])} deputados")
        except Exception as e:
            print("  erro nos federais:", str(e)[:160])
    # Votações nominais da Câmara: 7h e 19h (as sessões costumam terminar à noite).
    if not VOTACOES.exists() or agora.hour in (7, 19) or "--votacoes" in sys.argv:
        try:
            vot = coletar_votacoes(agora)
            gravar_se_mudou(VOTACOES, json.dumps(vot, ensure_ascii=False, separators=(",", ":")))
            print(f"votações: {len(vot['votacoes'])} nominais")
        except Exception as e:
            print("  erro nas votações:", str(e)[:160])
    print(f"{novos} notícias novas · {len(itens)} no total · {len(ok)} jornais lidos · {len(erros)} com erro")
    for e in erros:
        print("  erro:", e["fonte"], "-", e["erro"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
