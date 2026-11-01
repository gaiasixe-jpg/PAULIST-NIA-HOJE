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
DEPUTADOS = RAIZ / "data" / "deputados.json"
ARQUIVO = RAIZ / "data" / "arquivo"
RSS = RAIZ / "data" / "rss"
SITE = "https://gaiasixe-jpg.github.io/PAULIST-NIA-HOJE/"
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

    for tarefa, funcao in (("arquivo", lambda: atualizar_arquivo(itens)), ("rss", lambda: atualizar_rss(itens, municipios))):
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
    print(f"{novos} notícias novas · {len(itens)} no total · {len(ok)} jornais lidos · {len(erros)} com erro")
    for e in erros:
        print("  erro:", e["fonte"], "-", e["erro"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
