describe('login', () => {
  const defaultTimeout = 5000; // Timeout configurável

  beforeEach(() => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.get('body', { timeout: defaultTimeout }).should('be.visible'); // Espera que a página carregue
  });

  it('should execute the login flow', () => {
    // Ações do usuário capturadas e otimizadas
    cy.get("[role="button"]", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    
    // Verificação de navegação bem-sucedida
    cy.url().should('include', '/success', { timeout: defaultTimeout });
  });
});
