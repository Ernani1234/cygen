# Cygen 3

Grava o que você faz no navegador e escreve o teste — depois **roda o teste**
para provar que ele funciona.

Reimaginação do CypressGen Pro v2. A ideia original continua: gravar a jornada,
inferir a intenção, gerar o teste, refinar com IA. O que mudou foi tudo abaixo
disso.

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

## Início rápido (Windows)

Dê um clique duplo em **`Cygen.bat`**. Ele verifica o ambiente, instala o que
faltar e abre o aplicativo.

```
Cygen.bat          aplicativo de desktop
Cygen.bat web      só o backend, abre no navegador
Cygen.bat setup    instala as dependências e sai
```

Rodar por um `.bat` evita dois obstáculos do PowerShell de uma vez: a política
de execução que bloqueia `npm.ps1`, e o operador `&&` que a versão 5.1 não
reconhece. O script também limpa `ELECTRON_RUN_AS_NODE`, que faz o Electron
abrir como Node puro e falhar sem explicar o motivo.

O restante desta seção é para quem prefere rodar na mão.

---

## Instalação manual

Um comando por linha. **No PowerShell não use `&&`** — a versão 5.1, padrão do
Windows, não reconhece esse operador e responde
`O token '&&' não é um separador de instruções válido`.

```powershell
cd cygen-next\server
pip install -r requirements.txt
python -m playwright install chromium

cd ..\desktop
npm install
```

O `requirements.txt` fica em `server\`, não na raiz do projeto.

### Rodar

Como aplicativo de desktop (o Electron sobe o backend sozinho):

```powershell
cd cygen-next\desktop
npm start
```

Ou só o backend, abrindo a interface no navegador:

```powershell
cd cygen-next\server
python -m cygen
```

Ele imprime o endereço — normalmente <http://127.0.0.1:8756>. Se a porta
estiver ocupada, escolhe outra livre e mostra qual.

### Empacotar

```powershell
cd cygen-next\desktop
npm run dist:win
```

Gera o instalador em `cygen-next\dist\`. Para outras plataformas:
`npm run dist:mac` ou `npm run dist:linux`.

### Problemas comuns no Windows

**`npm : O arquivo npm.ps1 não pode ser carregado porque a execução de scripts
foi desabilitada`**

O PowerShell bloqueia scripts `.ps1` por padrão, e o `npm` do Windows é um
wrapper `.ps1`. Use `npm.cmd`, que é um arquivo de lote e não passa por essa
política:

```powershell
npm.cmd install
npm.cmd start
```

Se preferir resolver de vez para o seu usuário (não afeta a máquina toda):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`npm start` roda mas nenhuma janela abre**

A variável `ELECTRON_RUN_AS_NODE` faz o Electron rodar como Node puro. Alguns
terminais e ferramentas de desenvolvimento a deixam definida sem avisar:

```powershell
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
npm.cmd start
```

**Nada disso resolveu**

Chame o Electron direto, pulando o npm inteiro:

```powershell
.\node_modules\.bin\electron.cmd .
```

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
cygen-next/
├── server/cygen/
│   ├── recorder/        engine.py (Playwright) + injector.js (na página)
│   ├── intel/           oracle.py, selectors.py, intent.py, catalog.py
│   ├── emit/            ir.py, build.py, cypress.py, playwright_ts.py
│   ├── ai/              registry.py (23 provedores), client.py
│   ├── verify/          healer.py (executa e cura)
│   ├── app.py           FastAPI + WebSocket
│   └── store.py         persistência
├── ui/                  HTML/CSS/JS puro, sem build
└── desktop/             shell Electron
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
