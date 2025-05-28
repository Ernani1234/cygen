"""
Módulo para captura de regras e documentação com assistência de IA.
Implementa interface para upload de arquivos e consulta à IA sobre regras de negócio.
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
import zipfile
import shutil
from datetime import datetime
from tkinter import filedialog, messagebox

class RuleCapture:
    """
    Módulo para captura de regras e documentação com assistência de IA.
    """
    
    def __init__(self, parent, app):
        """
        Inicializa o módulo de captura de regras.
        
        Args:
            parent: Frame pai onde o módulo será exibido
            app: Referência à aplicação principal
        """
        self.parent = parent
        self.app = app
        self.config = app.config
        
        # Variáveis de estado
        self.uploaded_files = []
        self.temp_files = []
        self.chat_history = []
        self.current_category = "Geral"
        self.conversations = {}  # Dicionário para armazenar conversas salvas
        
        # Criar diretórios necessários
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.temp_dir = os.path.join(self.base_dir, "temp")
        self.conversations_dir = os.path.join(self.base_dir, "conversations")
        
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.conversations_dir, exist_ok=True)
        
        # Fila para comunicação thread-safe
        self.rule_queue = queue.Queue()
        
        # Criar componentes da interface
        self.create_widgets()
        
        # Carregar conversas salvas
        try:
            self.load_conversations()
        except Exception as e:
            print(f"Erro ao carregar conversas: {str(e)}")
    
    def create_widgets(self):
        """Cria os widgets da interface do módulo"""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=tk.BOTH, expand=True)  # Garantir que o frame seja empacotado
        
        # Título
        ttk.Label(
            self.frame, 
            text="Captura de Regras", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Frame principal dividido
        self.main_paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Painel de upload e consulta
        self.upload_frame = ttk.LabelFrame(self.main_paned, text="Upload e Consulta", padding=10)
        self.main_paned.add(self.upload_frame, weight=1)
        
        # Painel de respostas
        self.response_frame = ttk.LabelFrame(self.main_paned, text="Respostas da IA", padding=10)
        self.main_paned.add(self.response_frame, weight=2)
        
        # Configurar painel de upload
        self.setup_upload_panel()
        
        # Configurar painel de respostas
        self.setup_response_panel()

    
    def setup_upload_panel(self):
        """Configura o painel de upload e consulta"""
        # Área de upload de arquivos
        upload_area = ttk.LabelFrame(self.upload_frame, text="Upload de Arquivos", padding=10)
        upload_area.pack(fill=tk.X, pady=(0, 10))
        
        # Botões de upload
        upload_buttons = ttk.Frame(upload_area)
        upload_buttons.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            upload_buttons,
            text="Upload de Arquivo",
            command=self.upload_file
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            upload_buttons,
            text="Upload de ZIP",
            command=self.upload_zip
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            upload_buttons,
            text="Limpar Arquivos",
            command=self.clear_files
        ).pack(side=tk.RIGHT, padx=5)
        
        # Lista de arquivos
        files_frame = ttk.Frame(upload_area)
        files_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.files_list = tk.Listbox(
            files_frame,
            height=8,
            selectmode=tk.EXTENDED
        )
        files_scrollbar = ttk.Scrollbar(
            files_frame, 
            orient="vertical", 
            command=self.files_list.yview
        )
        self.files_list.configure(yscrollcommand=files_scrollbar.set)
        
        self.files_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Área de consulta
        query_area = ttk.LabelFrame(self.upload_frame, text="Consulta à IA", padding=10)
        query_area.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Campo de consulta
        ttk.Label(
            query_area,
            text="Digite sua pergunta sobre os arquivos:"
        ).pack(anchor=tk.W, pady=(0, 5))
        
        self.query_text = tk.Text(
            query_area,
            height=6,
            wrap=tk.WORD,
            padx=5,
            pady=5,
            font=("Segoe UI", 10),
            bg="#282a36",
            fg="#f8f8f2"
        )
        query_scrollbar = ttk.Scrollbar(
            query_area, 
            orient="vertical", 
            command=self.query_text.yview
        )
        self.query_text.configure(yscrollcommand=query_scrollbar.set)
        
        self.query_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        query_scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        
        # Vincular evento de tecla
        self.query_text.bind("<Control-Return>", self.send_query)
        
        # Botão de envio
        send_frame = ttk.Frame(query_area)
        send_frame.pack(fill=tk.X, pady=10)
        
        self.send_button = ttk.Button(
            send_frame,
            text="Enviar Consulta",
            bootstyle="primary",
            command=self.send_query
        )
        self.send_button.pack(side=tk.RIGHT)
        
        # Status da consulta
        self.query_status = ttk.Label(
            send_frame,
            text="Pronto para consulta",
            bootstyle="info"
        )
        self.query_status.pack(side=tk.LEFT)
        
        # Área de gerenciamento de conversas
        conversation_area = ttk.LabelFrame(self.upload_frame, text="Gerenciamento de Conversas", padding=10)
        conversation_area.pack(fill=tk.X, pady=10)
        
        # Categoria da conversa
        category_frame = ttk.Frame(conversation_area)
        category_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(
            category_frame,
            text="Categoria:"
        ).pack(side=tk.LEFT)
        
        self.category_var = tk.StringVar(value="Geral")
        categories = ["Geral", "Regras de Negócio", "Validações", "Fluxos", "Documentação", "Outros"]
        category_combo = ttk.Combobox(
            category_frame,
            textvariable=self.category_var,
            values=categories,
            state="readonly",
            width=20
        )
        category_combo.pack(side=tk.LEFT, padx=5)
        
        # Botões de gerenciamento
        buttons_frame = ttk.Frame(conversation_area)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            buttons_frame,
            text="Salvar Conversa",
            command=self.save_conversation
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame,
            text="Carregar Conversa",
            command=self.load_conversation
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame,
            text="Nova Conversa",
            command=self.new_conversation
        ).pack(side=tk.RIGHT, padx=5)
    
    def setup_response_panel(self):
        """Configura o painel de respostas"""
        # Área de histórico de chat
        chat_history_frame = ttk.Frame(self.response_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.response_text = tk.Text(
            chat_history_frame,
            wrap=tk.WORD,
            padx=5,
            pady=5,
            font=("Segoe UI", 10),
            bg="#282a36",
            fg="#f8f8f2",
            state="disabled"
        )
        
        response_scrollbar = ttk.Scrollbar(
            chat_history_frame, 
            orient="vertical", 
            command=self.response_text.yview
        )
        
        self.response_text.configure(yscrollcommand=response_scrollbar.set)
        
        response_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.response_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Barra de botões de ação
        action_frame = ttk.Frame(self.response_frame)
        action_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            action_frame,
            text="Copiar",
            command=self.copy_response
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            action_frame,
            text="Regenerar",
            command=self.regenerate_response
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            action_frame,
            text="Complementar Contexto",
            command=self.complement_context
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            action_frame,
            text="Reset",
            command=self.reset_conversation
        ).pack(side=tk.RIGHT, padx=5)
    
    def show(self):
        """Exibe o módulo de captura de regras"""
        self.frame.pack(fill=tk.BOTH, expand=True)
    
    def hide(self):
        """Oculta o módulo de captura de regras"""
        self.frame.pack_forget()
    
    def upload_file(self):
        """Faz upload de um arquivo"""
        filepaths = filedialog.askopenfilenames(
            title="Selecionar Arquivos",
            filetypes=[("Todos os Arquivos", "*.*")]
        )
        
        if not filepaths:
            return
        
        for filepath in filepaths:
            # Copiar arquivo para diretório temporário
            filename = os.path.basename(filepath)
            temp_path = os.path.join(self.temp_dir, filename)
            
            try:
                shutil.copy2(filepath, temp_path)
                self.uploaded_files.append(temp_path)
                self.temp_files.append(temp_path)
                self.files_list.insert(tk.END, filename)
                
                self.app.update_status(f"Arquivo carregado: {filename}", "success")
            except Exception as e:
                messagebox.showerror("Erro de Upload", f"Não foi possível carregar o arquivo {filename}:\n{e}")
                self.app.update_status(f"Erro ao carregar arquivo: {str(e)}", "error")
    
    def upload_zip(self):
        """Faz upload e extrai um arquivo ZIP"""
        filepath = filedialog.askopenfilename(
            title="Selecionar Arquivo ZIP",
            filetypes=[("Arquivos ZIP", "*.zip"), ("Todos os Arquivos", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            # Criar diretório para extração
            zip_name = os.path.basename(filepath).replace(".zip", "")
            extract_dir = os.path.join(self.temp_dir, zip_name)
            os.makedirs(extract_dir, exist_ok=True)
            
            # Extrair arquivo
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Adicionar arquivos extraídos à lista
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.temp_dir)
                    self.uploaded_files.append(file_path)
                    self.temp_files.append(file_path)
                    self.files_list.insert(tk.END, rel_path)
            
            self.app.update_status(f"Arquivo ZIP extraído: {zip_name}", "success")
        except Exception as e:
            messagebox.showerror("Erro de Upload", f"Não foi possível extrair o arquivo ZIP:\n{e}")
            self.app.update_status(f"Erro ao extrair ZIP: {str(e)}", "error")
    
    def clear_files(self):
        """Limpa a lista de arquivos"""
        if not self.uploaded_files:
            return
        
        if messagebox.askyesno("Limpar Arquivos", "Deseja remover todos os arquivos carregados?"):
            # Limpar arquivos temporários
            for file_path in self.temp_files:
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except:
                    pass
            
            # Limpar listas
            self.uploaded_files = []
            self.temp_files = []
            self.files_list.delete(0, tk.END)
            
            self.app.update_status("Arquivos removidos", "info")
    
    def send_query(self, event=None):
        """Envia consulta para a IA"""
        # Verificar se há arquivos carregados
        if not self.uploaded_files:
            messagebox.showwarning("Aviso", "Por favor, carregue pelo menos um arquivo antes de enviar uma consulta.")
            return
        
        # Obter consulta
        query = self.query_text.get("1.0", tk.END).strip()
        if not query:
            messagebox.showwarning("Aviso", "Por favor, digite uma consulta.")
            return
        
        # Atualizar status
        self.query_status.config(text="Processando consulta...", bootstyle="warning")
        self.send_button.config(state="disabled")
        
        # Adicionar consulta ao histórico
        self.add_user_message(query)
        
        # Iniciar thread para processar consulta
        threading.Thread(target=self._process_query, args=(query,), daemon=True).start()
    
    def _process_query(self, query):
        """
        Processa consulta em uma thread separada.
        
        Args:
            query: Consulta do usuário
        """
        try:
            # Verificar se a API está disponível
            if not hasattr(self.app, 'ai_integration') or not self.app.ai_integration:
                # Simulação de resposta se não houver integração com IA
                time.sleep(1)  # Simular processamento
                response = "Desculpe, a integração com IA não está disponível no momento."
                self.rule_queue.put(("system_message", response))
                self.rule_queue.put(("update_status", "Pronto para consulta", "info"))
                self.rule_queue.put(("enable_send", None))
                return
            
            # Preparar contexto dos arquivos
            file_context = self._prepare_file_context()
            
            # Estimar custo da requisição
            tokens = self.app.ai_integration.estimate_tokens(query, file_context)
            cost = self.app.ai_integration.estimate_cost(tokens)
            
            # Confirmar custo com o usuário
            if not self.app.ai_integration.confirm_api_cost(cost, tokens):
                self.rule_queue.put(("system_message", "Operação cancelada pelo usuário."))
                self.rule_queue.put(("update_status", "Pronto para consulta", "info"))
                self.rule_queue.put(("enable_send", None))
                return
            
            # Enviar para API
            response = self.app.ai_integration.get_file_analysis(query, file_context)
            
            # Adicionar resposta ao histórico
            self.rule_queue.put(("system_message", response))
            
            # Atualizar status
            self.rule_queue.put(("update_status", "Pronto para consulta", "info"))
            
        except Exception as e:
            # Adicionar mensagem de erro ao histórico
            error_message = f"Erro ao processar consulta: {str(e)}"
            self.rule_queue.put(("system_message", error_message))
            self.rule_queue.put(("update_status", "Erro", "danger"))
        
        finally:
            # Reativar botão de envio
            self.rule_queue.put(("enable_send", None))
            
            # Processar fila
            self.parent.after(100, self.process_queue)
    
    def _prepare_file_context(self):
        """
        Prepara o contexto dos arquivos para envio à API.
        
        Returns:
            str: Contexto dos arquivos
        """
        context = []
        
        for file_path in self.uploaded_files:
            try:
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                
                # Verificar tamanho do arquivo
                if file_size > 1024 * 1024:  # 1MB
                    context.append(f"Arquivo: {filename} (muito grande para incluir conteúdo)")
                    continue
                
                # Tentar ler o arquivo como texto
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    context.append(f"Arquivo: {filename}\n\n{content}\n\n")
                except UnicodeDecodeError:
                    # Se não for um arquivo de texto, apenas mencionar
                    context.append(f"Arquivo: {filename} (arquivo binário)")
            except Exception as e:
                context.append(f"Erro ao ler arquivo {filename}: {str(e)}")
        
        return "\n".join(context)
    
    def process_queue(self):
        """Processa itens na fila de comunicação"""
        try:
            while True:
                action, *args = self.rule_queue.get_nowait()
                
                if action == "system_message":
                    self.add_system_message(args[0])
                elif action == "update_status":
                    self.query_status.config(text=args[0], bootstyle=args[1])
                elif action == "enable_send":
                    self.send_button.config(state="normal")
                
                self.rule_queue.task_done()
        
        except queue.Empty:
            pass
    
    def add_user_message(self, message):
        """
        Adiciona mensagem do usuário ao histórico.
        
        Args:
            message: Mensagem do usuário
        """
        # Adicionar ao histórico
        self.chat_history.append({"role": "user", "content": message})
        
        # Atualizar widget de resposta
        self.response_text.config(state="normal")
        
        # Adicionar separador se não for a primeira mensagem
        if len(self.chat_history) > 1:
            self.response_text.insert(tk.END, "\n\n")
        
        # Adicionar mensagem
        self.response_text.insert(tk.END, "Você: ", "user_label")
        self.response_text.insert(tk.END, message)
        
        # Configurar tags
        self.response_text.tag_configure("user_label", foreground="#50fa7b", font=("Segoe UI", 10, "bold"))
        
        # Rolar para o final
        self.response_text.see(tk.END)
        self.response_text.config(state="disabled")
    
    def add_system_message(self, message):
        """
        Adiciona mensagem do sistema ao histórico.
        
        Args:
            message: Mensagem do sistema
        """
        # Adicionar ao histórico
        self.chat_history.append({"role": "assistant", "content": message})
        
        # Atualizar widget de resposta
        self.response_text.config(state="normal")
        
        # Adicionar separador se não for a primeira mensagem
        if len(self.chat_history) > 1:
            self.response_text.insert(tk.END, "\n\n")
        
        # Adicionar mensagem
        self.response_text.insert(tk.END, "Sistema: ", "system_label")
        
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
                self.response_text.insert(tk.END, f"\n\n[Código {language}]\n", "code_label")
                self.response_text.insert(tk.END, code_block, "code_block")
                self.response_text.insert(tk.END, "\n")
            else:
                # Adicionar texto normal
                self.response_text.insert(tk.END, part)
        
        # Configurar tags
        self.response_text.tag_configure("system_label", foreground="#8be9fd", font=("Segoe UI", 10, "bold"))
        self.response_text.tag_configure("code_label", foreground="#ff79c6", font=("Segoe UI", 10, "bold"))
        self.response_text.tag_configure("code_block", background="#44475a", font=("Consolas", 10))
        
        # Rolar para o final
        self.response_text.see(tk.END)
        self.response_text.config(state="disabled")
    
    def copy_response(self):
        """Copia a última resposta para a área de transferência"""
        if not self.chat_history:
            return
        
        # Encontrar a última resposta do sistema
        for item in reversed(self.chat_history):
            if item["role"] == "assistant":
                response = item["content"]
                self.parent.clipboard_clear()
                self.parent.clipboard_append(response)
                self.app.update_status("Resposta copiada para a área de transferência", "success")
                return
        
        self.app.update_status("Nenhuma resposta para copiar", "warning")
    
    def regenerate_response(self):
        """Regenera a última resposta"""
        if not self.chat_history:
            return
        
        # Encontrar a última consulta do usuário
        for item in reversed(self.chat_history):
            if item["role"] == "user":
                query = item["content"]
                self.query_text.delete("1.0", tk.END)
                self.query_text.insert("1.0", query)
                self.send_query()
                return
        
        self.app.update_status("Nenhuma consulta para regenerar", "warning")
    
    def complement_context(self):
        """Abre campo para complementar o contexto da última consulta"""
        if not self.chat_history:
            messagebox.showwarning("Aviso", "Não há histórico de conversa para complementar.")
            return
        
        # Encontrar a última consulta e resposta
        last_query = ""
        for item in self.chat_history:
            if item["role"] == "user":
                last_query = item["content"]
        
        if not last_query:
            messagebox.showwarning("Aviso", "Não há consulta anterior para complementar.")
            return
        
        # Solicitar complemento
        complement = messagebox.askstring(
            "Complementar Contexto",
            "Digite informações adicionais para complementar sua última consulta:",
            parent=self.parent
        )
        
        if not complement:
            return
        
        # Adicionar complemento ao campo de consulta
        self.query_text.delete("1.0", tk.END)
        self.query_text.insert("1.0", f"Complementando minha consulta anterior: {complement}")
        
        # Enviar consulta
        self.send_query()
    
    def reset_conversation(self):
        """Reinicia a conversa atual"""
        if not self.chat_history:
            return
        
        if messagebox.askyesno("Reset", "Deseja reiniciar a conversa atual? Todo o histórico será perdido."):
            self.chat_history = []
            self.response_text.config(state="normal")
            self.response_text.delete("1.0", tk.END)
            self.response_text.config(state="disabled")
            self.app.update_status("Conversa reiniciada", "info")
    
    def save_conversation(self):
        """Salva a conversa atual"""
        if not self.chat_history:
            messagebox.showwarning("Aviso", "Não há conversa para salvar.")
            return
        
        # Solicitar nome da conversa
        conversation_name = messagebox.askstring(
            "Salvar Conversa",
            "Digite um nome para a conversa:",
            parent=self.parent
        )
        
        if not conversation_name:
            return
        
        # Preparar dados da conversa
        category = self.category_var.get()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{conversation_name}_{timestamp}.json"
        filepath = os.path.join(self.conversations_dir, filename)
        
        conversation_data = {
            "name": conversation_name,
            "category": category,
            "timestamp": timestamp,
            "history": self.chat_history
        }
        
        try:
            # Salvar conversa
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, ensure_ascii=False, indent=2)
            
            # Adicionar à lista de conversas
            self.conversations[filename] = conversation_data
            
            self.app.update_status(f"Conversa salva: {conversation_name}", "success")
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar a conversa:\n{e}")
            self.app.update_status(f"Erro ao salvar conversa: {str(e)}", "error")
    
    def load_conversation(self):
        """Carrega uma conversa salva"""
        if not self.conversations:
            messagebox.showinfo("Informação", "Não há conversas salvas.")
            return
        
        # Criar lista de conversas para seleção
        conversation_list = []
        for filename, data in self.conversations.items():
            name = data.get("name", "Sem nome")
            category = data.get("category", "Geral")
            timestamp = data.get("timestamp", "")
            conversation_list.append(f"{name} ({category}) - {timestamp}")
        
        # Solicitar seleção
        selected = messagebox.askstring(
            "Carregar Conversa",
            "Selecione uma conversa para carregar:",
            parent=self.parent
        )
        
        if not selected:
            return
        
        # Encontrar conversa selecionada
        selected_index = -1
        try:
            selected_index = conversation_list.index(selected)
        except ValueError:
            messagebox.showwarning("Aviso", "Conversa não encontrada.")
            return
        
        # Obter dados da conversa
        filename = list(self.conversations.keys())[selected_index]
        conversation_data = self.conversations[filename]
        
        # Carregar conversa
        self.chat_history = conversation_data.get("history", [])
        self.category_var.set(conversation_data.get("category", "Geral"))
        
        # Atualizar interface
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", tk.END)
        
        # Adicionar mensagens ao widget
        for item in self.chat_history:
            if item["role"] == "user":
                self.add_user_message(item["content"])
            else:
                self.add_system_message(item["content"])
        
        self.app.update_status(f"Conversa carregada: {conversation_data.get('name', 'Sem nome')}", "success")
    
    def new_conversation(self):
        """Inicia uma nova conversa"""
        if self.chat_history and messagebox.askyesno("Nova Conversa", "Deseja salvar a conversa atual antes de iniciar uma nova?"):
            self.save_conversation()
        
        # Reiniciar conversa
        self.chat_history = []
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", tk.END)
        self.response_text.config(state="disabled")
        self.category_var.set("Geral")
        
        self.app.update_status("Nova conversa iniciada", "info")
    
    def load_conversations(self):
        """Carrega conversas salvas do disco"""
        self.conversations = {}
        
        if not os.path.exists(self.conversations_dir):
            return
        
        for filename in os.listdir(self.conversations_dir):
            if filename.endswith(".json"):
                try:
                    filepath = os.path.join(self.conversations_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        conversation_data = json.load(f)
                    
                    self.conversations[filename] = conversation_data
                except Exception as e:
                    print(f"Erro ao carregar conversa {filename}: {str(e)}")
