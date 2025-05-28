describe('Fluxo Orçamento Vigente', () => {
  beforeEach(() => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.wait(1000);  // Wait for initial page load
  });

  it('should execute the Fluxo Orçamento Vigente flow', () => {
    // Recorded user actions
    cy.get('.block').click();
    cy.wait(500);
    cy.get('.column').click();
    cy.wait(500);
    cy.get('span').click();
    cy.wait(500);
    cy.get('.items-center').click();
    cy.wait(500);
    cy.get('.q-item__label').click();
    cy.wait(500);
    cy.get('.material-icons').click();
    cy.wait(500);
    cy.get('#f_a77808d0-1eed-40b7-b47b-bf511114b789').type('q');
    // Verify successful navigation
    cy.url().should('include', '/success', { timeout: 10000 }); // Ensure URL check waits up to 10s
  });
});
