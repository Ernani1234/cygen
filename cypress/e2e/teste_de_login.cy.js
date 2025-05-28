describe('Teste de Login', () => {
  const defaultTimeout = 5000; // Timeout configurável

  beforeEach(() => {
    cy.visit('http://qa.sgpm.inovvati.com.br');
    cy.get('body', { timeout: defaultTimeout }).should('be.visible'); // Espera que a página carregue
  });

  it('should execute the Teste de Login flow', () => {
    // Ações do usuário capturadas e otimizadas
    cy.get(".q-focus-helper", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get(".q-focus-helper", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get(".q-field__bottom.row.items-start.q-field__bottom--animated", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get(".block", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    
    // Verificação de navegação bem-sucedida
    cy.url().should('include', '/success', { timeout: defaultTimeout });
  });
});
