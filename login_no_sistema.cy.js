
describe('login no sistema', () => {
  it('Deve executar o fluxo login no sistema', () => {
    cy.visit('https://qa.sgpm.inovvati.com.br');
    cy.get('span').click();cy.get('span').click();cy.get('#f_d94cf370-8ca5-46c8-a5b6-94aa66b08bb8').click();cy.get('#f_d94cf370-8ca5-46c8-a5b6-94aa66b08bb8').type('d');cy.get('#f_d94cf370-8ca5-46c8-a5b6-94aa66b08bb8').type('de');cy.get('#f_d94cf370-8ca5-46c8-a5b6-94aa66b08bb8').type('dev');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').click();cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@s');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg1');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg14');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg142');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg1425');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg14253');cy.get('#f_77785306-b074-4f72-baad-018c2393cf1c').type('P@sg142536');cy.get('.q-btn__content.text-center.col.items-center.q-anchor--skip.justify-center.row').click();cy.get('.notranslate.material-icons.q-icon.q-select__dropdown-icon.rotate-180').click();cy.get('.q-item__label').click();cy.get('.block').click();
    cy.url().should('include', '/success');
  }));
});
