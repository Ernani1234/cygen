/// <reference types="cypress" />

describe('SGPMMS - Login', () => {
  it('Login no sistema', () => {
    cy.visit('https://qa.sgpm.inovvati.com.br/#/auth/login');

    cy.get('span').should('be.visible').click();

    cy.get('span').should('be.visible').click();

    cy.get('[data-cy="login_id"]').should('be.visible').click();
    cy.get('[data-cy="login_id"]').should('be.visible').clear().type('dev');

    cy.get('[data-cy="password_id"]').should('be.visible').click();
    cy.get('[data-cy="password_id"]').should('be.visible').clear().type('P@sg142536');

    cy.visit('https://qa.sgpm.inovvati.com.br/#/config/programa-financiamento-selecionar');

    cy.get('[data-cy="programa_financiamento_id"]').should('be.visible').click();
    cy.contains('PROFISCO II-MS').should('be.visible').click();

    cy.visit('https://qa.sgpm.inovvati.com.br/#/');

    cy.contains('IR').should('be.visible').click();

  });
});

