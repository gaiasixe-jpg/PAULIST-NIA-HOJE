# Paulistânia Hoje — como colocar o site no ar

Este pacote é o site completo e independente do Paulistânia Hoje. Ele fica hospedado de graça no GitHub, qualquer pessoa abre sem precisar de conta, e um robô gratuito lê os jornais de hora em hora e atualiza as notícias sozinho.

Tempo para colocar no ar: cerca de 30 minutos, só pelo navegador.

## O que tem no pacote

| Arquivo | Para que serve |
| --- | --- |
| `index.html` | O site inteiro (mapa, jornal, decretos, cidades, regiões, promessas) |
| `data/feed.json` | Notícias que o robô coleta. **Não precisa mexer.** |
| `data/manual.json` | Notícias e decretos que você cadastra à mão, com resumo próprio |
| `data/promessas.json` | O placar das promessas do governador |
| `data/municipios.json` | Os 645 municípios (nome, código IBGE, posição no mapa, DDD) |
| `scripts/coletar.py` | O robô que lê os jornais |
| `scripts/fontes.json` | A lista de jornais que o robô lê |
| `.github/workflows/coletar.yml` | O "despertador" que liga o robô de hora em hora |

## Passo 1 — Criar a conta no GitHub

1. Entre em https://github.com/signup e crie uma conta gratuita.
2. Escolha bem o nome de usuário: ele aparece no endereço do site. Exemplo: com o usuário `paulistaniahoje`, o site fica em `https://paulistaniahoje.github.io/`.

## Passo 2 — Criar o repositório (a "pasta" do site)

1. Clique no **+** no canto superior direito e em **New repository**.
2. Em **Repository name**, escreva: `paulistaniahoje.github.io` (troque `paulistaniahoje` pelo seu usuário). Com esse nome, o site fica no endereço principal, sem nada depois da barra.
3. Marque **Public**. A hospedagem gratuita do GitHub exige repositório público.
4. Clique em **Create repository**.

## Passo 3 — Enviar os arquivos

1. Na página do repositório, clique em **uploading an existing file** (ou **Add file → Upload files**).
2. Descompacte o pacote no seu computador e arraste para a página: `index.html`, `LEIA-ME.md` e as pastas `data` e `scripts`.
3. Clique em **Commit changes**.

A pasta `.github` costuma ficar escondida no computador e não vai junto no arrastar. Crie esse arquivo direto no site:

4. Clique em **Add file → Create new file**.
5. No nome do arquivo, digite exatamente: `.github/workflows/coletar.yml` (as barras criam as pastas sozinhas).
6. Abra o arquivo `coletar.yml` do pacote num bloco de notas, copie tudo e cole na caixa grande.
7. Clique em **Commit changes**.

## Passo 4 — Dar permissão ao robô para salvar as notícias

1. No repositório, clique em **Settings** (Configurações).
2. No menu da esquerda: **Actions → General**.
3. Desça até **Workflow permissions**, marque **Read and write permissions** e clique em **Save**.

## Passo 5 — Ligar o site

1. Ainda em **Settings**, clique em **Pages** no menu da esquerda.
2. Em **Source**, escolha **Deploy from a branch**.
3. Em **Branch**, escolha **main** e a pasta **/ (root)**. Clique em **Save**.
4. Espere de 1 a 3 minutos e recarregue a página: aparece o endereço do site, por exemplo `https://paulistaniahoje.github.io/`.

## Passo 6 — Rodar o robô pela primeira vez

1. Clique na aba **Actions** do repositório.
2. Se aparecer um aviso pedindo para ativar os workflows, clique no botão verde para ativar.
3. Clique em **Coletar notícias** à esquerda e depois em **Run workflow → Run workflow**.
4. Em 1 a 2 minutos aparece um visto verde. As notícias já estão no site.

A partir daí, o robô roda sozinho de hora em hora (aos 17 minutos de cada hora). Você não precisa fazer mais nada.

## Como cadastrar uma notícia ou decreto com resumo próprio

