# Cygen 3

Grava o que você faz no navegador e escreve o teste — depois **roda o teste**
para provar que ele funciona.

Reimaginação do CypressGen Pro v2. A ideia original continua: gravar a jornada,
inferir a intenção, gerar o teste, refinar com IA. O que mudou foi tudo abaixo
disso.

> Esta é a branch **`v3`**. A `main` guarda a v2 original, em Python/Tkinter —
> outro projeto, outra stack.

---

## Instalar numa máquina nova

### 1. Pré-requisitos

| | Versão | Precisa mesmo? |
|---|---|---|
| **Python** | 3.10 ou superior | Sim. É o backend inteiro |
| **Node.js** | 18 ou superior | Só para a janela de desktop e para rodar o Cypress. Sem ele o Cygen abre no navegador e funciona igual |
| **Git** | qualquer | Para clonar |

Ao instalar o Python no Windows, marque **"Add Python to PATH"**. Sem isso o
inicializador não o encontra.

Você **não precisa** de Git LFS. A `main` rastreia os `.py` com LFS, mas esta
branch não — o código aqui é texto normal.

### 2. Clonar

```powershell
git clone -b v3 https://github.com/Ernani1234/cygen.git
cd cygen
```

O `-b v3` traz a branch certa já no checkout. Se você clonar sem ele, cai na
`main` (a v2) e precisa de `git checkout v3`.

### 3. Rodar

```powershell
.\Cygen.bat
```

É só isso. O inicializador verifica o ambiente, instala o que faltar e abre o
aplicativo:

```
  Cygen
  ---------------------------------------------------------------

  [ok] Python 3.12.10
  [..] Instalando dependencias Python. Demora um pouco na primeira vez.
  [..] Baixando o Chromium do Playwright (cerca de 150 MB, so desta vez)
  [..] Instalando o Electron (cerca de 200 MB, so desta vez)

  Iniciando o Cygen...
```

A primeira execução baixa cerca de 400 MB e leva de 3 a 8 minutos conforme a
conexão. As seguintes abrem em segundos.

Modos alternativos:

```powershell
.\Cygen.bat web      # sem Electron: abre no seu navegador
.\Cygen.bat setup    # só instala e sai, sem abrir nada
```

### 4. Conferir se deu certo

Abra **Configurações → Verificar ambiente**. Deve mostrar o navegador pronto e
a contagem de provedores. Se o Chromium aparecer indisponível, rode
`.\Cygen.bat setup` de novo.

### macOS e Linux

O `.bat` é do Windows. Nesses sistemas, três comandos:

```bash
cd server
pip install -r requirements.txt
python -m playwright install chromium
python -m cygen           # abre em http://127.0.0.1:8756
```

Para a janela de desktop:

```bash
cd desktop && npm install && npm start
```

### O que não vem no clone

O repositório traz só o código. Ficam de fora, por design:

| | Onde vive | Por quê |
|---|---|---|
| Fluxos gravados | `%LOCALAPPDATA%\Cygen` (Win) · `~/.local/share/cygen` | São seus dados, e podem conter informação de produção |
| Projetos gerados | `Documentos\Cygen` | Artefato seu, para abrir no editor e versionar à parte |
| Chaves de IA | variáveis de ambiente | Nunca são gravadas em arquivo |
| `node_modules` | ignorado pelo git | 558 MB; o `Cygen.bat` reinstala |

Então numa máquina nova você começa sem fluxos. Isso é intencional.

### Se algo der errado

