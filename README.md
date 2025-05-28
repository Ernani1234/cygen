# CypressGen Pro v2 - Documentação

## Visão Geral

O CypressGen Pro v2 é uma ferramenta avançada para geração e edição de testes automatizados Cypress, com foco na captura de interações do usuário, geração inteligente de testes e edição assistida por IA. A ferramenta foi projetada para simplificar o processo de criação de testes Cypress, seguindo a estrutura específica do seu projeto.

## Principais Funcionalidades

- **Captura de Elementos**: Registra todas as interações do usuário no navegador, incluindo cliques, digitação, navegação e requisições de API.
- **Geração de Testes**: Cria testes Cypress automaticamente a partir das interações capturadas, seguindo a estrutura específica do seu projeto.
- **Editor com IA**: Permite editar e melhorar os testes com assistência de IA, com suporte a comandos personalizados, fixtures e helpers.
- **Gerenciamento de Logs**: Armazena e gerencia logs de captura para referência futura e reuso.
- **Controle de Custos**: Monitora e controla o uso da API de IA, com estimativas precisas de custos.
- **Interface Visual Dinâmica**: Interface moderna com tema escuro, responsiva e intuitiva.

## Requisitos do Sistema

- Python 3.6 ou superior
- Bibliotecas Python:
  - selenium
  - ttkbootstrap
  - requests
  - Pillow (PIL)
  - tiktoken (instalado automaticamente)
- Navegador Chrome ou Edge
- Conexão com a Internet (para uso da API de IA)

## Instalação

1. Extraia o arquivo ZIP em uma pasta de sua escolha
2. Instale as dependências necessárias:

```bash
pip install selenium ttkbootstrap requests pillow
```

3. Execute o aplicativo:

```bash
python main.py
```

## Estrutura do Projeto

```
cypress_gen_pro_v2/
├── main.py                  # Arquivo principal da aplicação
├── modules/                 # Módulos da aplicação
│   ├── ai_editor.py         # Editor com assistência de IA
│   ├── ai_integration.py    # Integração com API de IA
│   ├── element_capture.py   # Captura de elementos
│   ├── settings.py          # Gerenciamento de configurações
│   ├── test_generator.py    # Gerador de testes
│   └── utils/               # Utilitários
│       ├── icon_manager.py  # Gerenciamento de ícones
│       └── theme_manager.py # Gerenciamento de temas
├── config/                  # Configurações salvas
├── logs/                    # Logs de captura
├── tests/                   # Testes gerados
└── resources/               # Recursos (ícones, etc.)
```

## Guia de Uso

### 1. Captura de Elementos

1. Acesse a aba "Captura de Elementos"
2. Insira a URL do site a ser testado
3. Clique em "Iniciar Captura"
4. Realize as interações desejadas no navegador
5. Clique em "Parar Captura" quando terminar
6. Exporte os elementos capturados

### 2. Geração de Testes

1. Acesse a aba "Gerador de Testes"
2. Carregue os dados de captura
3. Configure o nome e descrição do teste
4. Selecione os elementos a serem incluídos no teste
5. Configure as assertions desejadas
6. Gere o código do teste
7. Revise e salve o teste gerado

### 3. Edição com IA

1. Acesse a aba "Editor com IA"
2. Carregue um teste existente ou continue a partir do teste gerado
3. Utilize o chat para solicitar modificações no código
4. Aplique as sugestões da IA conforme necessário
5. Salve o teste editado

### 4. Gerenciamento de Logs

1. Acesse a aba "Logs"
2. Visualize, filtre e gerencie os logs de captura
3. Gere novos testes a partir de logs existentes

### 5. Configurações

1. Acesse a aba "Configurações"
2. Configure as opções de API, seletores e aparência
3. Salve as configurações para uso futuro

## Integração com Estrutura de Testes Cypress

O CypressGen Pro v2 foi projetado para gerar testes que seguem a estrutura específica do seu projeto Cypress, incluindo:

- **Commands Personalizados**: Geração e uso de comandos personalizados definidos em `cypress/support/commands.js`
- **Fixtures**: Criação e referência a fixtures para dados de teste
- **Helpers**: Integração com helpers como `graphql-test-utils.js` para interceptação de requisições
- **Estrutura de Diretórios**: Respeito à organização de arquivos do seu projeto

## Controle de Custos da API

A ferramenta implementa um sistema de controle de custos para o uso da API de IA:

- Estimativa precisa de tokens e custos antes de cada requisição
- Confirmação do usuário antes de operações que geram custos
- Limite configurável de requisições por sessão
- Monitoramento de uso total com estatísticas detalhadas

## Personalização de Seletores

É possível personalizar a prioridade e uso de seletores para elementos:

1. Acesse "Configurações" > "Seletores"
2. Reordene a lista de prioridade de seletores
3. Habilite/desabilite seletores específicos
4. Salve as configurações

A ordem padrão de prioridade é: data-cy, data-testid, id, name, role, aria-label, class, tag, type.

## Solução de Problemas

### O navegador não inicia durante a captura

- Verifique se o Chrome ou Edge está instalado e atualizado
- Certifique-se de que o WebDriver está acessível
- Aumente o timeout nas configurações

### Erro na geração de testes

- Verifique sua chave de API nas configurações
- Certifique-se de que há elementos suficientes capturados
- Verifique sua conexão com a Internet

### Interface gráfica não carrega corretamente

- Certifique-se de que a biblioteca ttkbootstrap está instalada
- Tente usar um tema diferente nas configurações

## Exemplos de Uso

### Exemplo 1: Teste de Login

1. Capture a interação de login em um site
2. Gere um teste que verifica o fluxo de login
3. Adicione assertions para validar o sucesso do login
4. Edite o teste para adicionar tratamento de erros

### Exemplo 2: Teste de API

1. Capture interações que envolvem chamadas de API
2. Gere um teste que intercepta e valida as requisições
3. Utilize o editor com IA para adicionar validações específicas
4. Salve o teste para execução automatizada

## Próximos Passos

- Execute os testes gerados com o Cypress
- Integre os testes ao seu pipeline de CI/CD
- Expanda a biblioteca de testes com novos fluxos
- Personalize ainda mais a estrutura dos testes gerados

## Suporte

Para suporte ou dúvidas, entre em contato com a equipe de desenvolvimento.

---

© 2025 CypressGen Pro v2 - Todos os direitos reservados
