"""
Módulo para interface de configurações do sistema.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import json
import os
import threading
import queue
from tkinter import messagebox, filedialog

from modules.settings import SettingsManager

class Settings:
    """
    Interface para gerenciamento de configurações do sistema.
    """
    
    def __init__(self, parent, app):
        """
        Inicializa a interface de configurações.
        
        Args:
            parent: Frame pai onde o módulo será exibido
            app: Referência à aplicação principal
        """
        self.parent = parent
        self.app = app
        self.config = app.config
        
        # Inicializar gerenciador de configurações
        self.settings_manager = SettingsManager()
        
        # Carregar configurações
        self.settings = self.settings_manager.load_settings()
        
        # Variáveis de estado
        self.api_key_var = tk.StringVar(value=self.settings.get("api_key", ""))
        self.model_var = tk.StringVar(value=self.settings.get("ai_edit_model", "gpt-3.5-turbo"))
        self.theme_var = tk.StringVar(value=self.settings.get("theme", "darkly"))
        self.timeout_var = tk.StringVar(value=str(self.settings.get("default_timeout", 5000)))
        self.use_typescript_var = tk.BooleanVar(value=self.settings.get("use_typescript", False))
        self.capture_network_var = tk.BooleanVar(value=self.settings.get("capture_network", True))
        
        # Criar componentes da interface
        self.create_widgets()
        
        # Atualizar dashboard
        self.update_dashboard()
    
    def create_widgets(self):
        """Cria os widgets da interface de configurações"""
        self.frame = ttk.Frame(self.parent)
        
        # Título
        ttk.Label(
            self.frame, 
            text="Configurações", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Notebook para abas
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Aba de configurações gerais
        self.general_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.general_tab, text="Geral")
        
        # Aba de configurações de API
        self.api_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.api_tab, text="API")
        
        # Aba de configurações de seletores
        self.selectors_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.selectors_tab, text="Seletores")
        
        # Aba de dashboard
        self.dashboard_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.dashboard_tab, text="Dashboard")
        
        # Configurar aba geral
        self.setup_general_tab()
        
        # Configurar aba de API
        self.setup_api_tab()
        
        # Configurar aba de seletores
        self.setup_selectors_tab()
        
        # Configurar aba de dashboard
        self.setup_dashboard_tab()
        
        # Barra de botões inferior
        self.button_frame = ttk.Frame(self.frame, padding=10)
        self.button_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=10)
        
        # Botões de ação
        self.save_button = ttk.Button(
            self.button_frame,
            text="Salvar Configurações",
            bootstyle="success",
            command=self.save_settings
        )
        self.save_button.pack(side=tk.RIGHT, padx=5)
        
        self.reset_button = ttk.Button(
            self.button_frame,
            text="Restaurar Padrões",
            bootstyle="warning",
            command=self.reset_settings
        )
        self.reset_button.pack(side=tk.RIGHT, padx=5)
    
    def setup_general_tab(self):
        """Configura a aba de configurações gerais"""
        # Frame para tema
        theme_frame = ttk.LabelFrame(self.general_tab, text="Tema", padding=10)
        theme_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            theme_frame, 
            text="Tema da Interface:"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        theme_combo = ttk.Combobox(
            theme_frame, 
            textvariable=self.theme_var,
            values=["darkly", "superhero", "cyborg", "vapor", "solar"],
            state="readonly",
            width=15
        )
        theme_combo.pack(side=tk.LEFT)
        
        ttk.Label(
            theme_frame, 
            text="(Requer reiniciar a aplicação)"
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Frame para timeout
        timeout_frame = ttk.LabelFrame(self.general_tab, text="Timeout", padding=10)
        timeout_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            timeout_frame, 
            text="Timeout Padrão (ms):"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        timeout_entry = ttk.Entry(
            timeout_frame, 
            textvariable=self.timeout_var,
            width=10
        )
        timeout_entry.pack(side=tk.LEFT)
        
        # Frame para opções de teste
        test_frame = ttk.LabelFrame(self.general_tab, text="Opções de Teste", padding=10)
        test_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Checkbutton(
            test_frame,
            text="Usar TypeScript",
            variable=self.use_typescript_var
        ).pack(anchor=tk.W)
        
        ttk.Checkbutton(
            test_frame,
            text="Capturar Requisições de Rede",
            variable=self.capture_network_var
        ).pack(anchor=tk.W)
    
    def setup_api_tab(self):
        """Configura a aba de configurações de API"""
        # Frame para chave da API
        api_key_frame = ttk.LabelFrame(self.api_tab, text="Chave da API", padding=10)
        api_key_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            api_key_frame, 
            text="Chave da API OpenAI:"
        ).pack(anchor=tk.W, pady=(0, 5))
        
        api_key_entry = ttk.Entry(
            api_key_frame, 
            textvariable=self.api_key_var,
            width=50,
            show="*"
        )
        api_key_entry.pack(fill=tk.X)
        
        # Frame para modelo
        model_frame = ttk.LabelFrame(self.api_tab, text="Modelo", padding=10)
        model_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            model_frame, 
            text="Modelo da API:"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        model_combo = ttk.Combobox(
            model_frame, 
            textvariable=self.model_var,
            values=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
            state="readonly",
            width=15
        )
        model_combo.pack(side=tk.LEFT)
        
        # Frame para estatísticas
        stats_frame = ttk.LabelFrame(self.api_tab, text="Estatísticas de Uso", padding=10)
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
    
    def setup_selectors_tab(self):
        """Configura a aba de configurações de seletores"""
        # Frame para prioridade de seletores
        priority_frame = ttk.LabelFrame(self.selectors_tab, text="Prioridade de Seletores", padding=10)
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
        selector_priority = self.settings.get("selector_priority", [])
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
        
        # Frame para habilitar/desabilitar seletores
        enable_frame = ttk.LabelFrame(self.selectors_tab, text="Habilitar/Desabilitar Seletores", padding=10)
        enable_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Criar checkboxes para cada seletor
        self.selector_vars = {}
        selector_enabled = self.settings.get("selector_enabled", {})
        
        for i, selector in enumerate(selector_priority):
            var = tk.BooleanVar(value=selector_enabled.get(selector, True))
            self.selector_vars[selector] = var
            
            ttk.Checkbutton(
                enable_frame,
                text=selector,
                variable=var
            ).grid(row=i // 3, column=i % 3, sticky=tk.W, padx=10, pady=2)
    
    def setup_dashboard_tab(self):
        """Configura a aba de dashboard"""
        # Frame para estatísticas de uso
        usage_frame = ttk.LabelFrame(self.dashboard_tab, text="Estatísticas de Uso da API", padding=10)
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
        actions_frame = ttk.Frame(self.dashboard_tab)
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
    
    def show(self):
        """Exibe o módulo de configurações"""
        self.frame.pack(fill=tk.BOTH, expand=True)
    
    def hide(self):
        """Oculta o módulo de configurações"""
        self.frame.pack_forget()
    
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
            self.settings["api_key"] = self.api_key_var.get()
            self.settings["ai_edit_model"] = self.model_var.get()
            self.settings["theme"] = self.theme_var.get()
            self.settings["default_timeout"] = int(self.timeout_var.get())
            self.settings["use_typescript"] = self.use_typescript_var.get()
            self.settings["capture_network"] = self.capture_network_var.get()
            
            # Atualizar prioridade de seletores
            selector_priority = []
            for i in range(self.selectors_listbox.size()):
                selector_priority.append(self.selectors_listbox.get(i))
            
            self.settings["selector_priority"] = selector_priority
            
            # Atualizar seletores habilitados
            selector_enabled = {}
            for selector, var in self.selector_vars.items():
                selector_enabled[selector] = var.get()
            
            self.settings["selector_enabled"] = selector_enabled
            
            # Salvar configurações
            success = self.settings_manager.save_settings(self.settings)
            
            if success:
                messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!")
                
                # Atualizar configurações da aplicação
                self.app.config["api_key"] = self.api_key_var.get()
                self.app.config["model"] = self.model_var.get()
                self.app.config["theme"] = self.theme_var.get()
                self.app.config["selector_priority"] = selector_priority
                self.app.config["selector_enabled"] = selector_enabled
                self.app.config["capture_network"] = self.capture_network_var.get()
                
                # Salvar configurações da aplicação
                self.app.save_config()
            else:
                messagebox.showerror("Erro", "Erro ao salvar configurações.")
                
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {str(e)}")
    
    def reset_settings(self):
        """Restaura as configurações padrão"""
        if messagebox.askyesno("Restaurar Padrões", "Tem certeza que deseja restaurar todas as configurações para os valores padrão?"):
            # Obter configurações padrão
            default_settings = self.settings_manager.get_default_settings()
            
            # Atualizar interface
            self.api_key_var.set(default_settings.get("api_key", ""))
            self.model_var.set(default_settings.get("ai_edit_model", "gpt-3.5-turbo"))
            self.theme_var.set(default_settings.get("theme", "darkly"))
            self.timeout_var.set(str(default_settings.get("default_timeout", 5000)))
            self.use_typescript_var.set(default_settings.get("use_typescript", False))
            self.capture_network_var.set(default_settings.get("capture_network", True))
            
            # Atualizar lista de seletores
            self.selectors_listbox.delete(0, tk.END)
            for selector in default_settings.get("selector_priority", []):
                self.selectors_listbox.insert(tk.END, selector)
            
            # Atualizar checkboxes de seletores
            selector_enabled = default_settings.get("selector_enabled", {})
            for selector, var in self.selector_vars.items():
                var.set(selector_enabled.get(selector, True))
            
            # Atualizar configurações
            self.settings = default_settings
            
            messagebox.showinfo("Sucesso", "Configurações restauradas para os valores padrão.")
    
    def update_dashboard(self):
        """Atualiza o dashboard com estatísticas de uso"""
        try:
            # Obter estatísticas de uso
            usage_stats = self.app.ai_integration.get_usage_stats()
            
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
                import datetime
                last_request_time = datetime.datetime.fromtimestamp(last_request).strftime("%d/%m/%Y %H:%M:%S")
                stats_text += f"Última Requisição: {last_request_time}\n"
            else:
                stats_text += "Última Requisição: Nunca\n"
            
            stats_text += f"\nCusto Estimado: ${estimated_cost:.4f} USD\n"
            stats_text += f"\nReferência: {self.settings.get('cost_pattern', '1,385 requests(6,024,231 tokens) = $6.94(dollar)')}"
            
            self.dashboard_text.insert("1.0", stats_text)
            self.dashboard_text.config(state="disabled")
            
            # Atualizar texto de estatísticas na aba de API
            self.stats_text.config(state="normal")
            self.stats_text.delete("1.0", tk.END)
            self.stats_text.insert("1.0", f"Tokens: {total_tokens:,} | Requisições: {total_requests:,} | Custo: ${estimated_cost:.4f} USD")
            self.stats_text.config(state="disabled")
            
        except Exception as e:
            print(f"Erro ao atualizar dashboard: {str(e)}")
    
    def export_stats(self):
        """Exporta as estatísticas de uso para um arquivo"""
        try:
            # Obter estatísticas de uso
            usage_stats = self.app.ai_integration.get_usage_stats()
            
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
                self.app.ai_integration.usage_stats = {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_requests": 0,
                    "last_request": None
                }
                
                # Salvar estatísticas
                self.app.ai_integration.save_usage_stats()
                
                # Atualizar dashboard
                self.update_dashboard()
                
                messagebox.showinfo("Sucesso", "Estatísticas de uso foram limpas.")
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao limpar estatísticas: {str(e)}")