| Mensagem | Causa | Solução |
|---|---|---|
| `npm : O arquivo npm.ps1 não pode ser carregado` | O PowerShell bloqueia scripts `.ps1`, e o `npm` do Windows é um | Rode pelo `.bat`, que usa `cmd`. Direto no terminal, use `npm.cmd` |
| `npm start` roda mas nenhuma janela abre | `ELECTRON_RUN_AS_NODE` definida no ambiente faz o Electron virar Node puro | `Remove-Item Env:ELECTRON_RUN_AS_NODE` — o `Cygen.bat` já limpa sozinho |
| `bad option: --smoke-test` ao rodar o Cypress | A mesma variável. O Cypress também é um app Electron | Idem acima |
| `Python nao encontrado` | Não está no PATH | Reinstale marcando "Add Python to PATH", ou aponte: `set CYGEN_PYTHON=C:\caminho\python.exe` |
| `A pasta atual não é válida` ao rodar um projeto | O Python da Microsoft Store virtualiza `AppData\Local`, e o `node` não enxerga a pasta | Já resolvido: os projetos vão para `Documentos\Cygen`. Se persistir, gere o projeto de novo |
| `token '&&' não é um separador válido` | PowerShell 5.1 não aceita `&&` | Um comando por linha |

---

## Por que a v2 gerava testes que quebravam

Um teste real produzido pela versão anterior:

```js
cy.get(".q-focus-helper", { timeout: 5000 }).should('be.visible').click();
cy.get('body').should('exist');
cy.get(".q-focus-helper", { timeout: 5000 }).should('be.visible').click();
cy.get('body').should('exist');
cy.url().should('include', '/success');
```

Quatro problemas, todos estruturais:

| Sintoma | Causa |
|---|---|
| `.q-focus-helper` como alvo | O clique caía na camada de ripple do Quasar, e nada olhava para o que estava por baixo |
| A mesma linha repetida | Cada evento bruto virava um comando; nada agrupava por intenção |
| `should('exist')` no `body` | Não havia como saber o que a página fez, então a assertion era decorativa |
| `/success` inventado | A URL nunca foi observada — o texto veio de um palpite do LLM |

O Cygen 3 ataca cada um deles com um mecanismo específico.

---

## Como funciona

```
navegador  ──▶  gravador  ──▶  compilador  ──▶  Oracle  ──▶  emissor  ──▶  verificador
(Playwright)   (injector.js)   (intenção)     (assertions)  (IR→código)   (executa e cura)
```

### 1. Gravador

Playwright com `add_init_script`, reinstalado a cada navegação, iframe e recarga.
A v2 injetava listeners uma vez via `execute_script` e os perdia na primeira
troca de rota — numa SPA com hash isso passava despercebido até o teste sair
vazio.

Captura por ação: descritor do elemento, cadeia de ancestrais, elementos **sob o
cursor** (`elementsFromPoint`), diff de DOM antes/depois, requisições
correlacionadas, delta de `localStorage` e erros de console.

A atribuição é causal, não temporal: quando uma ação nova começa, as janelas de
observação ainda abertas são fechadas naquele instante. Sem isso, a digitação
(cuja janela é longa por causa do debounce) absorveria a reação ao clique que
veio depois dela, e a evidência apareceria no passo errado.

### 2. Compilador de intenção

Quatro passagens: **retarget** (sobe pelos ancestrais ou olha por baixo até
achar o elemento que carrega a ação), **colapso** (funde teclas numa digitação,
descarta cliques redundantes antes de digitar, elimina navegações já cobertas
pelo clique que as causou), **segmentação** (agrupa em blocos: Autenticação,
Preenchimento, Envio) e **enriquecimento**.

Os eventos são ordenados por instante de ocorrência, não de chegada — um clique
lento é emitido depois da navegação que ele mesmo provocou.

### 3. Oracle — a IA nativa de custo zero

**19 regras** que olham a evidência e deduzem qual assertion descreve o que
aconteceu. Sem chave, sem rede, sem token, sem alucinação: cada sugestão aponta
para o fato que a originou, e cada uma vem com a justificativa em português.

Exemplos do que ele reconhece sozinho:

- Requisição disparada pela ação → `cy.intercept` + `cy.wait('@alias')`,
  eliminando `cy.wait(3000)`
- Spinner que apareceu e sumiu → `should('not.exist')` no spinner
- Rota de SPA que mudou → `cy.location('hash')` com o valor real
- Toast com `role="alert"` → `cy.contains(texto).should('be.visible')`
- `localStorage` ganhou uma chave de sessão → assertion de sessão estabelecida
- Lista que saiu de vazia → `have.length.at.least(1)`, não um número fixo
- **Campo com máscara** → afirma o valor que o DOM guardou (`123.456.789-01`),
  não o que foi digitado (`12345678901`)
