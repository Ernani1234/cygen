"""
Módulo para gerenciamento de assertions do Cypress.
Contém definições de todas as assertions disponíveis, organizadas por categorias.
Cada assertion inclui descrição, sintaxe e exemplos.
"""

class CypressAssertions:
    """
    Classe para gerenciar assertions do Cypress.
    Fornece acesso a todas as assertions disponíveis, organizadas por categorias.
    """
    
    @staticmethod
    def get_all_assertions():
        """
        Retorna todas as assertions disponíveis, organizadas por categorias.
        
        Returns:
            dict: Dicionário com categorias e suas assertions
        """
        return {
            "Visibilidade": {
                "exist": {
                    "description": "Verifica se o elemento existe no DOM",
                    "syntax": ".should('exist')",
                    "example": "cy.get('.elemento').should('exist')"
                },
                "not.exist": {
                    "description": "Verifica se o elemento não existe no DOM",
                    "syntax": ".should('not.exist')",
                    "example": "cy.get('.elemento-removido').should('not.exist')"
                },
                "be.visible": {
                    "description": "Verifica se o elemento está visível",
                    "syntax": ".should('be.visible')",
                    "example": "cy.get('button').should('be.visible')"
                },
                "not.be.visible": {
                    "description": "Verifica se o elemento não está visível",
                    "syntax": ".should('not.be.visible')",
                    "example": "cy.get('.elemento-oculto').should('not.be.visible')"
                }
            },
            "Estado": {
                "be.checked": {
                    "description": "Verifica se o checkbox ou radio está marcado",
                    "syntax": ".should('be.checked')",
                    "example": "cy.get('input[type=\"checkbox\"]').should('be.checked')"
                },
                "not.be.checked": {
                    "description": "Verifica se o checkbox ou radio não está marcado",
                    "syntax": ".should('not.be.checked')",
                    "example": "cy.get('input[type=\"checkbox\"]').should('not.be.checked')"
                },
                "be.disabled": {
                    "description": "Verifica se o elemento está desabilitado",
                    "syntax": ".should('be.disabled')",
                    "example": "cy.get('button[disabled]').should('be.disabled')"
                },
                "not.be.disabled": {
                    "description": "Verifica se o elemento não está desabilitado",
                    "syntax": ".should('not.be.disabled')",
                    "example": "cy.get('button').should('not.be.disabled')"
                },
                "be.enabled": {
                    "description": "Verifica se o elemento está habilitado",
                    "syntax": ".should('be.enabled')",
                    "example": "cy.get('button').should('be.enabled')"
                },
                "be.focused": {
                    "description": "Verifica se o elemento está com foco",
                    "syntax": ".should('be.focused')",
                    "example": "cy.get('input').should('be.focused')"
                },
                "not.be.focused": {
                    "description": "Verifica se o elemento não está com foco",
                    "syntax": ".should('not.be.focused')",
                    "example": "cy.get('button').should('not.be.focused')"
                },
                "be.selected": {
                    "description": "Verifica se a opção está selecionada",
                    "syntax": ".should('be.selected')",
                    "example": "cy.get('option').should('be.selected')"
                },
                "not.be.selected": {
                    "description": "Verifica se a opção não está selecionada",
                    "syntax": ".should('not.be.selected')",
                    "example": "cy.get('option').should('not.be.selected')"
                }
            },
            "Texto e Valor": {
                "have.text": {
                    "description": "Verifica se o elemento tem o texto exato",
                    "syntax": ".should('have.text', 'texto')",
                    "example": "cy.get('h1').should('have.text', 'Bem-vindo')"
                },
                "contain.text": {
                    "description": "Verifica se o elemento contém o texto",
                    "syntax": ".should('contain.text', 'texto')",
                    "example": "cy.get('p').should('contain.text', 'importante')"
                },
                "not.have.text": {
                    "description": "Verifica se o elemento não tem o texto exato",
                    "syntax": ".should('not.have.text', 'texto')",
                    "example": "cy.get('h1').should('not.have.text', 'Erro')"
                },
                "not.contain.text": {
                    "description": "Verifica se o elemento não contém o texto",
                    "syntax": ".should('not.contain.text', 'texto')",
                    "example": "cy.get('p').should('not.contain.text', 'erro')"
                },
                "have.value": {
                    "description": "Verifica se o elemento tem o valor exato",
                    "syntax": ".should('have.value', 'valor')",
                    "example": "cy.get('input').should('have.value', 'teste@email.com')"
                },
                "not.have.value": {
                    "description": "Verifica se o elemento não tem o valor exato",
                    "syntax": ".should('not.have.value', 'valor')",
                    "example": "cy.get('input').should('not.have.value', '')"
                },
                "contain.value": {
                    "description": "Verifica se o valor do elemento contém o texto",
                    "syntax": ".should('contain.value', 'texto')",
                    "example": "cy.get('input').should('contain.value', '@email')"
                },
                "have.html": {
                    "description": "Verifica se o elemento tem o HTML exato",
                    "syntax": ".should('have.html', 'html')",
                    "example": "cy.get('div').should('have.html', '<span>Texto</span>')"
                },
                "contain.html": {
                    "description": "Verifica se o HTML do elemento contém o texto",
                    "syntax": ".should('contain.html', 'html')",
                    "example": "cy.get('div').should('contain.html', '<span>')"
                }
            },
            "Atributos e Classes": {
                "have.attr": {
                    "description": "Verifica se o elemento tem o atributo com valor específico",
                    "syntax": ".should('have.attr', 'atributo', 'valor')",
                    "example": "cy.get('a').should('have.attr', 'href', 'https://exemplo.com')"
                },
                "have.attr (existência)": {
                    "description": "Verifica se o elemento tem o atributo (independente do valor)",
                    "syntax": ".should('have.attr', 'atributo')",
                    "example": "cy.get('img').should('have.attr', 'alt')"
                },
                "not.have.attr": {
                    "description": "Verifica se o elemento não tem o atributo",
                    "syntax": ".should('not.have.attr', 'atributo')",
                    "example": "cy.get('div').should('not.have.attr', 'disabled')"
                },
                "have.class": {
                    "description": "Verifica se o elemento tem a classe CSS",
                    "syntax": ".should('have.class', 'classe')",
                    "example": "cy.get('button').should('have.class', 'active')"
                },
                "not.have.class": {
                    "description": "Verifica se o elemento não tem a classe CSS",
                    "syntax": ".should('not.have.class', 'classe')",
                    "example": "cy.get('button').should('not.have.class', 'disabled')"
                },
                "have.css": {
                    "description": "Verifica se o elemento tem a propriedade CSS com valor específico",
                    "syntax": ".should('have.css', 'propriedade', 'valor')",
                    "example": "cy.get('div').should('have.css', 'color', 'rgb(255, 0, 0)')"
                },
                "have.prop": {
                    "description": "Verifica se o elemento tem a propriedade com valor específico",
                    "syntax": ".should('have.prop', 'propriedade', 'valor')",
                    "example": "cy.get('input').should('have.prop', 'checked', true)"
                },
                "have.id": {
                    "description": "Verifica se o elemento tem o ID específico",
                    "syntax": ".should('have.id', 'id')",
                    "example": "cy.get('div').should('have.id', 'main-content')"
                },
                "have.data": {
                    "description": "Verifica se o elemento tem o atributo data com valor específico",
                    "syntax": ".should('have.data', 'atributo', 'valor')",
                    "example": "cy.get('div').should('have.data', 'test-id', 'user-profile')"
                }
            },
            "Coleções e Listas": {
                "have.length": {
                    "description": "Verifica se a coleção tem o número exato de elementos",
                    "syntax": ".should('have.length', número)",
                    "example": "cy.get('li').should('have.length', 5)"
                },
                "have.length.greaterThan": {
                    "description": "Verifica se a coleção tem mais elementos que o número especificado",
                    "syntax": ".should('have.length.greaterThan', número)",
                    "example": "cy.get('tr').should('have.length.greaterThan', 2)"
                },
                "have.length.lessThan": {
                    "description": "Verifica se a coleção tem menos elementos que o número especificado",
                    "syntax": ".should('have.length.lessThan', número)",
                    "example": "cy.get('option').should('have.length.lessThan', 10)"
                },
                "have.length.at.least": {
                    "description": "Verifica se a coleção tem pelo menos o número especificado de elementos",
                    "syntax": ".should('have.length.at.least', número)",
                    "example": "cy.get('.item').should('have.length.at.least', 3)"
                },
                "have.length.at.most": {
                    "description": "Verifica se a coleção tem no máximo o número especificado de elementos",
                    "syntax": ".should('have.length.at.most', número)",
                    "example": "cy.get('.notification').should('have.length.at.most', 5)"
                }
            },
            "URL e Navegação": {
                "url.include": {
                    "description": "Verifica se a URL atual contém o texto",
                    "syntax": "cy.url().should('include', 'texto')",
                    "example": "cy.url().should('include', '/dashboard')"
                },
                "url.not.include": {
                    "description": "Verifica se a URL atual não contém o texto",
                    "syntax": "cy.url().should('not.include', 'texto')",
                    "example": "cy.url().should('not.include', '/admin')"
                },
                "url.eq": {
                    "description": "Verifica se a URL atual é exatamente igual ao texto",
                    "syntax": "cy.url().should('eq', 'url')",
                    "example": "cy.url().should('eq', 'https://exemplo.com/login')"
                },
                "url.match": {
                    "description": "Verifica se a URL atual corresponde ao padrão regex",
                    "syntax": "cy.url().should('match', /padrão/)",
                    "example": "cy.url().should('match', /\\/user\\/\\d+/)"
                },
                "location.pathname": {
                    "description": "Verifica o caminho da URL atual",
                    "syntax": "cy.location('pathname').should('eq', 'caminho')",
                    "example": "cy.location('pathname').should('eq', '/dashboard')"
                },
                "location.search": {
                    "description": "Verifica os parâmetros de consulta da URL atual",
                    "syntax": "cy.location('search').should('eq', 'parâmetros')",
                    "example": "cy.location('search').should('eq', '?id=123&type=user')"
                },
                "location.hash": {
                    "description": "Verifica o fragmento (hash) da URL atual",
                    "syntax": "cy.location('hash').should('eq', 'hash')",
                    "example": "cy.location('hash').should('eq', '#section2')"
                },
                "title.eq": {
                    "description": "Verifica se o título da página é exatamente igual ao texto",
                    "syntax": "cy.title().should('eq', 'título')",
                    "example": "cy.title().should('eq', 'Dashboard - Meu App')"
                },
                "title.include": {
                    "description": "Verifica se o título da página contém o texto",
                    "syntax": "cy.title().should('include', 'texto')",
                    "example": "cy.title().should('include', 'Dashboard')"
                }
            },
            "Requisições e Respostas": {
                "status": {
                    "description": "Verifica o código de status da resposta HTTP",
                    "syntax": ".should('have.property', 'status', código)",
                    "example": "cy.request('/api/users').should('have.property', 'status', 200)"
                },
                "statusText": {
                    "description": "Verifica o texto do status da resposta HTTP",
                    "syntax": ".should('have.property', 'statusText', 'texto')",
                    "example": "cy.request('/api/users').should('have.property', 'statusText', 'OK')"
                },
                "response.body": {
                    "description": "Verifica o corpo da resposta",
                    "syntax": ".its('body').should('deep.equal', objeto)",
                    "example": "cy.request('/api/user/1').its('body').should('deep.equal', { id: 1, name: 'João' })"
                },
                "response.body.property": {
                    "description": "Verifica uma propriedade específica no corpo da resposta",
                    "syntax": ".its('body').should('have.property', 'propriedade', valor)",
                    "example": "cy.request('/api/user/1').its('body').should('have.property', 'name', 'João')"
                },
                "response.headers": {
                    "description": "Verifica um cabeçalho específico na resposta",
                    "syntax": ".its('headers').should('have.property', 'cabeçalho', valor)",
                    "example": "cy.request('/api').its('headers').should('have.property', 'content-type', 'application/json')"
                }
            },
            "Comparações": {
                "eq": {
                    "description": "Verifica se o valor é igual ao esperado",
                    "syntax": ".should('eq', valor)",
                    "example": "cy.get('span').invoke('text').should('eq', '100')"
                },
                "not.eq": {
                    "description": "Verifica se o valor não é igual ao esperado",
                    "syntax": ".should('not.eq', valor)",
                    "example": "cy.get('span').invoke('text').should('not.eq', '0')"
                },
                "include": {
                    "description": "Verifica se o valor inclui o esperado",
                    "syntax": ".should('include', valor)",
                    "example": "cy.get('div').invoke('text').should('include', 'bem-vindo')"
                },
                "not.include": {
                    "description": "Verifica se o valor não inclui o esperado",
                    "syntax": ".should('not.include', valor)",
                    "example": "cy.get('div').invoke('text').should('not.include', 'erro')"
                },
                "match": {
                    "description": "Verifica se o valor corresponde ao padrão regex",
                    "syntax": ".should('match', /padrão/)",
                    "example": "cy.get('span').invoke('text').should('match', /\\d+\\.\\d{2}/)"
                },
                "not.match": {
                    "description": "Verifica se o valor não corresponde ao padrão regex",
                    "syntax": ".should('not.match', /padrão/)",
                    "example": "cy.get('div').invoke('text').should('not.match', /erro/i)"
                },
                "contain": {
                    "description": "Verifica se o array ou objeto contém o valor esperado",
                    "syntax": ".should('contain', valor)",
                    "example": "cy.get('li').should('contain', 'Item 3')"
                },
                "not.contain": {
                    "description": "Verifica se o array ou objeto não contém o valor esperado",
                    "syntax": ".should('not.contain', valor)",
                    "example": "cy.get('ul').should('not.contain', 'Item removido')"
                },
                "deep.equal": {
                    "description": "Verifica se o objeto é profundamente igual ao esperado",
                    "syntax": ".should('deep.equal', objeto)",
                    "example": "cy.window().its('app.state').should('deep.equal', { loggedIn: true })"
                }
            },
            "Numéricos": {
                "be.gt": {
                    "description": "Verifica se o valor é maior que o esperado",
                    "syntax": ".should('be.gt', número)",
                    "example": "cy.get('span').invoke('text').then(parseInt).should('be.gt', 10)"
                },
                "be.gte": {
                    "description": "Verifica se o valor é maior ou igual ao esperado",
                    "syntax": ".should('be.gte', número)",
                    "example": "cy.get('span').invoke('text').then(parseInt).should('be.gte', 100)"
                },
                "be.lt": {
                    "description": "Verifica se o valor é menor que o esperado",
                    "syntax": ".should('be.lt', número)",
                    "example": "cy.get('span').invoke('text').then(parseInt).should('be.lt', 50)"
                },
                "be.lte": {
                    "description": "Verifica se o valor é menor ou igual ao esperado",
                    "syntax": ".should('be.lte', número)",
                    "example": "cy.get('span').invoke('text').then(parseInt).should('be.lte', 100)"
                },
                "be.within": {
                    "description": "Verifica se o valor está dentro do intervalo esperado",
                    "syntax": ".should('be.within', min, max)",
                    "example": "cy.get('span').invoke('text').then(parseInt).should('be.within', 10, 50)"
                },
                "be.closeTo": {
                    "description": "Verifica se o valor está próximo ao esperado com uma margem",
                    "syntax": ".should('be.closeTo', número, margem)",
                    "example": "cy.get('span').invoke('text').then(parseFloat).should('be.closeTo', 100.5, 0.1)"
                }
            },
            "Outros": {
                "be.empty": {
                    "description": "Verifica se o elemento está vazio",
                    "syntax": ".should('be.empty')",
                    "example": "cy.get('ul').should('be.empty')"
                },
                "not.be.empty": {
                    "description": "Verifica se o elemento não está vazio",
                    "syntax": ".should('not.be.empty')",
                    "example": "cy.get('ul').should('not.be.empty')"
                },
                "be.true": {
                    "description": "Verifica se o valor é verdadeiro",
                    "syntax": ".should('be.true')",
                    "example": "cy.get('input').invoke('prop', 'checked').should('be.true')"
                },
                "be.false": {
                    "description": "Verifica se o valor é falso",
                    "syntax": ".should('be.false')",
                    "example": "cy.get('input').invoke('prop', 'disabled').should('be.false')"
                },
                "be.null": {
                    "description": "Verifica se o valor é nulo",
                    "syntax": ".should('be.null')",
                    "example": "cy.window().its('app.user').should('be.null')"
                },
                "not.be.null": {
                    "description": "Verifica se o valor não é nulo",
                    "syntax": ".should('not.be.null')",
                    "example": "cy.window().its('app.config').should('not.be.null')"
                },
                "be.undefined": {
                    "description": "Verifica se o valor é indefinido",
                    "syntax": ".should('be.undefined')",
                    "example": "cy.window().its('app.tempData').should('be.undefined')"
                },
                "not.be.undefined": {
                    "description": "Verifica se o valor não é indefinido",
                    "syntax": ".should('not.be.undefined')",
                    "example": "cy.window().its('app.init').should('not.be.undefined')"
                },
                "be.a": {
                    "description": "Verifica o tipo do valor",
                    "syntax": ".should('be.a', 'tipo')",
                    "example": "cy.get('button').invoke('prop', 'disabled').should('be.a', 'boolean')"
                },
                "be.an": {
                    "description": "Verifica o tipo do valor (alternativa para vogais)",
                    "syntax": ".should('be.an', 'tipo')",
                    "example": "cy.window().its('app.items').should('be.an', 'array')"
                }
            }
        }
    
    @staticmethod
    def get_assertion_categories():
        """
        Retorna as categorias de assertions disponíveis.
        
        Returns:
            list: Lista de categorias
        """
        return list(CypressAssertions.get_all_assertions().keys())
    
    @staticmethod
    def get_assertions_by_category(category):
        """
        Retorna as assertions de uma categoria específica.
        
        Args:
            category (str): Nome da categoria
            
        Returns:
            dict: Dicionário com assertions da categoria
        """
        all_assertions = CypressAssertions.get_all_assertions()
        return all_assertions.get(category, {})
    
    @staticmethod
    def get_assertion_info(category, assertion_name):
        """
        Retorna informações sobre uma assertion específica.
        
        Args:
            category (str): Nome da categoria
            assertion_name (str): Nome da assertion
            
        Returns:
            dict: Informações da assertion (description, syntax, example)
        """
        category_assertions = CypressAssertions.get_assertions_by_category(category)
        return category_assertions.get(assertion_name, {})
    
    @staticmethod
    def search_assertions(query):
        """
        Busca assertions que correspondam à consulta.
        
        Args:
            query (str): Texto de busca
            
        Returns:
            list: Lista de tuplas (categoria, nome_assertion, info_assertion)
        """
        query = query.lower()
        results = []
        
        all_assertions = CypressAssertions.get_all_assertions()
        for category, assertions in all_assertions.items():
            for assertion_name, assertion_info in assertions.items():
                # Buscar no nome da assertion
                if query in assertion_name.lower():
                    results.append((category, assertion_name, assertion_info))
                    continue
                
                # Buscar na descrição
                if query in assertion_info.get("description", "").lower():
                    results.append((category, assertion_name, assertion_info))
                    continue
                
                # Buscar no exemplo
                if query in assertion_info.get("example", "").lower():
                    results.append((category, assertion_name, assertion_info))
                    continue
        
        return results
