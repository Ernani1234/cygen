/// <reference types="cypress" />

describe('capture', () => {
  it('should complete the test flow successfully', () => {
    cy.visit('https://qa.sgpm.inovvati.com.br/#/auth/login');

    cy.contains('SGPM - Sistema de Gestão de Projetos de Modernização').should('be.visible').click();

    cy.get('[data-cy="login_id"]').should('be.visible').clear().type('d');

    cy.get('[data-cy="password_id"]').should('be.visible').clear().type('P@sg1425');

    cy.visit('https://qa.sgpm.inovvati.com.br/#/config/programa-financiamento-selecionar');

    cy.contains('arrow_drop_down').should('be.visible').click();

    cy.contains('PROFISCO II-MS').should('be.visible').click();

    cy.visit('https://qa.sgpm.inovvati.com.br/#/');

    cy.contains('IR').should('be.visible').click();
  });
});