- **Valor volátil** (data, uuid, moeda) → afirma o *formato* por regex, não o
  conteúdo, para o teste continuar válido amanhã
- **Campo de senha** → nunca escreve o valor; usa `Cypress.env()`

#### O Oracle também revisa código

Além de deduzir assertions a partir de eventos, ele lê um teste pronto e aponta
o que vai doer — **18 regras** de análise estática, também sem custo. Clique em
*Pedir revisão à IA* na aba Código e a análise sai na hora, sem passo extra.

Detecta espera por tempo fixo, seletor acoplado a framework, id gerado em
runtime, credencial escrita no arquivo, assertion que sempre passa
(`cy.get('body').should('exist')`), assertion sobre valor volátil, `force: true`
mascarando overlay, seleção por índice, teste sem nenhuma verificação e nome de
teste que não descreve nada. Cada achado traz a linha, o motivo e o conserto.

Também reconhece o que está certo — intercept com espera por alias, atributos
dedicados a teste, credenciais no ambiente — porque uma revisão que só reclama
ensina menos que uma que mostra o padrão bom ao lado do ruim.

O teste que a v2 gerava tira **nota 0**; o que o Cygen 3 gera tira 99.

### 4. Motor de seletores

Gera todos os candidatos, mede a unicidade de cada um **na página real** e
pontua combinando intenção (o atributo existe para teste?), unicidade, entropia
(parece gerado por máquina?) e acoplamento.

Descarta classes de framework (`q-`, `Mui`, `ant-`, Tailwind, CSS Modules) e ids
gerados (`f_5b7d19ae-...`). Emite um primário e reservas de **estratégias
diferentes** — se o primário morre num redesign, outra classe CSS morre junto.

### 5. Emissores

Os passos viram uma IR neutra; cada emissor traduz para seu alvo. Cypress e
Playwright saem do mesmo fluxo gravado. Escape correto: `O'Brien & Cia "Ltda"`
não quebra mais o arquivo.

#### Projeto completo, não só o spec

Um `.cy.js` solto não roda — falta configuração, `package.json` e a pasta
`support/`. O botão **Gerar projeto completo** monta tudo:

```
cypress.config.js         baseUrl, timeouts, 1 retentativa em CI
package.json              dependência e scripts
cypress/e2e/*.cy.js       o teste, com caminhos relativos à baseUrl
cypress/support/commands.js   comandos extraídos das repetições
cypress/support/e2e.js
cypress.env.example.json  onde as credenciais entram
.gitignore                já ignora cypress.env.json
README.md                 como rodar
```

Depois de gerar, a própria tela tem os botões:

**Rodar agora** instala o Cypress se preciso, grava a credencial em
`cypress.env.json` e executa a suíte — o resultado aparece na interface, com as
falhas detalhadas. **Abrir o Cypress** faz o mesmo e abre a janela do Cypress já
na pasta certa. **Abrir pasta** revela o projeto no explorador.

Nada de copiar comando para o terminal: o Cygen sabe a pasta, sabe quais
credenciais o teste pede e sabe chamar o npm.

> Os projetos vão para `Documentos\Cygen`, não para `AppData`. O Python da
> Microsoft Store virtualiza `AppData\Local` — o interpretador enxerga a pasta,
> mas `node` e `cmd.exe` não. Rodar de lá falhava com "A pasta atual não é
> válida", um erro que não menciona virtualização nenhuma.

A extração de comandos é feita, não sugerida. Uma sequência de login vira
`cy.login()` chamado no `beforeEach`; seletores que se repetem três vezes ou
mais viram comandos nomeados a partir do próprio elemento. É por isso que a
revisão não fica repetindo "extraia para commands.js": o Cygen extrai.

