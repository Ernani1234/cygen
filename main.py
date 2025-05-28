"""
Módulo principal do CypressGen Pro v2.
Implementa a interface principal e integração de todos os módulos.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import os
import sys
import json
import threading
import queue
import time
from tkinter import messagebox, filedialog

# Importar módulos
from modules.element_capture import ElementCapture
from modules.test_generator import TestGenerator
from modules.ai_editor import AIEditor
from modules.ai_integration import AIIntegration
from modules.rule_capture import RuleCapture
from modules.settings import SettingsManager
from modules.utils.theme_manager import ThemeManager
from modules.utils.icon_manager import IconManager

class CypressGenProApp:
    """
    Aplicação principal do CypressGen Pro v2.
    """
    
    def __init__(self, root):
        """
        Inicializa a aplicação principal.
        
        Args:
            root: Janela raiz do Tkinter
        """
        self.root = root
        self.root.title("CypressGen Pro v2")
        self.root.geometry("1280x720")
        self.root.minsize(1024, 600)
        
        # Configurar estilo
        self.style = ttk.Style(theme="darkly")
        
        # Carregar configurações
        self.settings_manager = SettingsManager()
        self.config = self.settings_manager.load_settings()
        
        # Gerenciador de temas
        self.theme_manager = ThemeManager(self.style)
        
        # Gerenciador de ícones
        self.icon_manager = IconManager()
        
        # Variáveis de estado
        self.current_module = None
        self.current_log_path = None
        
        # Criar estrutura de diretórios
        self.create_directories()
        
        # Configurar interface
        self.setup_ui()
        
        # Inicializar módulos
        self.init_modules()
        
        # Mostrar módulo inicial
        self.show_module("dashboard")
    
    def create_directories(self):
        """Cria a estrutura de diretórios necessária"""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # Diretórios principais
        dirs = [
            os.path.join(base_dir, "logs"),
            os.path.join(base_dir, "tests"),
            os.path.join(base_dir, "config"),
            os.path.join(base_dir, "resources", "icons"),
            os.path.join(base_dir, "temp"),
            os.path.join(base_dir, "conversations")
        ]
        
        # Criar diretórios
        for directory in dirs:
            os.makedirs(directory, exist_ok=True)
    
    def setup_ui(self):
        """Configura a interface do usuário"""
        # Frame principal
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Barra lateral
        self.sidebar_frame = ttk.Frame(self.main_frame, width=200, bootstyle="secondary")
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)
        
        # Área de conteúdo
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Configurar barra lateral
        self.setup_sidebar()
        
        # Barra de status
        self.status_frame = ttk.Frame(self.root, bootstyle="secondary", padding=2)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Status principal
        self.status_label = ttk.Label(
            self.status_frame, 
            text="Pronto",
            bootstyle="info"
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Status da API
        self.api_status_frame = ttk.Frame(self.status_frame)
        self.api_status_frame.pack(side=tk.RIGHT, padx=10)
        
        self.api_tokens_label = ttk.Label(
            self.api_status_frame,
            text="Tokens: 0",
            bootstyle="info"
        )
        self.api_tokens_label.pack(side=tk.LEFT, padx=5)
        
        self.api_cost_label = ttk.Label(
            self.api_status_frame,
            text="Custo: $0.00",
            bootstyle="info"
        )
        self.api_cost_label.pack(side=tk.LEFT, padx=5)
    
    def setup_sidebar(self):
        """Configura a barra lateral"""
        # Título
        title_frame = ttk.Frame(self.sidebar_frame, padding=10)
        title_frame.pack(fill=tk.X)
        
        ttk.Label(
            title_frame, 
            text="CypressGen Pro", 
            font=("Helvetica", 16, "bold"),
            bootstyle="light"
        ).pack(anchor=tk.W)
        
        ttk.Label(
            title_frame, 
            text="v2.0", 
            font=("Helvetica", 10),
            bootstyle="light"
        ).pack(anchor=tk.W)
        
        # Separador
        ttk.Separator(self.sidebar_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)
        
        # Botões de navegação
        nav_frame = ttk.Frame(self.sidebar_frame, padding=10)
        nav_frame.pack(fill=tk.X)
        
        # Botão Dashboard
        self.create_nav_button(
            nav_frame, 
            "Dashboard", 
            "dashboard_24", 
            lambda: self.show_module("dashboard")
        )
        
        # Botão Captura
        self.create_nav_button(
            nav_frame, 
            "Captura de Elementos", 
            "capture_24", 
            lambda: self.show_module("capture")
        )
        
        # Botão Captura de Regras
        self.create_nav_button(
            nav_frame, 
            "Captura de Regras", 
            "rules_24", 
            lambda: self.show_module("rules")
        )
        
        # Botão Gerador
        self.create_nav_button(
            nav_frame, 
            "Gerador de Testes", 
            "generator_24", 
            lambda: self.show_module("generator")
        )
        
        # Botão Editor
        self.create_nav_button(
            nav_frame, 
            "Editor com IA", 
            "editor_24", 
            lambda: self.show_module("editor")
        )
        
        # Botão Logs
        self.create_nav_button(
            nav_frame, 
            "Logs", 
            "logs_24", 
            lambda: self.show_module("logs")
        )
        
        # Separador
        ttk.Separator(self.sidebar_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)
        
        # Botão Configurações
        self.create_nav_button(
            nav_frame, 
            "Configurações", 
            "settings_24", 
            lambda: self.show_module("settings")
        )
        
        # Informações de versão e créditos
        info_frame = ttk.Frame(self.sidebar_frame, padding=10)
        info_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        ttk.Label(
            info_frame, 
            text="© 2025 CypressGen Pro",
            font=("Helvetica", 8),
            bootstyle="secondary"
        ).pack(anchor=tk.CENTER)
    
    def create_nav_button(self, parent, text, icon_name, command):
        """
        Cria um botão de navegação na barra lateral.
        
        Args:
            parent: Frame pai
            text: Texto do botão
            icon_name: Nome do ícone
            command: Função a ser chamada ao clicar
        """
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=5)
        
        # Obter ícone
        icon = self.icon_manager.get_icon(icon_name)
        
        # Criar botão
        button = ttk.Button(
            button_frame,
            text=f" {text}",
            compound=tk.LEFT,
            command=command,
            bootstyle="outline-light",
            width=25
        )
        
        if icon:
            button.config(image=icon)
        
        button.pack(fill=tk.X)
    
    def init_modules(self):
        """Inicializa os módulos da aplicação"""
        # Criar frames para cada módulo
        self.module_frames = {
            "dashboard": ttk.Frame(self.content_frame),
            "capture": ttk.Frame(self.content_frame),
            "rules": ttk.Frame(self.content_frame),
            "generator": ttk.Frame(self.content_frame),
            "editor": ttk.Frame(self.content_frame),
            "logs": ttk.Frame(self.content_frame),
            "settings": ttk.Frame(self.content_frame)
        }
        
        # Inicializar módulo de integração com IA
        self.modules = {
            "ai_integration": AIIntegration(self)
        }
        
        # Inicializar módulos de interface
        self.modules["capture"] = ElementCapture(self.module_frames["capture"], self)
        self.modules["rules"] = RuleCapture(self.module_frames["rules"], self)
        self.modules["generator"] = TestGenerator(self.module_frames["generator"], self)
        self.modules["editor"] = AIEditor(self.module_frames["editor"], self)
        
        # Configurar dashboard
        self.setup_dashboard()
        
        # Configurar logs
        self.setup_logs()
        
        # Configurar configurações
        self.setup_settings()
    
    def setup_dashboard(self):
        """Configura o módulo de dashboard"""
        frame = self.module_frames["dashboard"]
        
        # Título
        ttk.Label(
            frame, 
            text="Dashboard", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Cards de estatísticas
        stats_frame = ttk.Frame(frame, padding=10)
        stats_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Card de testes gerados
        tests_card = ttk.LabelFrame(stats_frame, text="Testes Gerados", padding=20)
        tests_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.tests_count_label = ttk.Label(
            tests_card, 
            text="0", 
            font=("Helvetica", 36, "bold"),
            bootstyle="success"
        )
        self.tests_count_label.pack(anchor=tk.CENTER)
        
        # Card de elementos capturados
        elements_card = ttk.LabelFrame(stats_frame, text="Elementos Capturados", padding=20)
        elements_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.elements_count_label = ttk.Label(
            elements_card, 
            text="0", 
            font=("Helvetica", 36, "bold"),
            bootstyle="info"
        )
        self.elements_count_label.pack(anchor=tk.CENTER)
        
        # Card de uso da API
        api_card = ttk.LabelFrame(stats_frame, text="Uso da API", padding=20)
        api_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.api_usage_label = ttk.Label(
            api_card, 
            text="0 tokens", 
            font=("Helvetica", 36, "bold"),
            bootstyle="warning"
        )
        self.api_usage_label.pack(anchor=tk.CENTER)
        
        # Ações rápidas
        actions_frame = ttk.LabelFrame(frame, text="Ações Rápidas", padding=20)
        actions_frame.pack(fill=tk.X, padx=20, pady=20)
        
        # Botão de nova captura
        new_capture_button = ttk.Button(
            actions_frame,
            text="Nova Captura",
            bootstyle="success",
            width=20,
            command=lambda: self.show_module("capture")
        )
        new_capture_button.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Botão de captura de regras
        new_rules_button = ttk.Button(
            actions_frame,
            text="Captura de Regras",
            bootstyle="warning",
            width=20,
            command=lambda: self.show_module("rules")
        )
        new_rules_button.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Botão de novo teste
        new_test_button = ttk.Button(
            actions_frame,
            text="Novo Teste",
            bootstyle="primary",
            width=20,
            command=lambda: self.show_module("generator")
        )
        new_test_button.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Botão de abrir editor
        open_editor_button = ttk.Button(
            actions_frame,
            text="Abrir Editor",
            bootstyle="info",
            width=20,
            command=lambda: self.show_module("editor")
        )
        open_editor_button.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Testes recentes
        recent_frame = ttk.LabelFrame(frame, text="Testes Recentes", padding=20)
        recent_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Lista de testes recentes
        self.recent_tests_list = tk.Listbox(
            recent_frame,
            height=10,
            font=("Segoe UI", 10)
        )
        recent_scrollbar = ttk.Scrollbar(
            recent_frame, 
            orient="vertical", 
            command=self.recent_tests_list.yview
        )
        self.recent_tests_list.configure(yscrollcommand=recent_scrollbar.set)
        
        self.recent_tests_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        recent_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular evento de duplo clique
        self.recent_tests_list.bind("<Double-1>", self.open_recent_test)
        
        # Carregar testes recentes
        self.load_recent_tests()
    
    def setup_logs(self):
        """Configura o módulo de logs"""
        frame = self.module_frames["logs"]
        
        # Título
        ttk.Label(
            frame, 
            text="Logs de Captura", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Filtros
        filters_frame = ttk.Frame(frame, padding=10)
        filters_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Label(filters_frame, text="Filtrar por:").pack(side=tk.LEFT)
        
        self.log_filter_var = tk.StringVar(value="Todos")
        filter_combo = ttk.Combobox(
            filters_frame, 
            textvariable=self.log_filter_var,
            values=["Todos", "Hoje", "Esta Semana", "Este Mês"],
            state="readonly",
            width=15
        )
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind("<<ComboboxSelected>>", self.filter_logs)
        
        # Botão de atualizar
        refresh_button = ttk.Button(
            filters_frame,
            text="Atualizar",
            command=self.load_logs
        )
        refresh_button.pack(side=tk.RIGHT)
        
        # Lista de logs
        logs_frame = ttk.Frame(frame, padding=10)
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Configurar árvore
        columns = ("Nome", "Data", "Elementos", "Tamanho")
        self.logs_tree = ttk.Treeview(
            logs_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        
        # Configurar colunas
        self.logs_tree.heading("Nome", text="Nome")
        self.logs_tree.heading("Data", text="Data")
        self.logs_tree.heading("Elementos", text="Elementos")
        self.logs_tree.heading("Tamanho", text="Tamanho")
        
        self.logs_tree.column("Nome", width=300)
        self.logs_tree.column("Data", width=150)
        self.logs_tree.column("Elementos", width=100)
        self.logs_tree.column("Tamanho", width=100)
        
        # Scrollbar
        logs_scrollbar = ttk.Scrollbar(
            logs_frame, 
            orient="vertical", 
            command=self.logs_tree.yview
        )
        self.logs_tree.configure(yscrollcommand=logs_scrollbar.set)
        
        self.logs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        logs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular evento de duplo clique
        self.logs_tree.bind("<Double-1>", self.open_log)
        
        # Botões de ação
        buttons_frame = ttk.Frame(frame, padding=10)
        buttons_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Botão de abrir
        open_button = ttk.Button(
            buttons_frame,
            text="Abrir Log",
            command=self.open_selected_log
        )
        open_button.pack(side=tk.LEFT, padx=5)
        
        # Botão de excluir
        delete_button = ttk.Button(
            buttons_frame,
            text="Excluir Log",
            bootstyle="danger",
            command=self.delete_selected_log
        )
        delete_button.pack(side=tk.LEFT, padx=5)
        
        # Botão de gerar teste
        generate_button = ttk.Button(
            buttons_frame,
            text="Gerar Teste",
            bootstyle="success",
            command=self.generate_test_from_log
        )
        generate_button.pack(side=tk.RIGHT, padx=5)
        
        # Carregar logs
        self.load_logs()
    
    def setup_settings(self):
        """Configura o módulo de configurações"""
        frame = self.module_frames["settings"]
        
        # Título
        ttk.Label(
            frame, 
            text="Configurações", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Notebook para abas
        settings_notebook = ttk.Notebook(frame)
        settings_notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Aba geral
        general_tab = ttk.Frame(settings_notebook, padding=20)
        settings_notebook.add(general_tab, text="Geral")
        
        # Aba API
        api_tab = ttk.Frame(settings_notebook, padding=20)
        settings_notebook.add(api_tab, text="API")
        
        # Aba seletores
        selectors_tab = ttk.Frame(settings_notebook, padding=20)
        settings_notebook.add(selectors_tab, text="Seletores")
        
        # Aba dashboard
        dashboard_tab = ttk.Frame(settings_notebook, padding=20)
        settings_notebook.add(dashboard_tab, text="Dashboard")
        
        # Configurar aba geral
        self.setup_general_settings(general_tab)
        
        # Configurar aba API
        self.setup_api_settings(api_tab)
        
        # Configurar aba seletores
        self.setup_selector_settings(selectors_tab)
        
        # Configurar aba dashboard
        self.setup_dashboard_settings(dashboard_tab)
        
        # Botões de ação
        buttons_frame = ttk.Frame(frame, padding=10)
        buttons_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=10)
        
        # Botão de salvar
        save_button = ttk.Button(
            buttons_frame,
            text="Salvar Configurações",
            bootstyle="success",
            command=self.save_settings
        )
        save_button.pack(side=tk.RIGHT, padx=5)
        
        # Botão de restaurar padrões
        reset_button = ttk.Button(
            buttons_frame,
            text="Restaurar Padrões",
            bootstyle="warning",
            command=self.reset_settings
        )
        reset_button.pack(side=tk.RIGHT, padx=5)
    
    def setup_general_settings(self, parent):
        """
        Configura as configurações gerais.
        
        Args:
            parent: Frame pai
        """
        # Tema
        theme_frame = ttk.LabelFrame(parent, text="Tema", padding=10)
        theme_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(theme_frame, text="Tema da Interface:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.theme_var = tk.StringVar(value=self.config.get("theme", "darkly"))
        theme_combo = ttk.Combobox(
            theme_frame, 
            textvariable=self.theme_var,
            values=["darkly", "superhero", "cyborg", "vapor", "solar"],
            state="readonly",
            width=15
        )
        theme_combo.pack(side=tk.LEFT)
        
        ttk.Label(theme_frame, text="(Requer reiniciar a aplicação)").pack(side=tk.LEFT, padx=(10, 0))
        
        # Timeout
        timeout_frame = ttk.LabelFrame(parent, text="Timeout", padding=10)
        timeout_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(timeout_frame, text="Timeout Padrão (ms):").pack(side=tk.LEFT, padx=(0, 10))
        
        self.timeout_var = tk.StringVar(value=str(self.config.get("default_timeout", 5000)))
        timeout_entry = ttk.Entry(
            timeout_frame, 
            textvariable=self.timeout_var,
            width=10
        )
        timeout_entry.pack(side=tk.LEFT)
        
        # Opções de teste
        test_frame = ttk.LabelFrame(parent, text="Opções de Teste", padding=10)
        test_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.typescript_var = tk.BooleanVar(value=self.config.get("use_typescript", False))
        ttk.Checkbutton(
            test_frame,
            text="Usar TypeScript",
            variable=self.typescript_var
        ).pack(anchor=tk.W)
        
        self.network_var = tk.BooleanVar(value=self.config.get("capture_network", True))
        ttk.Checkbutton(
            test_frame,
            text="Capturar Requisições de Rede",
            variable=self.network_var
        ).pack(anchor=tk.W)
    
    def setup_api_settings(self, parent):
        """
        Configura as configurações de API.
        
        Args:
            parent: Frame pai
        """
        # Chave da API
        api_key_frame = ttk.LabelFrame(parent, text="Chave da API", padding=10)
        api_key_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(api_key_frame, text="Chave da API OpenAI:").pack(anchor=tk.W, pady=(0, 5))
        
        self.api_key_var = tk.StringVar(value=self.config.get("api_key", ""))
        api_key_entry = ttk.Entry(
            api_key_frame, 
            textvariable=self.api_key_var,
            width=50,
            show="*"
        )
        api_key_entry.pack(fill=tk.X)
        
        # Modelo
        model_frame = ttk.LabelFrame(parent, text="Modelo", padding=10)
        model_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(model_frame, text="Modelo da API:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.model_var = tk.StringVar(value=self.config.get("model", "gpt-3.5-turbo"))
        model_combo = ttk.Combobox(
            model_frame, 
            textvariable=self.model_var,
            values=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
            state="readonly",
            width=15
        )
        model_combo.pack(side=tk.LEFT)
        
        # Estatísticas
        stats_frame = ttk.LabelFrame(parent, text="Estatísticas de Uso", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.stats_text = tk.Text(
            stats_frame,
            height=5,
            width=50,
            bg="#282a36",
            fg="#f8f8f2",
            font=("Consolas", 10),
            state="disabled"
        )
        self.stats_text.pack(fill=tk.X)
        
        # Atualizar estatísticas
        self.update_api_stats_display()
    
    def setup_selector_settings(self, parent):
        """
        Configura as configurações de seletores.
        
        Args:
            parent: Frame pai
        """
        # Prioridade de seletores
        priority_frame = ttk.LabelFrame(parent, text="Prioridade de Seletores", padding=10)
        priority_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            priority_frame, 
            text="Arraste para reordenar a prioridade dos seletores:"
        ).pack(anchor=tk.W, pady=(0, 5))
        
        # Lista de seletores
        self.selectors_listbox = tk.Listbox(
            priority_frame,
            bg="#282a36",
            fg="#f8f8f2",
            selectbackground="#44475a",
            selectforeground="#f8f8f2",
            font=("Segoe UI", 10),
            height=9
        )
        
        selectors_scrollbar = ttk.Scrollbar(
            priority_frame, 
            orient="vertical", 
            command=self.selectors_listbox.yview
        )
        
        self.selectors_listbox.configure(yscrollcommand=selectors_scrollbar.set)
        
        selectors_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.selectors_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Preencher lista de seletores
        selector_priority = self.config.get("selector_priority", [])
        for selector in selector_priority:
            self.selectors_listbox.insert(tk.END, selector)
        
        # Botões para reordenar
        reorder_frame = ttk.Frame(priority_frame)
        reorder_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            reorder_frame,
            text="↑",
            width=3,
            command=self.move_selector_up
        ).pack(pady=2)
        
        ttk.Button(
            reorder_frame,
            text="↓",
            width=3,
            command=self.move_selector_down
        ).pack(pady=2)
        
        # Habilitar/desabilitar seletores
        enable_frame = ttk.LabelFrame(parent, text="Habilitar/Desabilitar Seletores", padding=10)
        enable_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Criar checkboxes para cada seletor
        self.selector_vars = {}
        selector_enabled = self.config.get("selector_enabled", {})
        
        for i, selector in enumerate(selector_priority):
            var = tk.BooleanVar(value=selector_enabled.get(selector, True))
            self.selector_vars[selector] = var
            
            ttk.Checkbutton(
                enable_frame,
                text=selector,
                variable=var
            ).grid(row=i // 3, column=i % 3, sticky=tk.W, padx=10, pady=2)
    
    def setup_dashboard_settings(self, parent):
        """
        Configura as configurações do dashboard.
        
        Args:
            parent: Frame pai
        """
        # Estatísticas de uso
        usage_frame = ttk.LabelFrame(parent, text="Estatísticas de Uso da API", padding=10)
        usage_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Texto para estatísticas
        self.dashboard_text = tk.Text(
            usage_frame,
            height=10,
            width=60,
            bg="#282a36",
            fg="#f8f8f2",
            font=("Consolas", 10),
            state="disabled"
        )
        
        dashboard_scrollbar = ttk.Scrollbar(
            usage_frame, 
            orient="vertical", 
            command=self.dashboard_text.yview
        )
        
        self.dashboard_text.configure(yscrollcommand=dashboard_scrollbar.set)
        
        dashboard_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.dashboard_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Botões de ação
        actions_frame = ttk.Frame(parent)
        actions_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(
            actions_frame,
            text="Atualizar Estatísticas",
            command=self.update_dashboard
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            actions_frame,
            text="Exportar Estatísticas",
            command=self.export_stats
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            actions_frame,
            text="Limpar Estatísticas",
            bootstyle="danger",
            command=self.clear_stats
        ).pack(side=tk.RIGHT, padx=5)
        
        # Atualizar dashboard
        self.update_dashboard()
    
    def show_module(self, module_name):
        """
        Mostra um módulo específico.
        
        Args:
            module_name: Nome do módulo a ser exibido
        """
        # Ocultar todos os módulos
        for frame in self.module_frames.values():
            frame.pack_forget()
        
        # Mostrar módulo selecionado
        if module_name in self.module_frames:
            self.module_frames[module_name].pack(fill=tk.BOTH, expand=True)
            self.current_module = module_name
            
            # Atualizar título da janela
            module_titles = {
                "dashboard": "Dashboard",
                "capture": "Captura de Elementos",
                "rules": "Captura de Regras",
                "generator": "Gerador de Testes",
                "editor": "Editor com IA",
                "logs": "Logs",
                "settings": "Configurações"
            }
            self.root.title(f"CypressGen Pro v2 - {module_titles.get(module_name, '')}")
    
    def load_recent_tests(self):
        """Carrega a lista de testes recentes"""
        # Limpar lista
        self.recent_tests_list.delete(0, tk.END)
        
        # Diretório de testes
        tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")
        if not os.path.exists(tests_dir):
            return
        
        # Listar arquivos de teste
        test_files = []
        for file in os.listdir(tests_dir):
            if file.endswith(".cy.js") or file.endswith(".cy.ts"):
                file_path = os.path.join(tests_dir, file)
                test_files.append((file, os.path.getmtime(file_path)))
        
        # Ordenar por data de modificação (mais recentes primeiro)
        test_files.sort(key=lambda x: x[1], reverse=True)
        
        # Adicionar à lista
        for file, _ in test_files[:10]:  # Mostrar apenas os 10 mais recentes
            self.recent_tests_list.insert(tk.END, file)
        
        # Atualizar contador no dashboard
        self.tests_count_label.config(text=str(len(test_files)))
    
    def open_recent_test(self, event):
        """
        Abre um teste recente.
        
        Args:
            event: Evento de clique
        """
        # Obter índice selecionado
        selected = self.recent_tests_list.curselection()
        if not selected:
            return
        
        # Obter nome do arquivo
        filename = self.recent_tests_list.get(selected[0])
        
        # Caminho completo
        file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", filename)
        
        # Verificar se o arquivo existe
        if not os.path.exists(file_path):
            messagebox.showerror("Erro", f"Arquivo não encontrado: {file_path}")
            return
        
        # Abrir no editor
        self.show_module("editor")
        self.modules["editor"].load_file(file_path)
    
    def load_logs(self):
        """Carrega a lista de logs"""
        # Limpar árvore
        for item in self.logs_tree.get_children():
            self.logs_tree.delete(item)
        
        # Diretório de logs
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        if not os.path.exists(logs_dir):
            return
        
        # Listar arquivos de log
        log_files = []
        for file in os.listdir(logs_dir):
            if file.endswith(".json"):
                file_path = os.path.join(logs_dir, file)
                
                # Obter informações do arquivo
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        log_data = json.load(f)
                    
                    # Extrair informações
                    session_info = log_data.get("session_info", {})
                    name = session_info.get("name", file)
                    date = session_info.get("timestamp", "")
                    elements = len(log_data.get("captured_actions", []))
                    size = os.path.getsize(file_path) // 1024  # KB
                    
                    # Formatar data
                    if date:
                        try:
                            date_obj = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f")
                            date = date_obj.strftime("%d/%m/%Y %H:%M")
                        except:
                            pass
                    
                    log_files.append((file_path, name, date, elements, size))
                except:
                    # Ignorar arquivos inválidos
                    pass
        
        # Ordenar por data (mais recentes primeiro)
        log_files.sort(key=lambda x: x[2], reverse=True)
        
        # Aplicar filtro
        filter_value = self.log_filter_var.get()
        if filter_value != "Todos":
            today = datetime.now().date()
            filtered_logs = []
            
            for log in log_files:
                try:
                    log_date = datetime.strptime(log[2], "%d/%m/%Y %H:%M").date()
                    
                    if filter_value == "Hoje" and log_date == today:
                        filtered_logs.append(log)
                    elif filter_value == "Esta Semana" and (today - log_date).days <= 7:
                        filtered_logs.append(log)
                    elif filter_value == "Este Mês" and (today - log_date).days <= 30:
                        filtered_logs.append(log)
                except:
                    # Ignorar datas inválidas
                    pass
            
            log_files = filtered_logs
        
        # Adicionar à árvore
        for file_path, name, date, elements, size in log_files:
            self.logs_tree.insert("", tk.END, values=(name, date, elements, f"{size} KB"), tags=(file_path,))
        
        # Atualizar contador de elementos no dashboard
        total_elements = sum(log[3] for log in log_files)
        self.elements_count_label.config(text=str(total_elements))
    
    def filter_logs(self, event):
        """
        Filtra os logs por período.
        
        Args:
            event: Evento de seleção
        """
        self.load_logs()
    
    def open_log(self, event):
        """
        Abre um log ao clicar duas vezes.
        
        Args:
            event: Evento de clique
        """
        self.open_selected_log()
    
    def open_selected_log(self):
        """Abre o log selecionado"""
        # Obter item selecionado
        selected = self.logs_tree.selection()
        if not selected:
            messagebox.showinfo("Aviso", "Selecione um log para abrir.")
            return
        
        # Obter caminho do arquivo
        item = selected[0]
        file_path = self.logs_tree.item(item, "tags")[0]
        
        # Verificar se o arquivo existe
        if not os.path.exists(file_path):
            messagebox.showerror("Erro", f"Arquivo não encontrado: {file_path}")
            return
        
        # Abrir no gerador de testes
        self.current_log_path = file_path
        self.show_module("generator")
        self.modules["generator"].load_log(file_path)
    
    def delete_selected_log(self):
        """Exclui o log selecionado"""
        # Obter item selecionado
        selected = self.logs_tree.selection()
        if not selected:
            messagebox.showinfo("Aviso", "Selecione um log para excluir.")
            return
        
        # Obter caminho do arquivo
        item = selected[0]
        file_path = self.logs_tree.item(item, "tags")[0]
        file_name = self.logs_tree.item(item, "values")[0]
        
        # Confirmar exclusão
        if not messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir o log '{file_name}'?"):
            return
        
        # Excluir arquivo
        try:
            os.remove(file_path)
            self.logs_tree.delete(item)
            messagebox.showinfo("Sucesso", f"Log '{file_name}' excluído com sucesso.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao excluir log: {str(e)}")
    
    def generate_test_from_log(self):
        """Gera um teste a partir do log selecionado"""
        # Obter item selecionado
        selected = self.logs_tree.selection()
        if not selected:
            messagebox.showinfo("Aviso", "Selecione um log para gerar teste.")
            return
        
        # Obter caminho do arquivo
        item = selected[0]
        file_path = self.logs_tree.item(item, "tags")[0]
        
        # Verificar se o arquivo existe
        if not os.path.exists(file_path):
            messagebox.showerror("Erro", f"Arquivo não encontrado: {file_path}")
            return
        
        # Abrir no gerador de testes
        self.current_log_path = file_path
        self.show_module("generator")
        self.modules["generator"].load_log(file_path)
    
    def move_selector_up(self):
        """Move o seletor selecionado para cima na lista de prioridade"""
        selected = self.selectors_listbox.curselection()
        if not selected or selected[0] == 0:
            return
        
        index = selected[0]
        text = self.selectors_listbox.get(index)
        
        self.selectors_listbox.delete(index)
        self.selectors_listbox.insert(index - 1, text)
        self.selectors_listbox.selection_set(index - 1)
    
    def move_selector_down(self):
        """Move o seletor selecionado para baixo na lista de prioridade"""
        selected = self.selectors_listbox.curselection()
        if not selected or selected[0] == self.selectors_listbox.size() - 1:
            return
        
        index = selected[0]
        text = self.selectors_listbox.get(index)
        
        self.selectors_listbox.delete(index)
        self.selectors_listbox.insert(index + 1, text)
        self.selectors_listbox.selection_set(index + 1)
    
    def save_settings(self):
        """Salva as configurações"""
        try:
            # Atualizar configurações com valores da interface
            self.config["api_key"] = self.api_key_var.get()
            self.config["model"] = self.model_var.get()
            self.config["theme"] = self.theme_var.get()
            self.config["default_timeout"] = int(self.timeout_var.get())
            self.config["use_typescript"] = self.typescript_var.get()
            self.config["capture_network"] = self.network_var.get()
            
            # Atualizar prioridade de seletores
            selector_priority = []
            for i in range(self.selectors_listbox.size()):
                selector_priority.append(self.selectors_listbox.get(i))
            
            self.config["selector_priority"] = selector_priority
            
            # Atualizar seletores habilitados
            selector_enabled = {}
            for selector, var in self.selector_vars.items():
                selector_enabled[selector] = var.get()
            
            self.config["selector_enabled"] = selector_enabled
            
            # Salvar configurações
            self.settings_manager.save_settings(self.config)
            
            messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {str(e)}")
    
    def reset_settings(self):
        """Restaura as configurações padrão"""
        if messagebox.askyesno("Restaurar Padrões", "Tem certeza que deseja restaurar todas as configurações para os valores padrão?"):
            # Obter configurações padrão
            default_settings = self.settings_manager.get_default_settings()
            
            # Atualizar interface
            self.api_key_var.set(default_settings.get("api_key", ""))
            self.model_var.set(default_settings.get("model", "gpt-3.5-turbo"))
            self.theme_var.set(default_settings.get("theme", "darkly"))
            self.timeout_var.set(str(default_settings.get("default_timeout", 5000)))
            self.typescript_var.set(default_settings.get("use_typescript", False))
            self.network_var.set(default_settings.get("capture_network", True))
            
            # Atualizar lista de seletores
            self.selectors_listbox.delete(0, tk.END)
            for selector in default_settings.get("selector_priority", []):
                self.selectors_listbox.insert(tk.END, selector)
            
            # Atualizar checkboxes de seletores
            selector_enabled = default_settings.get("selector_enabled", {})
            for selector, var in self.selector_vars.items():
                var.set(selector_enabled.get(selector, True))
            
            # Atualizar configurações
            self.config = default_settings
            
            messagebox.showinfo("Sucesso", "Configurações restauradas para os valores padrão.")
    
    def update_dashboard(self):
        """Atualiza o dashboard com estatísticas de uso"""
        try:
            # Obter estatísticas de uso
            usage_stats = self.modules["ai_integration"].get_usage_stats()
            
            # Atualizar texto do dashboard
            self.dashboard_text.config(state="normal")
            self.dashboard_text.delete("1.0", tk.END)
            
            # Formatar estatísticas
            total_tokens = usage_stats.get("total_tokens", 0)
            prompt_tokens = usage_stats.get("prompt_tokens", 0)
            completion_tokens = usage_stats.get("completion_tokens", 0)
            total_requests = usage_stats.get("total_requests", 0)
            last_request = usage_stats.get("last_request", None)
            
            # Calcular custo estimado (aproximadamente $0.0015 por 1K tokens para gpt-3.5-turbo)
            estimated_cost = (total_tokens / 1000) * 0.0015
            
            # Formatar texto
            stats_text = f"Total de Tokens: {total_tokens:,}\n"
            stats_text += f"Tokens de Prompt: {prompt_tokens:,}\n"
            stats_text += f"Tokens de Resposta: {completion_tokens:,}\n"
            stats_text += f"Total de Requisições: {total_requests:,}\n"
            
            if last_request:
                from datetime import datetime
                last_request_time = datetime.fromtimestamp(last_request).strftime("%d/%m/%Y %H:%M:%S")
                stats_text += f"Última Requisição: {last_request_time}\n"
            else:
                stats_text += "Última Requisição: Nunca\n"
            
            stats_text += f"\nCusto Estimado: ${estimated_cost:.4f} USD\n"
            stats_text += f"\nReferência: {self.config.get('cost_pattern', '1,385 requests(6,024,231 tokens) = $6.94(dollar)')}"
            
            self.dashboard_text.insert("1.0", stats_text)
            self.dashboard_text.config(state="disabled")
            
            # Atualizar texto de estatísticas na aba de API
            self.stats_text.config(state="normal")
            self.stats_text.delete("1.0", tk.END)
            self.stats_text.insert("1.0", f"Tokens: {total_tokens:,} | Requisições: {total_requests:,} | Custo: ${estimated_cost:.4f} USD")
            self.stats_text.config(state="disabled")
            
            # Atualizar label no dashboard
            self.api_usage_label.config(text=f"{total_tokens:,}")
            
            # Atualizar status da API
            self.update_api_stats()
            
        except Exception as e:
            print(f"Erro ao atualizar dashboard: {str(e)}")
    
    def update_api_stats(self):
        """Atualiza as estatísticas de API na barra de status"""
        try:
            # Obter estatísticas de uso
            usage_stats = self.modules["ai_integration"].get_usage_stats()
            
            # Formatar estatísticas
            total_tokens = usage_stats.get("total_tokens", 0)
            
            # Calcular custo estimado (aproximadamente $0.0015 por 1K tokens para gpt-3.5-turbo)
            estimated_cost = (total_tokens / 1000) * 0.0015
            
            # Atualizar labels
            self.api_tokens_label.config(text=f"Tokens: {total_tokens:,}")
            self.api_cost_label.config(text=f"Custo: ${estimated_cost:.2f}")
            
        except Exception as e:
            print(f"Erro ao atualizar estatísticas de API: {str(e)}")
    
    def update_api_stats_display(self):
        """Atualiza o display de estatísticas de API na aba de configurações"""
        try:
            # Obter estatísticas de uso
            usage_stats = self.modules["ai_integration"].get_usage_stats()
            
            # Formatar estatísticas
            total_tokens = usage_stats.get("total_tokens", 0)
            total_requests = usage_stats.get("total_requests", 0)
            
            # Calcular custo estimado (aproximadamente $0.0015 por 1K tokens para gpt-3.5-turbo)
            estimated_cost = (total_tokens / 1000) * 0.0015
            
            # Atualizar texto
            self.stats_text.config(state="normal")
            self.stats_text.delete("1.0", tk.END)
            self.stats_text.insert("1.0", f"Tokens: {total_tokens:,} | Requisições: {total_requests:,} | Custo: ${estimated_cost:.4f} USD")
            self.stats_text.config(state="disabled")
            
        except Exception as e:
            print(f"Erro ao atualizar display de estatísticas de API: {str(e)}")
    
    def export_stats(self):
        """Exporta as estatísticas de uso para um arquivo"""
        try:
            # Obter estatísticas de uso
            usage_stats = self.modules["ai_integration"].get_usage_stats()
            
            # Solicitar local para salvar
            filepath = filedialog.asksaveasfilename(
                title="Exportar Estatísticas",
                defaultextension=".json",
                filetypes=[
                    ("Arquivo JSON", "*.json"),
                    ("Todos os Arquivos", "*.*")
                ]
            )
            
            if not filepath:
                return
            
            # Salvar estatísticas
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(usage_stats, f, indent=4)
            
            messagebox.showinfo("Sucesso", f"Estatísticas exportadas com sucesso para:\n{filepath}")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar estatísticas: {str(e)}")
    
    def clear_stats(self):
        """Limpa as estatísticas de uso"""
        if messagebox.askyesno("Limpar Estatísticas", "Tem certeza que deseja limpar todas as estatísticas de uso? Esta ação não pode ser desfeita."):
            try:
                # Limpar estatísticas
                self.modules["ai_integration"].reset_usage_stats()
                
                # Atualizar dashboard
                self.update_dashboard()
                
                messagebox.showinfo("Sucesso", "Estatísticas de uso foram limpas.")
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao limpar estatísticas: {str(e)}")

def main():
    """Função principal da aplicação"""
    # Criar janela principal com tema escuro
    root = ttk.Window(themename="darkly")
    
    # Inicializar aplicação
    app = CypressGenProApp(root)
    
    # Iniciar loop principal
    root.mainloop()

if __name__ == "__main__":
    main()
