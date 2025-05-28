describe('Login SGPM', () => {
  beforeEach(() => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.wait(1000);  // Espera inicial para carregamento da página
  });

  it('should execute the Login SGPM flow', () => {
    // Ações do usuário capturadas e otimizadas
    cy.get('span').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('span').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('#f_8b88628f-0de5-4e82-9d29-f3204ac588a0[aria-label="Data"]').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('#f_8b88628f-0de5-4e82-9d29-f3204ac588a0[aria-label="Data"]').should('be.visible').type('dev');
    cy.get('#f_637d618b-ce15-4092-906a-43cecf20a95f[aria-controls="f_637d618b-ce15-4092-906a-43cecf20a95f_lb"]').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('#f_637d618b-ce15-4092-906a-43cecf20a95f[aria-controls="f_637d618b-ce15-4092-906a-43cecf20a95f_lb"]').should('be.visible').type('P@sg142536');
    cy.get('span:contains("menu")').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('span:contains("Novo")').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('div:contains("Cadastros")').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get('span:contains("Programa Financiamento")').should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    
    // Verificação de navegação bem-sucedida
    cy.url().should('include', '/success', { timeout: 5000 });
  });
});