O `cy.session()` fica gerado e **comentado**, com a explicação de quando
ativar. Ele acelera muito uma suíte grande, mas depende de a aplicação
reconhecer a sessão ao recarregar uma rota — muitas SPAs começam sempre na tela
de login e ignoram o storage até o formulário ser enviado. Ligar por padrão
produziria testes que quebram reclamando de rota errada.

### 6. Verificador com auto-cura

Roda o fluxo num navegador headless — **executando as ações**, não só checando
seletores. Se o primário não resolve, testa as reservas, promove a que funciona
e reescreve o código. O relatório diz o que passou, o que foi curado e o que
não deu.

---

## Empacotar como instalador

```powershell
cd desktop
npm.cmd run dist:win
```

Gera o instalador em `dist\`. Para outras plataformas: `dist:mac`, `dist:linux`.

O empacotamento inclui o backend Python como recurso, mas **não** inclui um
interpretador. A máquina de destino precisa ter Python 3.10+ instalado — o
`main.js` procura por `py -3`, `python` e `python3`, nessa ordem.

---

## Provedores de IA

23 provedores, 47 modelos. O modo nativo (Oracle) funciona sempre, sem
configurar nada. Para os demais, defina a variável de ambiente e reinicie:

| Provedor | Variável |
|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google (Gemini) | `GEMINI_API_KEY` |
| Mistral, Groq, DeepSeek, xAI, Cohere | `MISTRAL_API_KEY`, `GROQ_API_KEY`, … |
| Together, Fireworks, Perplexity, OpenRouter | `TOGETHER_API_KEY`, … |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` |
| Moonshot, Qwen, Zhipu, NVIDIA, Cerebras | `MOONSHOT_API_KEY`, `DASHSCOPE_API_KEY`, … |
| Hugging Face, GitHub Models | `HF_TOKEN`, `GITHUB_TOKEN` |
| Ollama, LM Studio (locais) | nenhuma |

Cada modelo declara o que aceita. Isso não é detalhe: os modelos Claude atuais
respondem **HTTP 400** se `temperature` aparecer na requisição — a v2, que
mandava `temperature: 0.7` para todo mundo, quebraria contra eles.

**Chaves nunca são gravadas em arquivo.** Só variáveis de ambiente.

---

## Estrutura

```
Cygen.bat                inicializador (Windows)
server/
  requirements.txt
  cygen/
    recorder/            engine.py (Playwright) + injector.js (na página)
    intel/               oracle.py, review.py, selectors.py, intent.py
    emit/                ir.py, build.py, cypress.py, playwright_ts.py,
                         scaffold.py (monta o projeto completo)
    ai/                  registry.py (23 provedores), client.py
    verify/              healer.py (executa e cura), runner.py (roda o projeto)
    app.py               FastAPI + WebSocket
    store.py             persistência
ui/                      HTML/CSS/JS puro, sem build step
desktop/                 shell Electron
```

---

## Atalhos

| Tecla | Ação |
|---|---|
| `Ctrl K` | paleta de comandos |
| `Ctrl Enter` | gerar código (na aba Código) |
| `Esc` | fechar a paleta |

---

## O que mudou em relação à v2

| | v2 | v3 |
|---|---|---|
| Automação | Selenium + `chromedriver.exe` versionado | Playwright, baixa o navegador sozinho |
| Captura | polling a cada 100ms, perdia eventos em SPA | init script persistente, diff de DOM |
| Assertions | lista manual em wizard de 5 etapas | 19 regras deduzem da evidência real |
| Seletores | primeiro da lista de prioridade | ranqueados por unicidade medida |
| Geração | concatenação de string | IR → Cypress + Playwright |
| Escape | `O'Brien` quebrava o arquivo | correto |
| Verificação | nenhuma | executa o teste e cura seletores |
| IA | gpt-3.5 fixo, preço de 2023 | 23 provedores + Oracle local |
| Segredos | chave em `config.json`, senha no teste | variáveis de ambiente, `Cypress.env()` |
| Interface | Tkinter tema escuro | UI pastel animada, clara/escura |
```
