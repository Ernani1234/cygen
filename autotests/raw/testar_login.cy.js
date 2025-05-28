describe('Testar Login', () => {
  beforeEach(() => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.wait(1000);  // Wait for initial page load
  });

  it('should execute the Testar Login flow', () => {
    // Recorded user actions
    cy.get('.col').click();
    cy.wait(500);
    // Verify successful navigation
    cy.url().should('include', '/success', { timeout: 10000 }); // Ensure URL check waits up to 10s
  });
});
