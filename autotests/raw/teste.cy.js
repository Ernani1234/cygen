describe('teste', () => {
  const defaultTimeout = 5000; // Timeout configurável

  beforeEach(() => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.get('body', { timeout: defaultTimeout }).should('be.visible'); // Espera que a página carregue
  });

  it('should execute the teste flow', () => {
    // Ações do usuário capturadas e otimizadas
    cy.get("[role="img"]", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get(".notranslate.material-icons.q-icon.text-primary", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get(".q-focus-helper", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    cy.get("[role="button"]", { timeout: 5000 }).should('be.visible').click();
    cy.get('body').should('exist'); // Espera condicional após clique
    
    // Verificação de navegação bem-sucedida
    cy.url().should('include', '/success', { timeout: defaultTimeout });
  });
});