1. No repositório, abra `data/manual.json` e clique no lápis (**Edit this file**).
2. Copie um bloco inteiro, de `{` até `},`, e cole logo abaixo de `"itens": [`.
3. Troque os campos:
   - `d`: data no formato `2026-11-05`
   - `t`: título
   - `p`: resumo
   - `tema`: por exemplo `Saúde`, `Educação`, `Decretos`
   - `s`: `fato`, `decreto`, `entregue`, `obra`, `anunciado` ou `alerta`
   - `c`: cidades, com o nome oficial, por exemplo `["Votuporanga", "Fernandópolis"]`
   - `src`: nome da fonte
   - `u`: link começando com `https://`
   - Só para decretos: `num` (por exemplo `"Nº 1.234"`) e `org` (`"Prefeitura"` ou `"Estado"`)
4. Clique em **Commit changes**. Em cerca de 1 minuto está no site.

Cuidado com as aspas e as vírgulas: cada bloco termina com `},` menos o último da lista. Se o site parar de mostrar as notícias manuais, provavelmente faltou ou sobrou uma vírgula.

## Como marcar uma promessa como cumprida

1. Abra `data/promessas.json` e clique no lápis.
2. Ache o número da promessa (p01 a p38, na mesma ordem da tabela do site).
3. Troque `"status": "acompanhar"` por `cumprido`, `andamento`, `atrasado` ou `naocumprido`.
4. Em `"prova"`, cole o link que comprova. Em `"nota"`, escreva uma observação curta.
5. Clique em **Commit changes**.

## Como acrescentar um jornal

1. Abra `scripts/fontes.json` e clique no lápis.
2. Copie uma linha de jornal e troque `nome` e `feed`. O feed costuma ser o endereço do site com `/feed/` no final. Para testar, abra o endereço no navegador: se aparecer uma página de código com várias notícias, funciona.
3. Se o jornal for de uma cidade só, acrescente `"cidade": "Nome Oficial"`.
4. Se for o site de notícias de uma prefeitura, acrescente também `"oficial": true`. Assim entra tudo o que a prefeitura publica, menos esporte e entretenimento.

## Correções e denúncias do público

O botão "Mandar por e-mail" (aba Sobre) e o link "Corrigir" em cada notícia abrem um e-mail para aranellin@gmail.com já com o título e o link da notícia. Para trocar o endereço, abra `index.html`, procure `var MAIL=` e troque o e-mail.

## Ter um endereço próprio (opcional)

1. Compre o domínio em https://registro.br (por exemplo `paulistaniahoje.com.br`).
2. No repositório, vá em **Settings → Pages → Custom domain**, digite o domínio e salve.
3. No Registro.br, configure o DNS conforme a página de ajuda do GitHub Pages ("Managing a custom domain"), que mostra os endereços a cadastrar.

## O que é bom saber

- **De onde vêm as notícias:** dos feeds RSS oficiais dos próprios jornais. O site mostra o título, a data, o trecho que o jornal publicou e o link para a matéria completa. A notícia inteira fica no site do jornal.
- **A classificação é automática:** tema, situação (alerta, entregue…) e cidade são marcados por palavras-chave e podem errar. A fonte e o link são sempre os do jornal.
- **Decretos e leis do Estado:** vêm sozinhos da base oficial de legislação da Alesp, que registra o que sai no Diário Oficial. A Alesp atualiza essa base uma vez por dia, então o robô a consulta três vezes ao dia (7h, 13h e 19h). Os decretos de crédito suplementar do mesmo dia aparecem juntos num item só.
- **Jornais que bloqueiam o robô:** A Tribuna, Jornal Cruzeiro do Sul e Correio da Manhã recusam a leitura automática. Para ver quais funcionaram, abra `data/feed.json` e procure `fontes_com_erro`.
- **Cobertura regional:** Baixada Santista, Sorocaba, Presidente Prudente, Vale do Ribeira e Alta Paulista ganharam jornais e sites oficiais de prefeitura na lista. Vale continuar procurando jornais com feed nessas regiões.
- **Se o robô parar:** o GitHub pode pausar tarefas automáticas de repositórios sem atividade por 60 dias. Como o robô salva notícias toda hora, isso não deve acontecer. Se acontecer, vá em **Actions → Coletar notícias** e clique em **Enable workflow**.
- **Se um jornal pedir para sair da lista:** apague a linha dele em `scripts/fontes.json`.
