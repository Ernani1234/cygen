# Corrigido: populate_elements_tree agora exibe todos os tipos de ação (clique, input, select, navegação, rede)
# Corrigido: get_selected_elements agora recupera dados completos da ação
# Adicionado: Interface para escolha de seletores alternativos para cada elemento
# Melhorado: Etapa 3 (Assertions) com lista completa, categorizada e com tooltips

"""
Módulo para geração de testes Cypress a partir de elementos capturados.
Implementa interface visual para configuração e geração de testes.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import json
import os
import threading
import queue
import time
import re
from tkinter import filedialog, messagebox

# Importar módulos auxiliares
from modules.selector_chooser import SelectorChooserDialog
from modules.cypress_assertions import CypressAssertions
from modules.tooltip import ToolTip # Módulo para tooltips

class TestGenerator:
    """
    Módulo para geração de testes Cypress a partir de elementos capturados.
    """
    
    def __init__(self, parent, app):
        """
        Inicializa o gerador de testes.
        
        Args:
            parent: Frame pai onde o módulo será exibido
            app: Referência à aplicação principal
        """
        self.parent = parent
        self.app = app
        self.config = app.config
        
        # Variáveis de estado
        self.current_step = 0
        self.captured_data = None
        self.test_config = {
            "name": "",
            "description": "",
            "template": "default",
            "selected_elements": [], # Armazenará os dados completos das ações selecionadas
            "assertions": [],
            "commands": [],
            "fixtures": []
        }
        self.generated_code = None
        
        # Dicionário para armazenar seletores personalizados escolhidos pelo usuário
        self.custom_selectors = {}  # Formato: {item_id: selector_data}
        
        # Fila para comunicação thread-safe
        self.generator_queue = queue.Queue()
        
        # Carregar assertions
        self.all_assertions = CypressAssertions.get_all_assertions()
        
        # Criar componentes da interface
        self.create_widgets()
    
    def create_widgets(self):
        """Cria os widgets da interface do gerador de testes"""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=tk.BOTH, expand=True)  # Garantir que o frame seja empacotado
        
        # Título
        ttk.Label(
            self.frame, 
            text="Gerador de Testes Cypress", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Frame principal
        self.main_frame = ttk.Frame(self.frame, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Criar frames para cada etapa
        self.step_frames = []
        for i in range(5):  # 5 etapas no total
            step_frame = ttk.Frame(self.main_frame)
            self.step_frames.append(step_frame)
        
        # Configurar etapas
        self.setup_step_1()  # Configuração inicial
        self.setup_step_2()  # Seleção de elementos
        self.setup_step_3()  # Configuração de assertions
        self.setup_step_4()  # Visualização do código
        self.setup_step_5()  # Finalização
        
        # Barra de navegação de etapas
        self.steps_frame = ttk.Frame(self.frame, padding=10)
        self.steps_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=10)
        
        # Indicadores de etapa
        self.step_indicators = []
        steps_text = ["Configuração", "Elementos", "Assertions", "Código", "Finalizar"]
        
        indicators_frame = ttk.Frame(self.steps_frame)
        indicators_frame.pack(fill=tk.X, pady=10)
        
        for i, text in enumerate(steps_text):
            indicator_frame = ttk.Frame(indicators_frame)
            indicator_frame.pack(side=tk.LEFT, expand=True, fill=tk.X)
            
            # Círculo numerado
            circle = ttk.Label(
                indicator_frame, 
                text=str(i+1), 
                bootstyle="secondary",
                width=3,
                anchor=tk.CENTER
            )
            circle.pack(side=tk.TOP)
            
            # Texto da etapa
            label = ttk.Label(
                indicator_frame, 
                text=text, 
                bootstyle="secondary"
            )
            label.pack(side=tk.TOP)
            
            self.step_indicators.append((circle, label))
        
        # Separador
        ttk.Separator(self.steps_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # Botões de navegação
        self.nav_buttons_frame = ttk.Frame(self.steps_frame)
        self.nav_buttons_frame.pack(fill=tk.X)
        
        self.prev_button = ttk.Button(
            self.nav_buttons_frame,
            text="< Anterior",
            command=self.go_to_previous_step,
            state="disabled"
        )
        self.prev_button.pack(side=tk.LEFT)
        
        self.next_button = ttk.Button(
            self.nav_buttons_frame,
            text="Próximo >",
            bootstyle="primary",
            command=self.go_to_next_step
        )
        self.next_button.pack(side=tk.RIGHT)
        
        # Barra de progresso
        self.progress_frame = ttk.Frame(self.steps_frame)
        self.progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            value=0,
            maximum=4  # 5 etapas (0 a 4)
        )
        self.progress_bar.pack(fill=tk.X)
        
        # Mostrar primeira etapa
        self.show_step(0)

    
    def setup_step_1(self):
        """Configura a primeira etapa: Configuração inicial"""
        frame = self.step_frames[0]
        
        # Título da etapa
        ttk.Label(
            frame, 
            text="Configuração do Teste", 
            font=("Helvetica", 16, "bold")
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Nome do teste
        name_frame = ttk.Frame(frame)
        name_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            name_frame, 
            text="Nome do Teste:", 
            width=20
        ).pack(side=tk.LEFT)
        
        self.test_name_var = tk.StringVar()
        test_name_entry = ttk.Entry(
            name_frame, 
            textvariable=self.test_name_var,
            width=40
        )
        test_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Descrição do teste
        desc_frame = ttk.Frame(frame)
        desc_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            desc_frame, 
            text="Descrição:", 
            width=20
        ).pack(side=tk.LEFT, anchor=tk.N)
        
        self.test_desc_text = tk.Text(
            desc_frame, 
            height=4, 
            width=40,
            wrap=tk.WORD
        )
        self.test_desc_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Template do teste
        template_frame = ttk.Frame(frame)
        template_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            template_frame, 
            text="Template:", 
            width=20
        ).pack(side=tk.LEFT)
        
        self.template_var = tk.StringVar(value="default")
        templates = ["default", "page-object", "component", "api-test"]
        template_combo = ttk.Combobox(
            template_frame, 
            textvariable=self.template_var,
            values=templates,
            state="readonly",
            width=20
        )
        template_combo.pack(side=tk.LEFT)
        
        # Opções avançadas
        options_frame = ttk.LabelFrame(frame, text="Opções Avançadas", padding=10)
        options_frame.pack(fill=tk.X, pady=20)
        
        # Usar TypeScript
        self.use_ts_var = tk.BooleanVar(value=self.config.get("use_typescript", False))
        ttk.Checkbutton(
            options_frame, 
            text="Usar TypeScript", 
            variable=self.use_ts_var
        ).pack(anchor=tk.W, pady=5)
        
        # Auto-importar helpers
        self.auto_import_var = tk.BooleanVar(value=self.config.get("auto_import_helpers", True))
        ttk.Checkbutton(
            options_frame, 
            text="Auto-importar helpers", 
            variable=self.auto_import_var
        ).pack(anchor=tk.W, pady=5)
        
        # Auto-gerar fixtures
        self.auto_fixtures_var = tk.BooleanVar(value=self.config.get("auto_generate_fixtures", True))
        ttk.Checkbutton(
            options_frame, 
            text="Auto-gerar fixtures", 
            variable=self.auto_fixtures_var
        ).pack(anchor=tk.W, pady=5)
        
        # Carregar dados
        load_frame = ttk.Frame(frame)
        load_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(
            load_frame,
            text="Carregar Dados de Captura",
            command=self.load_capture_data
        ).pack(side=tk.LEFT, padx=5)
        
        self.data_status_label = ttk.Label(
            load_frame,
            text="Nenhum dado carregado",
            bootstyle="secondary"
        )
        self.data_status_label.pack(side=tk.LEFT, padx=10)
    
    def setup_step_2(self):
        """Configura a segunda etapa: Seleção de elementos"""
        frame = self.step_frames[1]
        
        # Título da etapa
        ttk.Label(
            frame, 
            text="Seleção de Elementos e Ações", 
            font=("Helvetica", 16, "bold")
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Instruções
        ttk.Label(
            frame, 
            text="Selecione as ações e elementos que deseja incluir no teste. Dê duplo clique para marcar/desmarcar.",
            wraplength=600
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Árvore de elementos
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Configurar árvore
        columns = ("Selecionado", "Tipo", "Descrição", "Seletor Principal", "Tempo")
        self.elements_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=15
        )
        
        # Configurar colunas
        self.elements_tree.heading("Selecionado", text="")
        self.elements_tree.heading("Tipo", text="Tipo")
        self.elements_tree.heading("Descrição", text="Descrição")
        self.elements_tree.heading("Seletor Principal", text="Seletor Principal")
        self.elements_tree.heading("Tempo", text="Tempo")
        
        self.elements_tree.column("Selecionado", width=30, stretch=False, anchor=tk.CENTER)
        self.elements_tree.column("Tipo", width=100, stretch=False)
        self.elements_tree.column("Descrição", width=250)
        self.elements_tree.column("Seletor Principal", width=250)
        self.elements_tree.column("Tempo", width=80, stretch=False, anchor=tk.E)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(
            tree_frame, 
            orient="vertical", 
            command=self.elements_tree.yview
        )
        self.elements_tree.configure(yscrollcommand=scrollbar.set)
        
        self.elements_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular eventos
        self.elements_tree.bind("<Double-1>", self.toggle_element_selection)
        self.elements_tree.bind("<Button-3>", self.show_selector_menu)  # Clique direito para menu de seletores
        
        # Botões de ação
        buttons_frame = ttk.Frame(frame)
        buttons_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            buttons_frame,
            text="Selecionar Todos",
            command=self.select_all_elements
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame,
            text="Desmarcar Todos",
            command=self.deselect_all_elements
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame,
            text="Inverter Seleção",
            command=self.invert_element_selection
        ).pack(side=tk.LEFT, padx=5)
        
        # Botão para escolher seletor
        self.choose_selector_button = ttk.Button(
            buttons_frame,
            text="Escolher Seletor",
            command=self.choose_selector_for_selected,
            bootstyle="info"
        )
        self.choose_selector_button.pack(side=tk.RIGHT, padx=5)
        
        # Filtros (opcional, pode ser removido se a árvore for clara o suficiente)
        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(filter_frame, text="Filtrar:").pack(side=tk.LEFT)
        
        self.filter_var = tk.StringVar(value="Todos")
        filter_combo = ttk.Combobox(
            filter_frame, 
            textvariable=self.filter_var,
            values=["Todos", "Navegação", "Cliques", "Inputs", "Selects", "API", "Outros"],
            state="readonly",
            width=15
        )
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind("<<ComboboxSelected>>", self.filter_elements)
    
    def setup_step_3(self):
        """Configura a terceira etapa: Configuração de assertions (com categorias e tooltips)"""
        frame = self.step_frames[2]
        
        # Título da etapa
        ttk.Label(
            frame, 
            text="Configuração de Assertions", 
            font=("Helvetica", 16, "bold")
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Instruções
        ttk.Label(
            frame, 
            text="Selecione uma ação e adicione assertions para verificar o estado esperado:",
            wraplength=600
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Painel dividido
        paned = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Painel de elementos selecionados
        selected_frame = ttk.LabelFrame(paned, text="Ações Selecionadas", padding=10)
        paned.add(selected_frame, weight=1)
        
        # Lista de elementos selecionados
        self.selected_elements_list = tk.Listbox(
            selected_frame,
            height=15,
            width=40,
            exportselection=False
        )
        selected_scrollbar = ttk.Scrollbar(
            selected_frame, 
            orient="vertical", 
            command=self.selected_elements_list.yview
        )
        self.selected_elements_list.configure(yscrollcommand=selected_scrollbar.set)
        
        self.selected_elements_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        selected_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular evento de seleção
        self.selected_elements_list.bind("<<ListboxSelect>>", self.on_element_select)
        
        # Painel de configuração de assertions
        assertions_config_frame = ttk.LabelFrame(paned, text="Configuração de Assertions", padding=10)
        paned.add(assertions_config_frame, weight=2)
        
        # Elemento atual
        current_element_frame = ttk.Frame(assertions_config_frame)
        current_element_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(
            current_element_frame, 
            text="Ação:"
        ).pack(side=tk.LEFT)
        
        self.current_element_label = ttk.Label(
            current_element_frame, 
            text="Nenhuma ação selecionada",
            bootstyle="info"
        )
        self.current_element_label.pack(side=tk.LEFT, padx=5)
        
        # Seleção de Assertions (usando Treeview para categorias)
        assertion_selection_frame = ttk.Frame(assertions_config_frame)
        assertion_selection_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(
            assertion_selection_frame, 
            text="Escolha a Assertion:"
        ).pack(anchor=tk.W, pady=(0, 5))
        
        # Árvore de Assertions
        assertion_tree_frame = ttk.Frame(assertion_selection_frame)
        assertion_tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.assertion_tree = ttk.Treeview(
            assertion_tree_frame,
            columns=("Descrição",),
            show="tree headings",
            selectmode="browse",
            height=10
        )
        
        self.assertion_tree.heading("#0", text="Assertion")
        self.assertion_tree.heading("Descrição", text="Descrição")
        
        self.assertion_tree.column("#0", width=200)
        self.assertion_tree.column("Descrição", width=300)
        
        # Scrollbar
        assertion_scrollbar = ttk.Scrollbar(
            assertion_tree_frame, 
            orient="vertical", 
            command=self.assertion_tree.yview
        )
        self.assertion_tree.configure(yscrollcommand=assertion_scrollbar.set)
        
        self.assertion_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        assertion_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Preencher árvore de assertions
        self.populate_assertion_tree()
        
        # Vincular eventos
        self.assertion_tree.bind("<<TreeviewSelect>>", self.on_assertion_tree_select)
        self.assertion_tree.bind("<Motion>", self.show_assertion_tooltip) # Para tooltip
        
        # Frame para tooltip (será posicionado dinamicamente)
        self.tooltip_frame = ttk.Frame(self.frame, borderwidth=1, relief="solid", padding=5)
        self.tooltip_label = ttk.Label(self.tooltip_frame, text="", wraplength=300)
        self.tooltip_label.pack()
        self.tooltip_frame.place_forget() # Inicialmente oculto
        self._tooltip_after_id = None
        
        # Valor da assertion (para tipos que precisam de valor)
        self.assertion_value_frame = ttk.Frame(assertions_config_frame)
        self.assertion_value_frame.pack(fill=tk.X, pady=10)
        
        self.assertion_value_label = ttk.Label(
            self.assertion_value_frame, 
            text="Valor:"
        )
        self.assertion_value_label.pack(side=tk.LEFT)
        
        self.assertion_value_var = tk.StringVar()
        self.assertion_value_entry = ttk.Entry(
            self.assertion_value_frame, 
            textvariable=self.assertion_value_var,
            width=30
        )
        self.assertion_value_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Inicialmente oculto
        self.assertion_value_frame.pack_forget()
        
        # Botões de ação para assertions
        assertion_buttons_frame = ttk.Frame(assertions_config_frame)
        assertion_buttons_frame.pack(fill=tk.X, pady=10)
        
        self.add_assertion_button = ttk.Button(
            assertion_buttons_frame,
            text="Adicionar Assertion",
            command=self.add_assertion,
            state="disabled"
        )
        self.add_assertion_button.pack(side=tk.LEFT, padx=5)
        
        self.remove_assertion_button = ttk.Button(
            assertion_buttons_frame,
            text="Remover Assertion",
            command=self.remove_assertion,
            state="disabled"
        )
        self.remove_assertion_button.pack(side=tk.LEFT, padx=5)
        
        # Lista de assertions configuradas
        assertions_list_frame = ttk.LabelFrame(assertions_config_frame, text="Assertions Configuradas", padding=10)
        assertions_list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.assertions_list = tk.Listbox(
            assertions_list_frame,
            height=5,
            width=50
        )
        assertions_scrollbar = ttk.Scrollbar(
            assertions_list_frame, 
            orient="vertical", 
            command=self.assertions_list.yview
        )
        self.assertions_list.configure(yscrollcommand=assertions_scrollbar.set)
        
        self.assertions_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        assertions_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular evento de seleção
        self.assertions_list.bind("<<ListboxSelect>>", self.on_assertion_select)
    
    def setup_step_4(self):
        """Configura a quarta etapa: Visualização do código"""
        frame = self.step_frames[3]
        
        # Título da etapa
        ttk.Label(
            frame, 
            text="Visualização do Código", 
            font=("Helvetica", 16, "bold")
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Instruções
        ttk.Label(
            frame, 
            text="Revise o código gerado e faça ajustes se necessário:",
            wraplength=600
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Botões de ação
        buttons_frame = ttk.Frame(frame)
        buttons_frame.pack(fill=tk.X, pady=10)
        
        self.generate_button = ttk.Button(
            buttons_frame,
            text="Gerar Código",
            bootstyle="success",
            command=self.generate_code
        )
        self.generate_button.pack(side=tk.LEFT, padx=5)
        
        self.regenerate_button = ttk.Button(
            buttons_frame,
            text="Regenerar Código",
            bootstyle="warning",
            command=self.regenerate_code,
            state="disabled"
        )
        self.regenerate_button.pack(side=tk.LEFT, padx=5)
        
        # Editor de código
        code_frame = ttk.Frame(frame)
        code_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.code_text = tk.Text(
            code_frame, 
            wrap=tk.NONE,
            font=("Consolas", 12),
            bg="#282a36",
            fg="#f8f8f2",
            insertbackground="#f8f8f2"
        )
        
        # Scrollbars
        code_y_scrollbar = ttk.Scrollbar(
            code_frame, 
            orient="vertical", 
            command=self.code_text.yview
        )
        code_x_scrollbar = ttk.Scrollbar(
            code_frame, 
            orient="horizontal", 
            command=self.code_text.xview
        )
        
        self.code_text.configure(
            yscrollcommand=code_y_scrollbar.set,
            xscrollcommand=code_x_scrollbar.set
        )
        
        code_y_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        code_x_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.code_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configurar syntax highlighting
        self.setup_syntax_highlighting()
        
        # Status da geração
        self.code_status_frame = ttk.Frame(frame)
        self.code_status_frame.pack(fill=tk.X, pady=10)
        
        self.code_status_label = ttk.Label(
            self.code_status_frame,
            text="Clique em 'Gerar Código' para iniciar a geração",
            bootstyle="secondary"
        )
        self.code_status_label.pack(side=tk.LEFT)
        
        # Estimativa de tokens/custo
        self.tokens_label = ttk.Label(
            self.code_status_frame,
            text="",
            bootstyle="info"
        )
        self.tokens_label.pack(side=tk.RIGHT)
    
    def setup_step_5(self):
        """Configura a quinta etapa: Finalização"""
        frame = self.step_frames[4]
        
        # Título da etapa
        ttk.Label(
            frame, 
            text="Finalizar Geração", 
            font=("Helvetica", 16, "bold")
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Instruções
        ttk.Label(
            frame, 
            text="Seu teste Cypress foi gerado com sucesso! Escolha o que fazer com ele:",
            wraplength=600
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Opções de finalização
        options_frame = ttk.Frame(frame)
        options_frame.pack(fill=tk.BOTH, expand=True, pady=20)
        
        # Salvar como arquivo
        save_button = ttk.Button(
            options_frame,
            text="Salvar como Arquivo",
            bootstyle="success",
            command=self.save_test_file,
            width=30
        )
        save_button.pack(pady=10)
        
        # Copiar para área de transferência
        copy_button = ttk.Button(
            options_frame,
            text="Copiar para Área de Transferência",
            bootstyle="info",
            command=self.copy_to_clipboard,
            width=30
        )
        copy_button.pack(pady=10)
        
        # Editar com IA
        edit_button = ttk.Button(
            options_frame,
            text="Editar com Assistente IA",
            bootstyle="primary",
            command=self.edit_with_ai,
            width=30
        )
        edit_button.pack(pady=10)
        
        # Iniciar novo teste
        new_button = ttk.Button(
            options_frame,
            text="Iniciar Novo Teste",
            bootstyle="secondary",
            command=self.start_new_test,
            width=30
        )
        new_button.pack(pady=10)
        
        # Resumo do teste
        summary_frame = ttk.LabelFrame(frame, text="Resumo do Teste", padding=10)
        summary_frame.pack(fill=tk.X, pady=20)
        
        self.summary_text = tk.Text(
            summary_frame, 
            height=8, 
            width=60, 
            wrap=tk.WORD,
            bg="#282a36",
            fg="#f8f8f2",
            state=tk.DISABLED
        )
        summary_scrollbar = ttk.Scrollbar(
            summary_frame, 
            orient="vertical", 
            command=self.summary_text.yview
        )
        self.summary_text.configure(yscrollcommand=summary_scrollbar.set)
        
        self.summary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        summary_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def setup_syntax_highlighting(self):
        """Configura syntax highlighting para o editor de código"""
        # Configurar tags para syntax highlighting
        self.code_text.tag_configure("keyword", foreground="#ff79c6")
        self.code_text.tag_configure("string", foreground="#f1fa8c")
        self.code_text.tag_configure("comment", foreground="#6272a4")
        self.code_text.tag_configure("function", foreground="#50fa7b")
        self.code_text.tag_configure("variable", foreground="#8be9fd")
        self.code_text.tag_configure("number", foreground="#bd93f9")
        self.code_text.tag_configure("operator", foreground="#ff79c6")
    
    def apply_syntax_highlighting(self):
        """Aplica syntax highlighting ao código"""
        if not self.generated_code:
            return
        
        # Limpar tags existentes
        for tag in ["keyword", "string", "comment", "function", "variable", "number", "operator"]:
            self.code_text.tag_remove(tag, "1.0", tk.END)
        
        # Palavras-chave do JavaScript/Cypress
        keywords = [
            "const", "let", "var", "function", "return", "if", "else", "for", "while", 
            "do", "switch", "case", "break", "continue", "try", "catch", "finally",
            "import", "export", "from", "class", "extends", "new", "this", "super",
            "describe", "it", "beforeEach", "afterEach", "before", "after", "context"
        ]
        
        # Funções do Cypress
        cypress_functions = [
            "cy.visit", "cy.get", "cy.contains", "cy.wait", "cy.intercept", "cy.request",
            "cy.url", "cy.location", "cy.title", "cy.window", "cy.document", "cy.fixture",
            "cy.route", "cy.server", "cy.stub", "cy.spy", "cy.clock", "cy.tick",
            "should", "and", "then", "click", "type", "select", "check", "uncheck",
            "clear", "submit", "trigger", "focus", "blur", "wrap"
        ]
        
        # Aplicar highlighting para palavras-chave
        for keyword in keywords:
            start_index = "1.0"
            while True:
                start_index = self.code_text.search(r'\y' + keyword + r'\y', start_index, tk.END, regexp=True)
                if not start_index:
                    break
                end_index = f"{start_index}+{len(keyword)}c"
                self.code_text.tag_add("keyword", start_index, end_index)
                start_index = end_index
        
        # Aplicar highlighting para funções do Cypress
        for func in cypress_functions:
            start_index = "1.0"
            while True:
                start_index = self.code_text.search(func, start_index, tk.END)
                if not start_index:
                    break
                end_index = f"{start_index}+{len(func)}c"
                self.code_text.tag_add("function", start_index, end_index)
                start_index = end_index
        
        # Aplicar highlighting para strings
        start_index = "1.0"
        while True:
            start_index = self.code_text.search(r'["\'].*?["\']', start_index, tk.END, regexp=True)
            if not start_index:
                break
            content = self.code_text.get(start_index, tk.END)
            quote = content[0]
            end_pos = 1
            escaped = False
            
            # Encontrar o final da string
            while end_pos < len(content):
                if content[end_pos] == '\\':
                    escaped = not escaped
                elif content[end_pos] == quote and not escaped:
                    break
                else:
                    escaped = False
                end_pos += 1
            
            if end_pos < len(content):
                end_index = f"{start_index}+{end_pos + 1}c"
                self.code_text.tag_add("string", start_index, end_index)
                start_index = end_index
            else:
                break
        
        # Aplicar highlighting para comentários
        start_index = "1.0"
        while True:
            start_index = self.code_text.search(r'//.*$', start_index, tk.END, regexp=True)
            if not start_index:
                break
            line = int(float(start_index))
            end_index = f"{line + 1}.0"
            self.code_text.tag_add("comment", start_index, end_index)
            start_index = end_index
        
        # Comentários de múltiplas linhas
        start_index = "1.0"
        while True:
            start_index = self.code_text.search(r'/\*', start_index, tk.END)
            if not start_index:
                break
            end_index = self.code_text.search(r'\*/', start_index, tk.END)
            if not end_index:
                break
            end_index = f"{end_index}+2c"
            self.code_text.tag_add("comment", start_index, end_index)
            start_index = end_index
        
        # Aplicar highlighting para números
        start_index = "1.0"
        while True:
            start_index = self.code_text.search(r'\y\d+\y', start_index, tk.END, regexp=True)
            if not start_index:
                break
            content = self.code_text.get(start_index, tk.END)
            match = re.match(r'\d+', content)
            if match:
                end_index = f"{start_index}+{match.end()}c"
                self.code_text.tag_add("number", start_index, end_index)
                start_index = end_index
            else:
                break
    
    def show(self):
        """Exibe o módulo de geração de testes"""
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Verificar se há dados de captura disponíveis (opcional, pode ser carregado manualmente)
        # if self.app.current_log_path and os.path.exists(self.app.current_log_path):
        #     self.load_capture_data(self.app.current_log_path)
    
    def hide(self):
        """Oculta o módulo de geração de testes"""
        self.frame.pack_forget()
    
    def show_step(self, step_index):
        """
        Exibe a etapa especificada.
        
        Args:
            step_index: Índice da etapa a ser exibida (0 a 4)
        """
        # Ocultar todas as etapas
        for frame in self.step_frames:
            frame.pack_forget()
        
        # Exibir etapa selecionada
        self.step_frames[step_index].pack(fill=tk.BOTH, expand=True)
        
        # Atualizar indicadores de etapa
        for i, (circle, label) in enumerate(self.step_indicators):
            if i < step_index:
                # Etapa concluída
                circle.config(bootstyle="success")
                label.config(bootstyle="success")
            elif i == step_index:
                # Etapa atual
                circle.config(bootstyle="primary")
                label.config(bootstyle="primary")
            else:
                # Etapa futura
                circle.config(bootstyle="secondary")
                label.config(bootstyle="secondary")
        
        # Atualizar barra de progresso
        self.progress_bar.config(value=step_index)
        
        # Atualizar botões de navegação
        self.prev_button.config(state="normal" if step_index > 0 else "disabled")
        
        if step_index == 3:  # Etapa de visualização do código
            self.next_button.config(
                text="Finalizar",
                state="normal" if self.generated_code else "disabled"
            )
        elif step_index == 4:  # Etapa final
            self.next_button.config(
                text="Concluir",
                state="disabled"
            )
            self.update_summary()
        else:
            self.next_button.config(
                text="Próximo >",
                state="normal"
            )
        
        # Armazenar etapa atual
        self.current_step = step_index
    
    def go_to_next_step(self):
        """Avança para a próxima etapa"""
        # Validar etapa atual
        if not self.validate_current_step():
            return
        
        # Avançar para próxima etapa
        if self.current_step < 4:
            self.show_step(self.current_step + 1)
    
    def go_to_previous_step(self):
        """Retorna para a etapa anterior"""
        if self.current_step > 0:
            self.show_step(self.current_step - 1)
    
    def validate_current_step(self):
        """
        Valida a etapa atual antes de avançar.
        
        Returns:
            bool: True se a etapa é válida, False caso contrário
        """
        if self.current_step == 0:
            # Validar configuração inicial
            test_name = self.test_name_var.get().strip()
            if not test_name:
                messagebox.showwarning("Validação", "Por favor, informe um nome para o teste.")
                return False
            
            if not self.captured_data:
                messagebox.showwarning("Validação", "Por favor, carregue dados de captura antes de prosseguir.")
                return False
            
            # Atualizar configuração do teste
            self.test_config["name"] = test_name
            self.test_config["description"] = self.test_desc_text.get("1.0", tk.END).strip()
            self.test_config["template"] = self.template_var.get()
            
            # Preencher árvore de elementos
            self.populate_elements_tree()
            
        elif self.current_step == 1:
            # Validar seleção de elementos
            selected_elements = self.get_selected_elements()
            if not selected_elements:
                messagebox.showwarning("Validação", "Por favor, selecione pelo menos uma ação para o teste.")
                return False
            
            # Atualizar configuração do teste
            self.test_config["selected_elements"] = selected_elements
            
            # Preencher lista de elementos selecionados na próxima etapa
            self.populate_selected_elements_list()
            
        elif self.current_step == 2:
            # Validar assertions (opcional)
            pass
            
        elif self.current_step == 3:
            # Validar código gerado
            if not self.generated_code:
                messagebox.showwarning("Validação", "Por favor, gere o código do teste antes de prosseguir.")
                return False
        
        return True
    
    def load_capture_data(self, filepath=None):
        """
        Carrega dados de captura de um arquivo.
        
        Args:
            filepath: Caminho do arquivo de captura (opcional)
        """
        if not filepath:
            # Solicitar arquivo
            logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            filepath = filedialog.askopenfilename(
                title="Selecionar Arquivo de Captura",
                filetypes=[("Arquivos JSON", "*.json"), ("Todos os Arquivos", "*.*")],
                initialdir=logs_dir if os.path.exists(logs_dir) else os.getcwd()
            )
            
            if not filepath:
                return
        
        try:
            # Carregar dados
            with open(filepath, 'r', encoding='utf-8') as f:
                self.captured_data = json.load(f)
            
            # Atualizar interface
            actions_count = len(self.captured_data.get("actions", []))
            network_count = len(self.captured_data.get("network_requests", []))
            
            self.data_status_label.config(
                text=f"Dados carregados: {actions_count} ações, {network_count} requisições",
                bootstyle="success"
            )
            
            # Sugerir nome do teste a partir do nome do arquivo
            if not self.test_name_var.get().strip():
                filename_base = os.path.basename(filepath)
                # Remover extensão e timestamp
                test_name_suggestion = re.sub(r'_\d{8}_\d{6}\.json$', '', filename_base)
                test_name_suggestion = re.sub(r'[^a-zA-Z0-9_\- ]', '_', test_name_suggestion).strip()
                if test_name_suggestion:
                    self.test_name_var.set(test_name_suggestion)
            
            self.app.update_status(f"Dados de captura carregados: {os.path.basename(filepath)}", "success")
            
            # Resetar etapas seguintes se dados forem carregados novamente
            self.reset_steps_after(0)
            
        except Exception as e:
            self.captured_data = None # Limpar dados em caso de erro
            self.data_status_label.config(
                text=f"Erro ao carregar dados: {str(e)}",
                bootstyle="danger"
            )
            self.app.update_status(f"Erro ao carregar dados: {str(e)}", "error")
            messagebox.showerror("Erro de Carregamento", f"Não foi possível carregar o arquivo JSON:\n{e}")
    
    def populate_elements_tree(self):
        """Preenche a árvore de elementos com os dados capturados (ações e rede)"""
        # Limpar árvore
        for item in self.elements_tree.get_children():
            self.elements_tree.delete(item)
        
        if not self.captured_data:
            print("[DEBUG] Nenhum dado capturado para popular a árvore.")
            return
        
        print(f"[DEBUG] Populando árvore com {len(self.captured_data.get('actions', []))} ações e {len(self.captured_data.get('network_requests', []))} requisições.")
        
        # Combinar ações e requisições de rede, mantendo a ordem original (baseado em timestamp)
        all_items = sorted(
            self.captured_data.get("actions", []) + self.captured_data.get("network_requests", []),
            key=lambda x: x.get("timestamp", 0)
        )

        for i, item_data in enumerate(all_items):
            item_type = item_data.get("type", "unknown")
            category = item_data.get("category", "Outros")
            time_str = item_data.get("time_str", "?")
            description = ""
            selector = "N/A"
            
            # Determinar tipo e descrição para exibição
            display_type = category # Usar categoria como tipo inicial
            
            if item_type == "navigation":
                display_type = "Navegação"
                description = item_data.get("url", "URL desconhecida")
                selector = "cy.visit() / cy.url()"
            elif item_type == "click":
                display_type = "Clique"
                element = item_data.get("element", {})
                text = element.get("text", "").strip()
                aria_label = element.get("aria-label", "")
                name = element.get("name", "")
                tag = element.get("tag", "")
                el_id = element.get("id", "")
                description = text if text else aria_label if aria_label else name if name else el_id if el_id else f"<{tag}>"
                selector = item_data.get("selector", "Sem seletor")
            elif item_type == "input":
                display_type = "Input"
                element = item_data.get("element", {})
                value = element.get("value", "")
                name = element.get("name", "")
                aria_label = element.get("aria-label", "")
                el_id = element.get("id", "")
                placeholder = element.get("placeholder", "")
                description_base = name if name else el_id if el_id else aria_label if aria_label else placeholder
                description = f"{description_base} = '{value[:30]}{'...' if len(value)>30 else ''}'"
                selector = item_data.get("selector", "Sem seletor")
            elif item_type == "select":
                display_type = "Select"
                element = item_data.get("element", {})
                value = element.get("value", "")
                selected_text = element.get("selected_text", "")
                name = element.get("name", "")
                aria_label = element.get("aria-label", "")
                el_id = element.get("id", "")
                description_base = name if name else el_id if el_id else aria_label
                option_text = selected_text if selected_text else value
                description = f"{description_base} = '{option_text}'"
                selector = item_data.get("selector", "Sem seletor")
            elif item_type == "network":
                display_type = "API"
                method = item_data.get("method", "?")
                status = item_data.get("status", "?")
                endpoint = self._get_endpoint_name(item_data.get("url", ""))
                description = f"{method} {endpoint} ({status})"
                selector = f"cy.intercept('{method}', '**/{endpoint}*')"
            else:
                # Outros tipos de ação (se houver)
                display_type = item_type.capitalize()
                description = f"Ação: {item_type}"
                selector = item_data.get("selector", "N/A")

            # Limitar tamanho da descrição
            description = description[:100] + ('...' if len(description) > 100 else '')
            
            # Adicionar à árvore
            # Usar o índice 'i' para garantir que a ordem seja mantida
            # Armazenar o índice original do item em all_items como tag
            item_id = self.elements_tree.insert(
                "",
                tk.END,
                values=(
                    "✓",  # Selecionado por padrão
                    display_type,
                    description,
                    selector,
                    time_str
                ),
                tags=(item_type, "selected", f"item_index_{i}") # Adiciona tag com índice original
            )
        print(f"[DEBUG] Árvore populada com {len(self.elements_tree.get_children())} itens.")
    
    def _is_important_request(self, url):
        """Verifica se a requisição é importante para ser exibida (simplificado)"""
        # Pode ser ajustado conforme necessidade
        return True # Por enquanto, mostra todas as requisições de rede capturadas
    
    def _get_endpoint_name(self, url):
        """Extrai o nome do endpoint da URL"""
        try:
            path = url.split("?")[0]  # Remover query string
            path = path.split("#")[0]  # Remover fragmento
            parts = path.rstrip("/").split("/")
            # Tenta pegar a última parte não numérica ou UUID
            for part in reversed(parts):
                if part and not part.isdigit() and len(part) < 30: # Evitar IDs longos
                    return part
            return parts[-1] if parts else "endpoint"
        except:
            return "endpoint"
    
    def toggle_element_selection(self, event=None):
        """Alterna a seleção de um elemento na árvore"""
        item_id = self.elements_tree.focus()
        if not item_id:
            return
        
        # Obter valores atuais
        values = list(self.elements_tree.item(item_id, "values"))
        tags = list(self.elements_tree.item(item_id, "tags"))
        
        # Alternar seleção
        if "selected" in tags:
            values[0] = ""  # Desmarcar
            tags.remove("selected")
        else:
            values[0] = "✓"  # Marcar
            tags.append("selected")
        
        # Atualizar item
        self.elements_tree.item(item_id, values=values, tags=tags)
    
    def show_selector_menu(self, event=None):
        """Exibe menu de contexto para escolha de seletor ao clicar com botão direito"""
        item_id = self.elements_tree.identify_row(event.y)
        if not item_id:
            return
        
        # Selecionar o item clicado
        self.elements_tree.selection_set(item_id)
        self.elements_tree.focus(item_id)
        
        # Criar menu de contexto
        context_menu = tk.Menu(self.elements_tree, tearoff=0)
        context_menu.add_command(label="Escolher Seletor", command=self.choose_selector_for_selected)
        context_menu.add_separator()
        
        # Adicionar opção para marcar/desmarcar
        tags = self.elements_tree.item(item_id, "tags")
        if "selected" in tags:
            context_menu.add_command(label="Desmarcar", command=lambda: self.toggle_element_selection())
        else:
            context_menu.add_command(label="Marcar", command=lambda: self.toggle_element_selection())
        
        # Exibir menu na posição do clique
        context_menu.tk_popup(event.x_root, event.y_root)
    
    def choose_selector_for_selected(self):
        """Abre diálogo para escolha de seletor para o elemento selecionado"""
        item_id = self.elements_tree.focus()
        if not item_id:
            messagebox.showinfo("Seleção", "Por favor, selecione um elemento primeiro.")
            return
        
        # Obter dados do elemento
        tags = self.elements_tree.item(item_id, "tags")
        item_index_tag = next((tag for tag in tags if tag.startswith("item_index_")), None)
        
        if not item_index_tag:
            messagebox.showerror("Erro", "Não foi possível identificar o elemento selecionado.")
            return
        
        try:
            item_index = int(item_index_tag.split("_")[-1])
            all_items = sorted(
                self.captured_data.get("actions", []) + self.captured_data.get("network_requests", []),
                key=lambda x: x.get("timestamp", 0)
            )
            
            if 0 <= item_index < len(all_items):
                element_data = all_items[item_index]
                
                # Abrir diálogo de escolha de seletor
                dialog = SelectorChooserDialog(self.frame, element_data)
                
                # Verificar resultado
                if dialog.result:
                    # Atualizar seletor na árvore
                    values = list(self.elements_tree.item(item_id, "values"))
                    values[3] = dialog.result["value"]  # Atualizar coluna de seletor
                    self.elements_tree.item(item_id, values=values)
                    
                    # Armazenar seletor personalizado
                    self.custom_selectors[item_id] = dialog.result
                    
                    # Mostrar confirmação
                    self.app.update_status(f"Seletor atualizado: {dialog.result['value']}", "success")
            else:
                messagebox.showerror("Erro", "Índice de elemento inválido.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao processar seletor: {str(e)}")
    
    def select_all_elements(self):
        """Seleciona todos os elementos na árvore"""
        for item_id in self.elements_tree.get_children():
            values = list(self.elements_tree.item(item_id, "values"))
            tags = list(self.elements_tree.item(item_id, "tags"))
            
            values[0] = "✓"  # Marcar
            if "selected" not in tags:
                tags.append("selected")
            
            self.elements_tree.item(item_id, values=values, tags=tags)
    
    def deselect_all_elements(self):
        """Desmarca todos os elementos na árvore"""
        for item_id in self.elements_tree.get_children():
            values = list(self.elements_tree.item(item_id, "values"))
            tags = list(self.elements_tree.item(item_id, "tags"))
            
            values[0] = ""  # Desmarcar
            if "selected" in tags:
                tags.remove("selected")
            
            self.elements_tree.item(item_id, values=values, tags=tags)
    
    def invert_element_selection(self):
        """Inverte a seleção de todos os elementos na árvore"""
        for item_id in self.elements_tree.get_children():
            values = list(self.elements_tree.item(item_id, "values"))
            tags = list(self.elements_tree.item(item_id, "tags"))
            
            if "selected" in tags:
                values[0] = ""  # Desmarcar
                tags.remove("selected")
            else:
                values[0] = "✓"  # Marcar
                tags.append("selected")
            
            self.elements_tree.item(item_id, values=values, tags=tags)
    
    def filter_elements(self, event=None):
        """Filtra os elementos exibidos na árvore"""
        filter_value = self.filter_var.get()
        
        # Restaurar todos os itens
        for detached_id in self.elements_tree.detached():
            self.elements_tree.reattach(detached_id, "", 0)
        
        # Aplicar filtro
        if filter_value != "Todos":
            for item_id in self.elements_tree.get_children():
                tags = self.elements_tree.item(item_id, "tags")
                values = self.elements_tree.item(item_id, "values")
                
                if filter_value == "Navegação" and "navigation" in tags:
                    continue
                elif filter_value == "Cliques" and "click" in tags:
                    continue
                elif filter_value == "Inputs" and "input" in tags:
                    continue
                elif filter_value == "Selects" and "select" in tags:
                    continue
                elif filter_value == "API" and "network" in tags:
                    continue
                elif filter_value == "Outros" and not any(tag in tags for tag in ["navigation", "click", "input", "select", "network"]):
                    continue
                else:
                    self.elements_tree.detach(item_id)
    
    def get_selected_elements(self):
        """
        Obtém os dados completos das ações selecionadas na árvore.
        
        Returns:
            list: Lista de dicionários, cada um representando uma ação selecionada.
        """
        selected_actions_data = []
        all_items = sorted(
            self.captured_data.get("actions", []) + self.captured_data.get("network_requests", []),
            key=lambda x: x.get("timestamp", 0)
        )

        for item_id in self.elements_tree.get_children():
            tags = self.elements_tree.item(item_id, "tags")
            
            if "selected" in tags:
                # Encontrar o índice original do item
                item_index_tag = next((tag for tag in tags if tag.startswith("item_index_")), None)
                if item_index_tag:
                    try:
                        item_index = int(item_index_tag.split("_")[-1])
                        if 0 <= item_index < len(all_items):
                            # Obter o dicionário completo da ação/requisição original
                            action_data = all_items[item_index].copy()
                            
                            # Verificar se há um seletor personalizado para este item
                            if item_id in self.custom_selectors:
                                # Atualizar o seletor na ação com o escolhido pelo usuário
                                custom_selector = self.custom_selectors[item_id]
                                action_data["custom_selector"] = custom_selector
                                
                                # Se for um elemento interativo, atualizar o seletor principal
                                if action_data.get("type") in ["click", "input", "select"]:
                                    action_data["selector"] = custom_selector["value"]
                            
                            selected_actions_data.append(action_data)
                        else:
                             print(f"[WARN] Índice inválido encontrado na tag: {item_index_tag}")
                    except ValueError:
                        print(f"[WARN] Tag de índice inválida: {item_index_tag}")
                else:
                    print(f"[WARN] Tag de índice não encontrada para o item selecionado: {item_id}")

        print(f"[DEBUG] {len(selected_actions_data)} ações selecionadas.")
        return selected_actions_data
    
    def populate_selected_elements_list(self):
        """Preenche a lista de elementos selecionados na Etapa 3 (Assertions)"""
        # Limpar lista
        self.selected_elements_list.delete(0, tk.END)
        
        # Adicionar ações selecionadas
        for i, action_data in enumerate(self.test_config["selected_elements"]):
            item_type = action_data.get("type", "unknown")
            description = ""
            
            # Gerar descrição similar à da árvore
            if item_type == "navigation":
                description = action_data.get("url", "URL desconhecida")
            elif item_type == "click":
                element = action_data.get("element", {})
                text = element.get("text", "").strip()
                aria_label = element.get("aria-label", "")
                name = element.get("name", "")
                tag = element.get("tag", "")
                el_id = element.get("id", "")
                description = text if text else aria_label if aria_label else name if name else el_id if el_id else f"<{tag}>"
            elif item_type == "input":
                element = action_data.get("element", {})
                value = element.get("value", "")
                name = element.get("name", "")
                aria_label = element.get("aria-label", "")
                el_id = element.get("id", "")
                placeholder = element.get("placeholder", "")
                description_base = name if name else el_id if el_id else aria_label if aria_label else placeholder
                description = f"{description_base} = '{value[:30]}{'...' if len(value)>30 else ''}'"
            elif item_type == "select":
                element = action_data.get("element", {})
                value = element.get("value", "")
                selected_text = element.get("selected_text", "")
                name = element.get("name", "")
                aria_label = element.get("aria-label", "")
                el_id = element.get("id", "")
                description_base = name if name else el_id if el_id else aria_label
                option_text = selected_text if selected_text else value
                description = f"{description_base} = '{option_text}'"
            elif item_type == "network":
                method = action_data.get("method", "?")
                status = action_data.get("status", "?")
                endpoint = self._get_endpoint_name(action_data.get("url", ""))
                description = f"{method} {endpoint} ({status})"
            else:
                description = f"Ação: {item_type}"

            description = description[:50] + ('...' if len(description) > 50 else '')
            display_type = item_type.capitalize()
            
            # Adicionar à lista, armazenando o índice original
            self.selected_elements_list.insert(tk.END, f"{i+1}. {display_type}: {description}")
            # Associar o índice original (i) ao item da listbox para referência
            # (Não é diretamente suportado por Listbox, usaremos o índice da listbox)
    
    def on_element_select(self, event=None):
        """Manipula a seleção de uma ação na lista da Etapa 3"""
        selected_indices = self.selected_elements_list.curselection()
        if not selected_indices:
            self.current_element_label.config(text="Nenhuma ação selecionada")
            self.add_assertion_button.config(state="disabled")
            return
        
        # Obter índice da ação selecionada
        index = selected_indices[0]
        action_data = self.test_config["selected_elements"][index]
        
        # Atualizar label
        listbox_text = self.selected_elements_list.get(index)
        self.current_element_label.config(text=listbox_text)
        
        # Habilitar/desabilitar adição de assertion baseado na seleção da árvore
        self.update_add_assertion_button_state()
        
        # Atualizar lista de assertions para esta ação
        self.update_assertions_list(index)
    
    def populate_assertion_tree(self):
        """Preenche a árvore de assertions com categorias e itens"""
        for category, assertions in self.all_assertions.items():
            # Inserir categoria como nó pai
            category_id = self.assertion_tree.insert(
                "", 
                tk.END, 
                text=category, 
                values=("",), # Coluna Descrição vazia para categoria
                open=False, # Começar fechado
                tags=("category",)
            )
            
            # Inserir assertions como nós filhos
            for assertion_name, assertion_info in assertions.items():
                self.assertion_tree.insert(
                    category_id, 
                    tk.END, 
                    text=assertion_name, 
                    values=(assertion_info.get("description", ""),),
                    tags=("assertion", category, assertion_name) # Armazenar categoria e nome nos tags
                )
    
    def on_assertion_tree_select(self, event=None):
        """Manipula a seleção de uma assertion na árvore"""
        selected_item = self.assertion_tree.focus()
        if not selected_item:
            self.update_add_assertion_button_state()
            return
        
        tags = self.assertion_tree.item(selected_item, "tags")
        
        # Verificar se é uma assertion (não uma categoria)
        if "assertion" in tags:
            category = tags[1]
            assertion_name = tags[2]
            assertion_info = CypressAssertions.get_assertion_info(category, assertion_name)
            
            # Verificar se a assertion precisa de valor
            needs_value = self._assertion_needs_value(assertion_name)
            
            if needs_value:
                # Ajustar label conforme o tipo
                if assertion_name in ["have.text", "contain.text", "have.value", "contain.value", "eq", "include", "contain"]:
                    self.assertion_value_label.config(text="Texto/Valor:")
                elif assertion_name in ["have.class", "not.have.class"]:
                    self.assertion_value_label.config(text="Classe CSS:")
                elif assertion_name in ["have.attr", "not.have.attr", "have.data"]:
                    self.assertion_value_label.config(text="Atributo=Valor:") # Ex: name=username ou data-test-id=login
                elif assertion_name in ["have.attr (existência)"]:
                    self.assertion_value_label.config(text="Atributo:")
                elif assertion_name in ["have.length", "have.length.greaterThan", "have.length.lessThan", "have.length.at.least", "have.length.at.most"]:
                    self.assertion_value_label.config(text="Número:")
                elif assertion_name in ["match", "not.match"]:
                     self.assertion_value_label.config(text="Regex:")
                elif assertion_name in ["be.gt", "be.gte", "be.lt", "be.lte"]:
                    self.assertion_value_label.config(text="Número:")
                elif assertion_name in ["be.within"]:
                    self.assertion_value_label.config(text="Min, Max:")
                elif assertion_name in ["be.closeTo"]:
                    self.assertion_value_label.config(text="Número, Margem:")
                elif assertion_name in ["be.a", "be.an"]:
                    self.assertion_value_label.config(text="Tipo (string, number, etc.):")
                elif assertion_name in ["status"]:
                    self.assertion_value_label.config(text="Código HTTP:")
                elif assertion_name in ["statusText"]:
                    self.assertion_value_label.config(text="Texto Status HTTP:")
                elif assertion_name in ["response.body"]:
                    self.assertion_value_label.config(text="Objeto/Valor JSON:")
                elif assertion_name in ["response.body.property"]:
                    self.assertion_value_label.config(text="Propriedade=Valor:")
                elif assertion_name in ["response.headers"]:
                    self.assertion_value_label.config(text="Cabeçalho=Valor:")
                else:
                    self.assertion_value_label.config(text="Valor:")
                    
                self.assertion_value_frame.pack(fill=tk.X, pady=10)
            else:
                self.assertion_value_frame.pack_forget()
        else:
            # Categoria selecionada, ocultar campo de valor
            self.assertion_value_frame.pack_forget()
            
        # Atualizar estado do botão "Adicionar"
        self.update_add_assertion_button_state()
    
    def _assertion_needs_value(self, assertion_name):
        """Verifica se uma assertion específica precisa de um valor"""
        # Lista de assertions que NÃO precisam de valor
        no_value_assertions = [
            "exist", "not.exist", "be.visible", "not.be.visible", 
            "be.checked", "not.be.checked", "be.disabled", "not.be.disabled",
            "be.enabled", "be.focused", "not.be.focused", "be.selected", 
            "not.be.selected", "be.empty", "not.be.empty", "be.true", 
            "be.false", "be.null", "not.be.null", "be.undefined", "not.be.undefined"
        ]
        return assertion_name not in no_value_assertions
    
    def update_add_assertion_button_state(self):
        """Atualiza o estado do botão 'Adicionar Assertion'"""
        action_selected = bool(self.selected_elements_list.curselection())
        assertion_selected = bool(self.assertion_tree.focus())
        is_assertion_node = False
        if assertion_selected:
            tags = self.assertion_tree.item(self.assertion_tree.focus(), "tags")
            is_assertion_node = "assertion" in tags
        
        if action_selected and assertion_selected and is_assertion_node:
            self.add_assertion_button.config(state="normal")
        else:
            self.add_assertion_button.config(state="disabled")
    
    def show_assertion_tooltip(self, event):
        """Exibe tooltip com descrição da assertion ao passar o mouse"""
        # Cancelar tooltip anterior se houver
        if self._tooltip_after_id:
            self.frame.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
            self.tooltip_frame.place_forget()
            
        # Identificar item sob o cursor
        item_id = self.assertion_tree.identify_row(event.y)
        if not item_id:
            return
        
        tags = self.assertion_tree.item(item_id, "tags")
        
        # Verificar se é uma assertion
        if "assertion" in tags:
            category = tags[1]
            assertion_name = tags[2]
            assertion_info = CypressAssertions.get_assertion_info(category, assertion_name)
            description = assertion_info.get("description", "")
            syntax = assertion_info.get("syntax", "")
            
            if description:
                tooltip_text = f"{description}\nSintaxe: {syntax}"
                # Agendar exibição do tooltip após um delay
                self._tooltip_after_id = self.frame.after(500, lambda: self._display_tooltip(event.x_root, event.y_root, tooltip_text))
    
    def _display_tooltip(self, x, y, text):
        """Posiciona e exibe o tooltip"""
        self.tooltip_label.config(text=text)
        self.tooltip_frame.update_idletasks() # Atualizar tamanho
        # Posicionar abaixo e à direita do cursor
        self.tooltip_frame.place(x=x + 10, y=y + 10)
    
    def add_assertion(self):
        """Adiciona uma assertion para a ação selecionada"""
        selected_action_indices = self.selected_elements_list.curselection()
        selected_assertion_item = self.assertion_tree.focus()
        
        if not selected_action_indices or not selected_assertion_item:
            return
        
        # Obter índice da ação
        action_index = selected_action_indices[0]
        
        # Obter dados da assertion selecionada na árvore
        tags = self.assertion_tree.item(selected_assertion_item, "tags")
        if "assertion" not in tags:
            return # Não é uma assertion válida
            
        category = tags[1]
        assertion_name = tags[2]
        assertion_info = CypressAssertions.get_assertion_info(category, assertion_name)
        assertion_value = self.assertion_value_var.get().strip()
        
        # Validar valor se necessário
        needs_value = self._assertion_needs_value(assertion_name)
        if needs_value and not assertion_value:
            messagebox.showwarning("Validação", "Por favor, informe um valor para este tipo de assertion.")
            return
            
        # Tratar casos especiais de valor (ex: atributos, within, closeTo)
        value1 = None
        value2 = None
        attr_name = None
        attr_value = None
        
        if assertion_name in ["have.attr", "not.have.attr", "have.data", "response.body.property", "response.headers"]:
            if '=' in assertion_value:
                parts = assertion_value.split('=', 1)
                attr_name = parts[0].strip()
                attr_value = parts[1].strip()
                if not attr_name:
                    messagebox.showwarning("Validação", "Formato inválido. Use 'nome=valor'.")
                    return
            else:
                # Se não houver '=', assume que é apenas o nome (para existência)
                attr_name = assertion_value
                attr_value = None # Indicar verificação de existência
        elif assertion_name == "have.attr (existência)":
             attr_name = assertion_value
             attr_value = None
        elif assertion_name == "be.within":
            if ',' not in assertion_value:
                messagebox.showwarning("Validação", "Formato inválido para 'within'. Use 'min, max'.")
                return
            parts = assertion_value.split(',', 1)
            try:
                value1 = float(parts[0].strip())
                value2 = float(parts[1].strip())
            except ValueError:
                messagebox.showwarning("Validação", "Valores inválidos para 'within'. Use números.")
                return
        elif assertion_name == "be.closeTo":
            if ',' not in assertion_value:
                messagebox.showwarning("Validação", "Formato inválido para 'closeTo'. Use 'numero, margem'.")
                return
            parts = assertion_value.split(',', 1)
            try:
                value1 = float(parts[0].strip())
                value2 = float(parts[1].strip()) # Margem
            except ValueError:
                messagebox.showwarning("Validação", "Valores inválidos para 'closeTo'. Use números.")
                return
        elif needs_value:
            value1 = assertion_value # Valor principal para outros casos

        # Criar assertion
        assertion = {
            "action_index": action_index, # Referencia a ação na lista test_config["selected_elements"]
            "category": category,
            "name": assertion_name,
            "value1": value1,
            "value2": value2,
            "attr_name": attr_name,
            "attr_value": attr_value
        }
        
        # Adicionar à lista de assertions
        if "assertions" not in self.test_config:
            self.test_config["assertions"] = []
        
        self.test_config["assertions"].append(assertion)
        
        # Atualizar lista de assertions na UI
        self.update_assertions_list(action_index)
        
        # Limpar campo de valor
        self.assertion_value_var.set("")
    
    def remove_assertion(self):
        """Remove a assertion selecionada da lista"""
        selected_assertion_indices = self.assertions_list.curselection()
        if not selected_assertion_indices:
            return
        
        # Obter índice da ação selecionada na lista da Etapa 3
        selected_action_indices = self.selected_elements_list.curselection()
        if not selected_action_indices:
            return
        
        action_index = selected_action_indices[0]
        assertion_list_index = selected_assertion_indices[0]
        
        # Encontrar a assertion correspondente na lista geral de assertions
        # Filtrar assertions para a ação atual e pegar a que corresponde ao índice da lista
        action_assertions = [a for a in self.test_config.get("assertions", []) if a["action_index"] == action_index]
        
        if assertion_list_index < len(action_assertions):
            assertion_to_remove = action_assertions[assertion_list_index]
            
            # Remover da lista principal
            if assertion_to_remove in self.test_config["assertions"]:
                self.test_config["assertions"].remove(assertion_to_remove)
                print(f"[DEBUG] Assertion removida: {assertion_to_remove}")
            else:
                 print(f"[WARN] Não foi possível encontrar a assertion para remover: {assertion_to_remove}")

            # Atualizar lista na UI
            self.update_assertions_list(action_index)
        else:
             print(f"[WARN] Índice de assertion inválido: {assertion_list_index}")

    
    def on_assertion_select(self, event=None):
        """Manipula a seleção de uma assertion na lista de assertions configuradas"""
        selected_indices = self.assertions_list.curselection()
        if not selected_indices:
            self.remove_assertion_button.config(state="disabled")
            return
        
        self.remove_assertion_button.config(state="normal")
    
    def update_assertions_list(self, action_index):
        """Atualiza a lista de assertions configuradas para a ação selecionada"""
        # Limpar lista
        self.assertions_list.delete(0, tk.END)
        
        # Adicionar assertions para a ação selecionada
        for assertion in self.test_config.get("assertions", []):
            if assertion["action_index"] == action_index:
                assertion_name = assertion["name"]
                assertion_text = f".should('{assertion_name}'"
                
                # Adicionar valores conforme necessário
                if assertion_name in ["have.attr", "not.have.attr", "have.data", "response.body.property", "response.headers"]:
                    if assertion["attr_value"] is None:
                        assertion_text += f", '{assertion['attr_name']}')"
                    else:
                        assertion_text += f", '{assertion['attr_name']}', '{assertion['attr_value']}')"
                elif assertion_name == "have.attr (existência)":
                     assertion_text += f", '{assertion['attr_name']}')"
                elif assertion_name == "be.within":
                    assertion_text += f", {assertion['value1']}, {assertion['value2']})"
                elif assertion_name == "be.closeTo":
                    assertion_text += f", {assertion['value1']}, {assertion['value2']})"
                elif assertion["value1"] is not None:
                    # Tratar strings e outros tipos
                    if isinstance(assertion["value1"], str):
                        assertion_text += f", '{assertion['value1']}')"
                    else:
                        assertion_text += f", {assertion['value1']})"
                else:
                    assertion_text += ")"
                
                self.assertions_list.insert(tk.END, assertion_text)
    
    def generate_code(self):
        """Gera o código do teste Cypress"""
        # Verificar se há elementos selecionados
        if not self.test_config["selected_elements"]:
            messagebox.showwarning("Validação", "Por favor, selecione pelo menos uma ação para o teste.")
            return
        
        # Atualizar interface
        self.code_status_label.config(
            text="Gerando código do teste...",
            bootstyle="warning"
        )
        self.generate_button.config(state="disabled")
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert(tk.END, "// Gerando código do teste...\n// Por favor, aguarde...")
        
        # Iniciar geração em thread separada
        threading.Thread(target=self._generate_code_thread, daemon=True).start()
    
    def _generate_code_thread(self):
        """Thread para geração do código do teste"""
        try:
            # Aqui seria a chamada para a API de IA para gerar o código
            # Por enquanto, vamos simular com um código de exemplo
            
            # Simular tempo de processamento
            time.sleep(1)
            
            # Gerar código de exemplo
            code = self._generate_example_code()
            
            # Atualizar interface na thread principal
            self.frame.after(0, lambda: self._update_generated_code(code))
            
        except Exception as e:
            # Atualizar interface na thread principal em caso de erro
            self.frame.after(0, lambda: self._update_generation_error(str(e)))
    
    def _generate_example_code(self):
        """Gera um código de exemplo baseado nos elementos selecionados e assertions"""
        test_name = self.test_config["name"]
        description = self.test_config["description"]
        
        # Cabeçalho do teste
        code = f"// Cypress Test: {test_name}\n"
        code += f"// Description: {description}\n"
        code += f"// Generated by CypressGen Pro\n\n"
        
        # Importações
        code += "/// <reference types=\"cypress\" />\n\n"
        
        # Descrição do teste
        code += f"describe('{test_name}', () => {{\n"
        code += f"  it('{description or 'should complete the test flow successfully'}', () => {{\n"
        
        # Agrupar assertions por índice de ação
        assertions_by_action_index = {}
        for assertion in self.test_config.get("assertions", []):
            idx = assertion["action_index"]
            if idx not in assertions_by_action_index:
                assertions_by_action_index[idx] = []
            assertions_by_action_index[idx].append(assertion)
            
        # Adicionar comandos para cada elemento selecionado
        for i, action in enumerate(self.test_config["selected_elements"]):
            action_type = action.get("type", "unknown")
            command_code = ""
            
            if action_type == "navigation":
                url = action.get("url", "")
                command_code += f"    // Navigate to URL\n"
                command_code += f"    cy.visit('{url}');\n"
                
            elif action_type == "click":
                selector = action.get("selector", "")
                element = action.get("element", {})
                text = element.get("text", "").strip()
                
                # Verificar se há um seletor personalizado
                if "custom_selector" in action:
                    selector = action["custom_selector"]["value"]
                
                command_code += f"    // Click element\n"
                if text and len(text) < 30:
                    command_code += f"    cy.get('{selector}').should('be.visible').click(); // {text}\n"
                else:
                    command_code += f"    cy.get('{selector}').should('be.visible').click();\n"
                
            elif action_type == "input":
                selector = action.get("selector", "")
                element = action.get("element", {})
                value = element.get("value", "")
                
                # Verificar se há um seletor personalizado
                if "custom_selector" in action:
                    selector = action["custom_selector"]["value"]
                
                command_code += f"    // Type into input field\n"
                command_code += f"    cy.get('{selector}').should('be.visible').clear().type('{value}');\n"
                
            elif action_type == "select":
                selector = action.get("selector", "")
                element = action.get("element", {})
                value = element.get("value", "")
                
                # Verificar se há um seletor personalizado
                if "custom_selector" in action:
                    selector = action["custom_selector"]["value"]
                
                command_code += f"    // Select option\n"
                command_code += f"    cy.get('{selector}').should('be.visible').select('{value}');\n"
                
            elif action_type == "network":
                method = action.get("method", "GET")
                url = action.get("url", "")
                endpoint = self._get_endpoint_name(url)
                alias = endpoint.lower().replace('-', '_') # Criar alias válido
                
                command_code += f"    // Intercept network request\n"
                command_code += f"    cy.intercept('{method}', '**/{endpoint}*').as('{alias}');\n"
                # Adicionar wait apenas se houver assertion para ele?
                # command_code += f"    cy.wait('@{alias}');\n"
            
            # Adicionar assertions para esta ação
            if i in assertions_by_action_index:
                # Remover a última nova linha do comando se houver
                if command_code.endswith('\n'):
                    command_code = command_code[:-1]
                    
                # Adicionar assertions encadeadas
                for assertion in assertions_by_action_index[i]:
                    assertion_name = assertion["name"]
                    assertion_text = f"\n      .should('{assertion_name}'"
                    
                    # Adicionar valores conforme necessário
                    if assertion_name in ["have.attr", "not.have.attr", "have.data", "response.body.property", "response.headers"]:
                        if assertion["attr_value"] is None:
                            assertion_text += f", '{assertion['attr_name']}')"
                        else:
                            assertion_text += f", '{assertion['attr_name']}', '{assertion['attr_value']}')"
                    elif assertion_name == "have.attr (existência)":
                         assertion_text += f", '{assertion['attr_name']}')"
                    elif assertion_name == "be.within":
                        assertion_text += f", {assertion['value1']}, {assertion['value2']})"
                    elif assertion_name == "be.closeTo":
                        assertion_text += f", {assertion['value1']}, {assertion['value2']})"
                    elif assertion["value1"] is not None:
                        # Tratar strings e outros tipos
                        if isinstance(assertion["value1"], str):
                            assertion_text += f", '{assertion['value1']}')"
                        else:
                            assertion_text += f", {assertion['value1']})"
                    else:
                        assertion_text += ")"
                    
                    command_code += assertion_text
                
                # Adicionar ponto e vírgula e nova linha no final das assertions
                command_code += ";\n"
            
            # Adicionar espaço extra após cada bloco de ação/assertion
            code += command_code + "\n"
        
        # Fechar o teste
        code += "  });\n"
        code += "});\n"
        
        return code
    
    def _update_generated_code(self, code):
        """Atualiza a interface com o código gerado"""
        self.generated_code = code
        
        # Atualizar editor de código
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert(tk.END, code)
        
        # Aplicar syntax highlighting
        self.apply_syntax_highlighting()
        
        # Atualizar status
        self.code_status_label.config(
            text="Código gerado com sucesso!",
            bootstyle="success"
        )
        
        # Atualizar botões
        self.generate_button.config(state="normal")
        self.regenerate_button.config(state="normal")
        self.next_button.config(state="normal")
        
        # Estimar tokens
        tokens = len(code.split())
        self.tokens_label.config(
            text=f"Aproximadamente {tokens} tokens"
        )
    
    def _update_generation_error(self, error_message):
        """Atualiza a interface em caso de erro na geração"""
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert(tk.END, f"// Erro ao gerar código:\n// {error_message}")
        
        self.code_status_label.config(
            text=f"Erro ao gerar código: {error_message}",
            bootstyle="danger"
        )
        
        self.generate_button.config(state="normal")
    
    def regenerate_code(self):
        """Regenera o código do teste"""
        self.generate_code()
    
    def update_summary(self):
        """Atualiza o resumo do teste na etapa final"""
        if not self.generated_code:
            return
        
        # Habilitar edição
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        
        # Adicionar resumo
        self.summary_text.insert(tk.END, f"Nome do Teste: {self.test_config['name']}\n\n")
        self.summary_text.insert(tk.END, f"Descrição: {self.test_config['description']}\n\n")
        
        # Estatísticas
        actions_count = len(self.test_config["selected_elements"])
        assertions_count = len(self.test_config.get("assertions", []))
        
        self.summary_text.insert(tk.END, f"Ações: {actions_count}\n")
        self.summary_text.insert(tk.END, f"Assertions: {assertions_count}\n\n")
        
        # Contagem por tipo
        action_types = {}
        for action in self.test_config["selected_elements"]:
            action_type = action.get("type", "unknown")
            action_types[action_type] = action_types.get(action_type, 0) + 1
        
        self.summary_text.insert(tk.END, "Tipos de Ações:\n")
        for action_type, count in action_types.items():
            self.summary_text.insert(tk.END, f"- {action_type.capitalize()}: {count}\n")
        
        # Desabilitar edição
        self.summary_text.config(state=tk.DISABLED)
    
    def save_test_file(self):
        """Salva o código gerado em um arquivo"""
        if not self.generated_code:
            messagebox.showwarning("Validação", "Por favor, gere o código do teste primeiro.")
            return
        
        # Solicitar local para salvar
        filename = filedialog.asksaveasfilename(
            title="Salvar Teste Cypress",
            filetypes=[("JavaScript", "*.js"), ("TypeScript", "*.ts"), ("Todos os Arquivos", "*.*")],
            defaultextension=".js" if not self.use_ts_var.get() else ".ts",
            initialfile=f"{self.test_config['name'].lower().replace(' ', '_')}.cy.js"
        )
        
        if not filename:
            return
        
        try:
            # Salvar arquivo
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.generated_code)
            
            self.app.update_status(f"Teste salvo em: {filename}", "success")
            messagebox.showinfo("Sucesso", f"Teste salvo com sucesso em:\n{filename}")
            
        except Exception as e:
            self.app.update_status(f"Erro ao salvar teste: {str(e)}", "error")
            messagebox.showerror("Erro", f"Erro ao salvar o arquivo:\n{str(e)}")
    
    def copy_to_clipboard(self):
        """Copia o código gerado para a área de transferência"""
        if not self.generated_code:
            messagebox.showwarning("Validação", "Por favor, gere o código do teste primeiro.")
            return
        
        self.frame.clipboard_clear()
        self.frame.clipboard_append(self.generated_code)
        
        self.app.update_status("Código copiado para a área de transferência", "success")
        messagebox.showinfo("Sucesso", "Código copiado para a área de transferência.")
    
    def edit_with_ai(self):
        """Abre o editor de IA para editar o código gerado"""
        if not self.generated_code:
            messagebox.showwarning("Validação", "Por favor, gere o código do teste primeiro.")
            return
        
        # Aqui seria a chamada para o módulo de edição com IA
        self.app.update_status("Abrindo editor de IA...", "info")
        
        # Verificar se o módulo de edição com IA está disponível
        if hasattr(self.app, "show_ai_editor"):
            self.app.show_ai_editor(self.generated_code, self.test_config["name"])
        else:
            messagebox.showinfo("Informação", "O editor de IA não está disponível nesta versão.")
    
    def start_new_test(self):
        """Inicia um novo teste, resetando o estado"""
        if messagebox.askyesno("Confirmar", "Deseja iniciar um novo teste? Todas as alterações não salvas serão perdidas."):
            # Resetar estado
            self.test_config = {
                "name": "",
                "description": "",
                "template": "default",
                "selected_elements": [],
                "assertions": [],
                "commands": [],
                "fixtures": []
            }
            self.generated_code = None
            self.custom_selectors = {}
            
            # Limpar interface
            self.test_name_var.set("")
            self.test_desc_text.delete("1.0", tk.END)
            self.template_var.set("default")
            
            # Voltar para a primeira etapa
            self.show_step(0)
            
            self.app.update_status("Novo teste iniciado", "success")
    
    def reset_steps_after(self, step_index):
        """Reseta o estado das etapas após a etapa especificada"""
        if step_index < 1:
            # Limpar árvore de elementos
            for item in self.elements_tree.get_children():
                self.elements_tree.delete(item)
            
            # Limpar seletores personalizados
            self.custom_selectors = {}
        
        if step_index < 2:
            # Limpar lista de elementos selecionados
            self.selected_elements_list.delete(0, tk.END)
            
            # Limpar lista de assertions configuradas
            self.assertions_list.delete(0, tk.END)
            
            # Resetar configuração de assertions
            self.test_config["assertions"] = []
            
            # Resetar seleção na árvore de assertions
            if hasattr(self, 'assertion_tree'):
                selection = self.assertion_tree.selection()
                if selection:
                    self.assertion_tree.selection_remove(selection)
                self.assertion_value_frame.pack_forget()
                self.add_assertion_button.config(state="disabled")
        
        if step_index < 3:
            # Limpar código gerado
            self.code_text.delete("1.0", tk.END)
            self.generated_code = None
            
            # Resetar status
            self.code_status_label.config(
                text="Clique em 'Gerar Código' para iniciar a geração",
                bootstyle="secondary"
            )
            
            # Resetar botões
            self.regenerate_button.config(state="disabled")
        
        if step_index < 4:
            # Limpar resumo
            self.summary_text.config(state=tk.NORMAL)
            self.summary_text.delete("1.0", tk.END)
            self.summary_text.config(state=tk.DISABLED)
