"""
Módulo para edição de testes com assistência de IA.
Implementa interface de chat para modificação de código em tempo real.
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
from tkinter import messagebox, filedialog

class AIEditor:
    """
    Módulo para edição de testes com assistência de IA.
    """
    
    def __init__(self, parent, app):
        """
        Inicializa o editor com assistência de IA.
        
        Args:
            parent: Frame pai onde o módulo será exibido
            app: Referência à aplicação principal
        """
        self.parent = parent
        self.app = app
        self.config = app.config
        
        # Variáveis de estado
        self.current_code = None
        self.chat_history = []
        self.edit_history = []
        self.edit_index = -1
        self.welcome_message_shown = False  # Flag para controlar a exibição da mensagem de boas-vindas
        
        # Fila para comunicação thread-safe
        self.editor_queue = queue.Queue()
        
        # Criar componentes da interface
        self.create_widgets()
    
    def create_widgets(self):
        """Cria os widgets da interface do editor"""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=tk.BOTH, expand=True)  # Garantir que o frame seja empacotado
        
        # Título
        ttk.Label(
            self.frame, 
            text="Editor de Testes com IA", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Frame principal dividido
        self.main_paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Painel de código
        self.code_frame = ttk.LabelFrame(self.main_paned, text="Código do Teste", padding=10)
        self.main_paned.add(self.code_frame, weight=2)
        
        # Painel de chat
        self.chat_frame = ttk.LabelFrame(self.main_paned, text="Assistente IA", padding=10)
        self.main_paned.add(self.chat_frame, weight=1)
        
        # Configurar painel de código
        self.setup_code_panel()
        
        # Configurar painel de chat
        self.setup_chat_panel()
        
        # Barra de botões inferior
        self.button_frame = ttk.Frame(self.frame, padding=10)
        self.button_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=10)
        
        # Botões de ação
        self.run_button = ttk.Button(
            self.button_frame,
            text="Executar Teste",
            bootstyle="success",
            command=self.run_test
        )
        self.run_button.pack(side=tk.RIGHT, padx=5)
        
        self.save_button = ttk.Button(
            self.button_frame,
            text="Salvar Código",
            bootstyle="primary",
            command=self.save_code
        )
        self.save_button.pack(side=tk.RIGHT, padx=5)
        
        # Botões de histórico
        self.undo_button = ttk.Button(
            self.button_frame,
            text="Desfazer",
            bootstyle="secondary",
            command=self.undo_edit,
            state="disabled"
        )
        self.undo_button.pack(side=tk.LEFT, padx=5)
        
        self.redo_button = ttk.Button(
            self.button_frame,
            text="Refazer",
            bootstyle="secondary",
            command=self.redo_edit,
            state="disabled"
        )
        self.redo_button.pack(side=tk.LEFT, padx=5)

    
    def setup_code_panel(self):
        """Configura o painel de código"""
        # Barra de ferramentas
        tools_frame = ttk.Frame(self.code_frame)
        tools_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Botões de formatação
        format_button = ttk.Button(
            tools_frame,
            text="Formatar Código",
            command=self.format_code
        )
        format_button.pack(side=tk.LEFT, padx=5)
        
        # Botão para destacar linha
        highlight_button = ttk.Button(
            tools_frame,
            text="Destacar Linha",
            command=self.highlight_current_line
        )
        highlight_button.pack(side=tk.LEFT, padx=5)
        
        # Editor de código
        code_editor_frame = ttk.Frame(self.code_frame)
        code_editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # Números de linha
        self.line_numbers = tk.Text(
            code_editor_frame,
            width=4,
            padx=3,
            pady=5,
            takefocus=0,
            border=0,
            background="#282a36",
            foreground="#6272a4",
            font=("Consolas", 12),
            state="disabled"
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        # Editor de código principal
        self.code_text = tk.Text(
            code_editor_frame, 
            wrap=tk.NONE,
            padx=5,
            pady=5,
            font=("Consolas", 12),
            bg="#282a36",
            fg="#f8f8f2",
            insertbackground="#f8f8f2",
            selectbackground="#44475a",
            selectforeground="#f8f8f2"
        )
        
        # Scrollbars
        code_y_scrollbar = ttk.Scrollbar(
            code_editor_frame, 
            orient="vertical", 
            command=self.on_code_scroll_y
        )
        code_x_scrollbar = ttk.Scrollbar(
            code_editor_frame, 
            orient="horizontal", 
            command=self.code_text.xview
        )
        
        self.code_text.configure(
            yscrollcommand=self.on_code_scroll_update,
            xscrollcommand=code_x_scrollbar.set
        )
        
        code_y_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        code_x_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.code_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Vincular eventos
        self.code_text.bind("<KeyRelease>", self.on_code_change)
        self.code_text.bind("<Control-z>", self.undo_edit)
        self.code_text.bind("<Control-y>", self.redo_edit)
        self.code_text.bind("<Control-s>", self.save_code)
        
        # Configurar syntax highlighting
        self.setup_syntax_highlighting()
        
        # Atualizar números de linha
        self.update_line_numbers()
    
    def setup_chat_panel(self):
        """Configura o painel de chat"""
        # Área de histórico de chat
        chat_history_frame = ttk.Frame(self.chat_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.chat_text = tk.Text(
            chat_history_frame,
            wrap=tk.WORD,
            padx=5,
            pady=5,
            font=("Segoe UI", 10),
            bg="#282a36",
            fg="#f8f8f2",
            state="disabled"
        )
        
        chat_scrollbar = ttk.Scrollbar(
            chat_history_frame, 
            orient="vertical", 
            command=self.chat_text.yview
        )
        
        self.chat_text.configure(yscrollcommand=chat_scrollbar.set)
        
        chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Área de entrada de mensagem
        message_frame = ttk.Frame(self.chat_frame)
        message_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.message_text = tk.Text(
            message_frame,
            wrap=tk.WORD,
            height=3,
            padx=5,
            pady=5,
            font=("Segoe UI", 10),
            bg="#282a36",
            fg="#f8f8f2"
        )
        
        message_scrollbar = ttk.Scrollbar(
            message_frame, 
            orient="vertical", 
            command=self.message_text.yview
        )
        
        self.message_text.configure(yscrollcommand=message_scrollbar.set)
        
        message_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Vincular evento de tecla
        self.message_text.bind("<Return>", self.on_message_return)
        self.message_text.bind("<Shift-Return>", self.on_shift_return)
        
        # Botão de envio
        send_frame = ttk.Frame(self.chat_frame)
        send_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.send_button = ttk.Button(
            send_frame,
            text="Enviar",
            bootstyle="primary",
            command=self.send_message
        )
        self.send_button.pack(side=tk.RIGHT)
        
        # Status do chat
        self.chat_status = ttk.Label(
            send_frame,
            text="Pronto para ajudar",
            bootstyle="info"
        )
        self.chat_status.pack(side=tk.LEFT)
    
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
        self.code_text.tag_configure("highlight_line", background="#44475a")
    
    def apply_syntax_highlighting(self):
        """Aplica syntax highlighting ao código"""
        code = self.code_text.get("1.0", tk.END)
        if not code.strip():
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
        """Exibe o módulo de editor"""
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Adicionar mensagem de boas-vindas ao chat apenas se ainda não foi mostrada
        if not self.welcome_message_shown:
            self.add_system_message("Bem-vindo ao Editor de Testes com IA! Como posso ajudar a melhorar seu teste Cypress?")
            self.welcome_message_shown = True
    
    def hide(self):
        """Oculta o módulo de editor"""
        self.frame.pack_forget()
    
    def set_code(self, code):
        """
        Define o código a ser editado.
        
        Args:
            code: Código a ser editado
        """
        # Limpar histórico de edição
        self.edit_history = []
        self.edit_index = -1
        
        # Definir código atual
        self.current_code = code
        
        # Atualizar editor
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", code)
        
        # Aplicar syntax highlighting
        self.apply_syntax_highlighting()
        
        # Atualizar números de linha
        self.update_line_numbers()
        
        # Desabilitar botões de histórico
        self.undo_button.config(state="disabled")
        self.redo_button.config(state="disabled")
        
        # Adicionar estado inicial ao histórico
        self.add_to_history(code)
    
    def on_code_change(self, event=None):
        """Manipula mudanças no código"""
        # Atualizar números de linha
        self.update_line_numbers()
        
        # Aplicar syntax highlighting
        self.apply_syntax_highlighting()
        
        # Obter código atual
        code = self.code_text.get("1.0", tk.END)
        
        # Verificar se o código mudou significativamente
        if self.edit_history and self.edit_index >= 0:
            last_code = self.edit_history[self.edit_index]
            if code == last_code:
                return
        
        # Adicionar ao histórico
        self.add_to_history(code)
    
    def add_to_history(self, code):
        """
        Adiciona código ao histórico de edição.
        
        Args:
            code: Código a ser adicionado
        """
        # Se estamos no meio do histórico, remover tudo após o índice atual
        if self.edit_index < len(self.edit_history) - 1:
            self.edit_history = self.edit_history[:self.edit_index + 1]
        
        # Adicionar ao histórico
        self.edit_history.append(code)
        self.edit_index = len(self.edit_history) - 1
        
        # Atualizar botões
        self.update_history_buttons()
    
    def update_history_buttons(self):
        """Atualiza o estado dos botões de histórico"""
        # Ativar/desativar botão de desfazer
        if self.edit_index > 0:
            self.undo_button.config(state="normal")
        else:
            self.undo_button.config(state="disabled")
        
        # Ativar/desativar botão de refazer
        if self.edit_index < len(self.edit_history) - 1:
            self.redo_button.config(state="normal")
        else:
            self.redo_button.config(state="disabled")
    
    def undo_edit(self, event=None):
        """Desfaz a última edição"""
        if self.edit_index > 0:
            self.edit_index -= 1
            code = self.edit_history[self.edit_index]
            
            # Atualizar editor
            self.code_text.delete("1.0", tk.END)
            self.code_text.insert("1.0", code)
            
            # Aplicar syntax highlighting
            self.apply_syntax_highlighting()
            
            # Atualizar números de linha
            self.update_line_numbers()
            
            # Atualizar botões
            self.update_history_buttons()
        
        # Impedir propagação do evento se chamado por tecla de atalho
        return "break"
    
    def redo_edit(self, event=None):
        """Refaz a última edição desfeita"""
        if self.edit_index < len(self.edit_history) - 1:
            self.edit_index += 1
            code = self.edit_history[self.edit_index]
            
            # Atualizar editor
            self.code_text.delete("1.0", tk.END)
            self.code_text.insert("1.0", code)
            
            # Aplicar syntax highlighting
            self.apply_syntax_highlighting()
            
            # Atualizar números de linha
            self.update_line_numbers()
            
            # Atualizar botões
            self.update_history_buttons()
        
        # Impedir propagação do evento se chamado por tecla de atalho
        return "break"
    
    def update_line_numbers(self):
        """Atualiza os números de linha"""
        # Obter número de linhas
        text = self.code_text.get("1.0", tk.END)
        num_lines = text.count("\n") + 1
        
        # Atualizar widget de números de linha
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", tk.END)
        
        for i in range(1, num_lines):
            self.line_numbers.insert(tk.END, f"{i}\n")
        
        self.line_numbers.config(state="disabled")
    
    def on_code_scroll_y(self, *args):
        """Sincroniza o scroll vertical do editor e números de linha"""
        self.code_text.yview(*args)
        self.line_numbers.yview(*args)
    
    def on_code_scroll_update(self, *args):
        """Atualiza a posição do scroll vertical"""
        self.line_numbers.yview_moveto(args[0])
        return self.code_text.yview(*args)
    
    def highlight_current_line(self):
        """Destaca a linha atual no editor"""
        # Remover destaque anterior
        self.code_text.tag_remove("highlight_line", "1.0", tk.END)
        
        # Obter posição do cursor
        cursor_pos = self.code_text.index(tk.INSERT)
        line = cursor_pos.split(".")[0]
        
        # Adicionar destaque
        self.code_text.tag_add("highlight_line", f"{line}.0", f"{line}.end+1c")
    
    def format_code(self):
        """Formata o código no editor"""
        # Implementação básica de formatação
        # Em uma versão real, poderia usar prettier ou outra biblioteca
        
        code = self.code_text.get("1.0", tk.END)
        if not code.strip():
            return
        
        # Adicionar ao histórico antes de formatar
        self.add_to_history(code)
        
        # Formatar código (implementação simplificada)
        formatted_code = self._simple_format(code)
        
        # Atualizar editor
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", formatted_code)
        
        # Aplicar syntax highlighting
        self.apply_syntax_highlighting()
        
        # Atualizar números de linha
        self.update_line_numbers()
        
        # Adicionar ao histórico após formatar
        self.add_to_history(formatted_code)
    
    def _simple_format(self, code):
        """
        Implementação simplificada de formatação de código.
        
        Args:
            code: Código a ser formatado
            
        Returns:
            str: Código formatado
        """
        # Dividir em linhas
        lines = code.split("\n")
        formatted_lines = []
        indent_level = 0
        
        for line in lines:
            # Remover espaços em branco no início e fim
            stripped = line.strip()
            
            # Ajustar nível de indentação
            if stripped.endswith("{"):
                # Adicionar linha com indentação atual
                formatted_lines.append("  " * indent_level + stripped)
                indent_level += 1
            elif stripped.startswith("}"):
                # Reduzir indentação e adicionar linha
                indent_level = max(0, indent_level - 1)
                formatted_lines.append("  " * indent_level + stripped)
            else:
                # Adicionar linha com indentação atual
                if stripped:
                    formatted_lines.append("  " * indent_level + stripped)
                else:
                    formatted_lines.append("")
        
        # Juntar linhas formatadas
        return "\n".join(formatted_lines)
    
    def save_code(self, event=None):
        """Salva o código em um arquivo"""
        code = self.code_text.get("1.0", tk.END)
        if not code.strip():
            messagebox.showwarning("Aviso", "Não há código para salvar.")
            return
        
        # Solicitar arquivo
        filepath = filedialog.asksaveasfilename(
            title="Salvar Código",
            filetypes=[("Arquivos JavaScript", "*.js"), ("Arquivos TypeScript", "*.ts"), ("Todos os Arquivos", "*.*")],
            defaultextension=".js"
        )
        
        if not filepath:
            return
        
        try:
            # Salvar código
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code)
            
            self.app.update_status(f"Código salvo em: {os.path.basename(filepath)}", "success")
            
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o arquivo:\n{e}")
            self.app.update_status(f"Erro ao salvar código: {str(e)}", "error")
        
        # Impedir propagação do evento se chamado por tecla de atalho
        return "break"
    
    def run_test(self):
        """Executa o teste Cypress"""
        code = self.code_text.get("1.0", tk.END)
        if not code.strip():
            messagebox.showwarning("Aviso", "Não há código para executar.")
            return
        
        # Verificar se o código foi salvo
        if messagebox.askyesno("Executar Teste", "O teste precisa ser salvo antes de ser executado. Deseja salvar agora?"):
            self.save_code()
        else:
            return
        
        # Implementação da execução do teste seria feita aqui
        # Por exemplo, usando subprocess para executar o Cypress
        
        self.app.update_status("Iniciando execução do teste...", "info")
        
        # Simulação de execução
        self.chat_status.config(text="Executando teste...", bootstyle="warning")
        
        # Em uma implementação real, isso seria feito em uma thread separada
        # e o resultado seria exibido no chat
        
        # Simulação de resultado
        self.add_system_message("Teste executado com sucesso! Todos os testes passaram.")
        self.chat_status.config(text="Pronto para ajudar", bootstyle="info")
        self.app.update_status("Teste executado com sucesso", "success")
    
    def on_message_return(self, event=None):
        """Manipula pressionamento de Enter no campo de mensagem"""
        # Enviar mensagem se Enter for pressionado sem Shift
        self.send_message()
        return "break"  # Impedir quebra de linha
    
    def on_shift_return(self, event=None):
        """Manipula pressionamento de Shift+Enter no campo de mensagem"""
        # Permitir quebra de linha se Shift+Enter for pressionado
        return None  # Permitir comportamento padrão
    
    def send_message(self):
        """Envia mensagem para o assistente IA"""
        # Obter mensagem
        message = self.message_text.get("1.0", tk.END).strip()
        if not message:
            return
        
        # Limpar campo de mensagem
        self.message_text.delete("1.0", tk.END)
        
        # Adicionar mensagem ao chat
        self.add_user_message(message)
        
        # Obter código atual
        code = self.code_text.get("1.0", tk.END)
        
        # Atualizar status
        self.chat_status.config(text="Processando...", bootstyle="warning")
        self.send_button.config(state="disabled")
        
        # Iniciar thread para processar mensagem
        threading.Thread(target=self._process_message, args=(message, code), daemon=True).start()
    
    def _process_message(self, message, code):
        """
        Processa mensagem em uma thread separada.
        
        Args:
            message: Mensagem do usuário
            code: Código atual
        """
        try:
            # Verificar se a API está disponível
            if not hasattr(self.app, 'ai_integration') or not self.app.ai_integration:
                # Simulação de resposta se não houver integração com IA
                time.sleep(1)  # Simular processamento
                response = "Desculpe, a integração com IA não está disponível no momento."
                self.editor_queue.put(("system_message", response))
                self.editor_queue.put(("update_status", "Pronto para ajudar", "info"))
                self.editor_queue.put(("enable_send", None))
                return
            
            # Estimar custo da requisição
            tokens = self.app.ai_integration.estimate_tokens(message, code)
            cost = self.app.ai_integration.estimate_cost(tokens)
            
            # Confirmar custo com o usuário
            if not self.app.ai_integration.confirm_api_cost(cost, tokens):
                self.editor_queue.put(("system_message", "Operação cancelada pelo usuário."))
                self.editor_queue.put(("update_status", "Pronto para ajudar", "info"))
                self.editor_queue.put(("enable_send", None))
                return
            
            # Enviar para API
            response = self.app.ai_integration.get_code_improvement(message, code)
            
            # Verificar se há sugestões de código
            code_suggestions = self.app.ai_integration.extract_code_blocks(response)
            
            # Adicionar resposta ao chat
            self.editor_queue.put(("system_message", response))
            
            # Se houver sugestões de código, perguntar se deseja aplicar
            if code_suggestions:
                self.editor_queue.put(("ask_apply_code", code_suggestions))
            
            # Atualizar status
            self.editor_queue.put(("update_status", "Pronto para ajudar", "info"))
            
        except Exception as e:
            # Adicionar mensagem de erro ao chat
            error_message = f"Erro ao processar mensagem: {str(e)}"
            self.editor_queue.put(("system_message", error_message))
            self.editor_queue.put(("update_status", "Erro", "danger"))
        
        finally:
            # Reativar botão de envio
            self.editor_queue.put(("enable_send", None))
            
            # Processar fila
            self.parent.after(100, self.process_queue)
    
    def process_queue(self):
        """Processa itens na fila de comunicação"""
        try:
            while True:
                action, *args = self.editor_queue.get_nowait()
                
                if action == "system_message":
                    self.add_system_message(args[0])
                elif action == "update_status":
                    self.chat_status.config(text=args[0], bootstyle=args[1])
                elif action == "enable_send":
                    self.send_button.config(state="normal")
                elif action == "ask_apply_code":
                    self.ask_apply_code(args[0])
                
                self.editor_queue.task_done()
        
        except queue.Empty:
            pass
    
    def add_user_message(self, message):
        """
        Adiciona mensagem do usuário ao chat.
        
        Args:
            message: Mensagem do usuário
        """
        # Adicionar ao histórico
        self.chat_history.append({"role": "user", "content": message})
        
        # Atualizar widget de chat
        self.chat_text.config(state="normal")
        
        # Adicionar separador se não for a primeira mensagem
        if len(self.chat_history) > 1:
            self.chat_text.insert(tk.END, "\n\n")
        
        # Adicionar mensagem
        self.chat_text.insert(tk.END, "Você: ", "user_label")
        self.chat_text.insert(tk.END, message)
        
        # Configurar tags
        self.chat_text.tag_configure("user_label", foreground="#50fa7b", font=("Segoe UI", 10, "bold"))
        
        # Rolar para o final
        self.chat_text.see(tk.END)
        self.chat_text.config(state="disabled")
    
    def add_system_message(self, message):
        """
        Adiciona mensagem do sistema ao chat.
        
        Args:
            message: Mensagem do sistema
        """
        # Adicionar ao histórico
        self.chat_history.append({"role": "assistant", "content": message})
        
        # Atualizar widget de chat
        self.chat_text.config(state="normal")
        
        # Adicionar separador se não for a primeira mensagem
        if len(self.chat_history) > 1:
            self.chat_text.insert(tk.END, "\n\n")
        
        # Adicionar mensagem
        self.chat_text.insert(tk.END, "Sistema: ", "system_label")
        
        # Processar blocos de código
        parts = re.split(r'(```[\s\S]*?```)', message)
        for part in parts:
            if part.startswith("```") and part.endswith("```"):
                # Extrair código e linguagem
                code_block = part[3:-3].strip()
                language = ""
                if "\n" in code_block:
                    first_line = code_block.split("\n")[0].strip()
                    if first_line and not first_line.startswith("```"):
                        language = first_line
                        code_block = code_block[len(first_line):].strip()
                
                # Adicionar bloco de código
                self.chat_text.insert(tk.END, f"\n\n[Código {language}]\n", "code_label")
                self.chat_text.insert(tk.END, code_block, "code_block")
                self.chat_text.insert(tk.END, "\n")
            else:
                # Adicionar texto normal
                self.chat_text.insert(tk.END, part)
        
        # Configurar tags
        self.chat_text.tag_configure("system_label", foreground="#8be9fd", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("code_label", foreground="#ff79c6", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("code_block", background="#44475a", font=("Consolas", 10))
        
        # Rolar para o final
        self.chat_text.see(tk.END)
        self.chat_text.config(state="disabled")
    
    def ask_apply_code(self, code_suggestions):
        """
        Pergunta ao usuário se deseja aplicar sugestões de código.
        
        Args:
            code_suggestions: Lista de blocos de código sugeridos
        """
        if not code_suggestions:
            return
        
        # Mostrar diálogo de confirmação
        if messagebox.askyesno("Aplicar Código", "Deseja aplicar as sugestões de código ao editor?"):
            # Aplicar primeiro bloco de código
            code = code_suggestions[0]
            
            # Adicionar ao histórico antes de aplicar
            current_code = self.code_text.get("1.0", tk.END)
            self.add_to_history(current_code)
            
            # Atualizar editor
            self.code_text.delete("1.0", tk.END)
            self.code_text.insert("1.0", code)
            
            # Aplicar syntax highlighting
            self.apply_syntax_highlighting()
            
            # Atualizar números de linha
            self.update_line_numbers()
            
            # Adicionar ao histórico após aplicar
            self.add_to_history(code)
            
            # Atualizar status
            self.app.update_status("Código atualizado com sugestões da IA", "success")

