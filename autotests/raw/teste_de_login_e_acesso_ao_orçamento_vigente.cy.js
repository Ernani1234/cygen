describe('Teste de Login e acesso ao orçamento vigente', () => {
  beforeEach(() => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.wait(1000);  // Wait for initial page load
  });

  it('should execute the Teste de Login e acesso ao orçamento vigente flow', () => {
    // Recorded user actions
    
cy.get('.q-focus-helper').click();    cy.wait(500);    cy.get('.column').click();    cy.wait(500);    cy.get('.block').click();    cy.wait(500);    cy.get('.column').click();    cy.wait(500);    cy.get('span').click();    cy.wait(500);    cy.get('.block').click();    cy.wait(500);    cy.get('.q-page-container').click();    cy.wait(500);    cy.get('#f_a723f360-a043-4a89-9c9a-829f5911e00e').type('0,00');    cy.get('#f_45d4adc7-d199-411d-a9c5-e4115debee58').type('0,00');    cy.get('#f_3bc37eb7-2782-402f-a959-95082ca9003b').type('0,00');    cy.get('#f_a723f360-a043-4a89-9c9a-829f5911e00e').type('0,00');    cy.get('#f_45d4adc7-d199-411d-a9c5-e4115debee58').type('0,00');    cy.get('#f_3bc37eb7-2782-402f-a959-95082ca9003b').type('0,00');    cy.get('#f_a723f360-a043-4a89-9c9a-829f5911e00e').type('0,00');    cy.get('#f_45d4adc7-d199-411d-a9c5-e4115debee58').type('0,00');    cy.get('#f_3bc37eb7-2782-402f-a959-95082ca9003b').type('0,00');    cy.get('#f_a723f360-a043-4a89-9c9a-829f5911e00e').type('0,00');    cy.get('#f_45d4adc7-d199-411d-a9c5-e4115debee58').type('0,00');    cy.get('#f_3bc37eb7-2782-402f-a959-95082ca9003b').type('0,00');    cy.get('b').click();    cy.wait(500);    cy.get('.q-pa-lg').click();    cy.wait(500);
    // Verify successful navigation
    cy.url().should('include', '/success', { timeout: 10000 }); // Ensure URL check waits up to 10s
  });
});
