"""
Módulo para gerenciamento de logs e visualização de logs anteriores.
Implementa persistência segura e interface de visualização.
"""

import os
import json
import tkinter as tk
from tkinter import ttk
import datetime
import threading

class LogManager:
    """
    Classe para gerenciamento de logs.
    """
    
    def __init__(self, logs_dir="logs"):
        """
        Inicializa o gerenciador de logs.
        
        Args:
            logs_dir: Diretório onde os logs são armazenados
        """
        self.logs_dir = logs_dir
        
        # Criar diretório se não existir
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)
    
    def get_available_logs(self):
        """
        Retorna uma lista de arquivos de log disponíveis.
        
        Returns:
            list: Lista de caminhos para arquivos de log
        """
        log_files = []
        for filename in os.listdir(self.logs_dir):
            if filename.endswith(".json"):
                log_files.append(os.path.join(self.logs_dir, filename))
        
        # Ordenar por data de modificação (mais recente primeiro)
        log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        return log_files
    
    def get_log_info(self, log_path):
        """
        Retorna informações básicas sobre um arquivo de log.
        
        Args:
            log_path: Caminho para o arquivo de log
            
        Returns:
            dict: Informações sobre o log
        """
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_data = json.load(f)
            
            # Extrair informações básicas
            flow_name = log_data.get("flow_name", "Fluxo desconhecido")
            start_time = log_data.get("start_time", "")
            end_time = log_data.get("end_time", "")
            total_duration = log_data.get("total_duration", 0)
            
            # Contar ações por tipo
            actions = log_data.get("actions", [])
            action_types = {}
            for action in actions:
                action_type = action.get("type", "unknown")
                action_types[action_type] = action_types.get(action_type, 0) + 1
            
            # Formatar datas
            try:
                start_dt = datetime.datetime.fromisoformat(start_time)
                start_formatted = start_dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                start_formatted = start_time
            
            try:
                end_dt = datetime.datetime.fromisoformat(end_time)
                end_formatted = end_dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                end_formatted = end_time
            
            return {
                "flow_name": flow_name,
                "start_time": start_formatted,
                "end_time": end_formatted,
                "total_duration": f"{total_duration:.2f} segundos",
                "total_actions": len(actions),
                "clicks": action_types.get("click", 0),
                "inputs": action_types.get("input", 0),
                "navigations": action_types.get("navigation", 0),
                "errors": action_types.get("error", 0),
                "network_requests": len(log_data.get("network_requests", []))
            }
        
        except Exception as e:
            return {
                "flow_name": os.path.basename(log_path),
                "error": str(e)
            }
    
    def load_log(self, log_path):
        """
        Carrega um arquivo de log.
        
        Args:
            log_path: Caminho para o arquivo de log
            
        Returns:
            dict: Dados do log
        """
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}
    
    def delete_log(self, log_path):
        """
        Exclui um arquivo de log.
        
        Args:
            log_path: Caminho para o arquivo de log
            
        Returns:
            bool: True se a exclusão foi bem-sucedida, False caso contrário
        """
        try:
            os.remove(log_path)
            return True
        except Exception:
            return False
    
    def export_log(self, log_path, export_path, format="json"):
        """
        Exporta um arquivo de log para outro formato.
        
        Args:
            log_path: Caminho para o arquivo de log
            export_path: Caminho para o arquivo de exportação
            format: Formato de exportação (json, csv, html)
            
        Returns:
            bool: True se a exportação foi bem-sucedida, False caso contrário
        """
        try:
            log_data = self.load_log(log_path)
            
            if format == "json":
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False)
                return True
            
            elif format == "csv":
                with open(export_path, "w", encoding="utf-8") as f:
                    # Escrever cabeçalho
                    f.write("type,timestamp,elapsed_time,url,page_title\n")
                    
                    # Escrever ações
                    for action in log_data.get("actions", []):
                        action_type = action.get("type", "")
                        timestamp = action.get("timestamp", "")
                        elapsed_time = action.get("elapsed_time", "")
                        url = action.get("url", "").replace(",", " ")
                        page_title = action.get("page_title", "").replace(",", " ")
                        
                        f.write(f"{action_type},{timestamp},{elapsed_time},{url},{page_title}\n")
                
                return True
            
            elif format == "html":
                with open(export_path, "w", encoding="utf-8") as f:
                    # Escrever cabeçalho HTML
                    f.write("""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Log de Ações</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .error { background-color: #ffdddd; }
        .success { background-color: #ddffdd; }
    </style>
</head>
<body>
    <h1>Log de Ações - """ + log_data.get("flow_name", "Fluxo") + """</h1>
    <p><strong>Início:</strong> """ + log_data.get("start_time", "") + """</p>
    <p><strong>Fim:</strong> """ + log_data.get("end_time", "") + """</p>
    <p><strong>Duração total:</strong> """ + str(log_data.get("total_duration", "")) + """ segundos</p>
    
    <h2>Ações</h2>
    <table>
        <tr>
            <th>Tipo</th>
            <th>Timestamp</th>
            <th>Tempo (s)</th>
            <th>URL</th>
            <th>Título</th>
        </tr>
""")
                    
                    # Escrever ações
                    for action in log_data.get("actions", []):
                        action_type = action.get("type", "")
                        timestamp = action.get("timestamp", "")
                        elapsed_time = action.get("elapsed_time", "")
                        url = action.get("url", "")
                        page_title = action.get("page_title", "")
                        
                        row_class = ""
                        if action_type == "error":
                            row_class = "error"
                        elif action_type == "session_end":
                            row_class = "success"
                        
                        f.write(f"""        <tr class="{row_class}">
            <td>{action_type}</td>
            <td>{timestamp}</td>
            <td>{elapsed_time}</td>
            <td>{url}</td>
            <td>{page_title}</td>
        </tr>
""")
                    
                    # Escrever rodapé HTML
                    f.write("""    </table>
</body>
</html>""")
                
                return True
            
            else:
                return False
        
        except Exception:
            return False

class LogViewerWindow:
    """
    Janela para visualização de logs anteriores.
    """
    
    def __init__(self, parent, logs):
        """
        Inicializa a janela de visualização de logs.
        
        Args:
            parent: Widget pai
            logs: Lista de caminhos para arquivos de log
        """
        self.parent = parent
        self.logs = logs
        self.selected_log = None
        self.log_manager = LogManager()
        
        # Criar janela
        self.window = tk.Toplevel(parent)
        self.window.title("Visualizador de Logs")
        self.window.geometry("900x600")
        self.window.minsize(800, 500)
        
        # Aplicar tema escuro
        self.window.configure(bg="#1e1e1e")
        
        # Frame principal
        self.main_frame = ttk.Frame(self.window, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Dividir em dois painéis
        self.paned_window = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Painel esquerdo (lista de logs)
        self.logs_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(self.logs_frame, weight=1)
        
        # Painel direito (detalhes do log)
        self.details_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(self.details_frame, weight=2)
        
        # Configurar lista de logs
        ttk.Label(self.logs_frame, text="Logs Disponíveis", font=("Helvetica", 12, "bold")).pack(fill=tk.X, pady=(0, 5))
        
        self.logs_listbox = tk.Listbox(self.logs_frame, bg="#2a2a2a", fg="#d4d4d4", 
                                      selectbackground="#264f78", selectforeground="#ffffff")
        self.logs_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        logs_scrollbar = ttk.Scrollbar(self.logs_frame, orient="vertical", command=self.logs_listbox.yview)
        logs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.logs_listbox.configure(yscrollcommand=logs_scrollbar.set)
        
        # Preencher lista de logs
        for log_path in self.logs:
            # Obter informações básicas
            log_info = self.log_manager.get_log_info(log_path)
            flow_name = log_info.get("flow_name", os.path.basename(log_path))
            
            # Adicionar à lista
            self.logs_listbox.insert(tk.END, flow_name)
        
        # Vincular evento de seleção
        self.logs_listbox.bind("<<ListboxSelect>>", self.on_log_select)
        
        # Configurar painel de detalhes
        ttk.Label(self.details_frame, text="Detalhes do Log", font=("Helvetica", 12, "bold")).pack(fill=tk.X, pady=(0, 5))
        
        # Frame para informações básicas
        self.info_frame = ttk.Frame(self.details_frame)
        self.info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Criar campos de informação
        self.info_labels = {}
        info_fields = [
            "flow_name", "start_time", "end_time", "total_duration",
            "total_actions", "clicks", "inputs", "navigations", "errors", "network_requests"
        ]
        
        for i, field in enumerate(info_fields):
            row, col = divmod(i, 2)
            
            # Label do campo
            field_label = field.replace("_", " ").title() + ":"
            ttk.Label(self.info_frame, text=field_label).grid(row=row, column=col*2, sticky="w", padx=(10 if col else 0, 5), pady=2)
            
            # Valor do campo
            value_label = ttk.Label(self.info_frame, text="")
            value_label.grid(row=row, column=col*2+1, sticky="w", padx=(0, 10), pady=2)
            self.info_labels[field] = value_label
        
        # Frame para ações
        self.actions_frame = ttk.LabelFrame(self.details_frame, text="Ações")
        self.actions_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Criar tabela de ações
        self.actions_tree = ttk.Treeview(self.actions_frame, columns=("type", "timestamp", "elapsed", "url", "details"), show="headings")
        self.actions_tree.heading("type", text="Tipo")
        self.actions_tree.heading("timestamp", text="Timestamp")
        self.actions_tree.heading("elapsed", text="Tempo (s)")
        self.actions_tree.heading("url", text="URL")
        self.actions_tree.heading("details", text="Detalhes")
        
        self.actions_tree.column("type", width=100)
        self.actions_tree.column("timestamp", width=150)
        self.actions_tree.column("elapsed", width=80)
        self.actions_tree.column("url", width=200)
        self.actions_tree.column("details", width=300)
        
        self.actions_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        actions_scrollbar = ttk.Scrollbar(self.actions_frame, orient="vertical", command=self.actions_tree.yview)
        actions_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.actions_tree.configure(yscrollcommand=actions_scrollbar.set)
        
        # Botões de ação
        self.buttons_frame = ttk.Frame(self.main_frame)
        self.buttons_frame.pack(fill=tk.X)
        
        ttk.Button(self.buttons_frame, text="Selecionar", style="primary.TButton", 
                  command=self.select_log).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(self.buttons_frame, text="Exportar", style="info.TButton", 
                  command=self.export_log).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(self.buttons_frame, text="Excluir", style="danger.TButton", 
                  command=self.delete_log).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(self.buttons_frame, text="Cancelar", style="secondary.TButton", 
                  command=self.window.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Selecionar primeiro log se houver
        if self.logs:
            self.logs_listbox.selection_set(0)
            self.on_log_select(None)
    
    def on_log_select(self, event):
        """
        Manipulador de evento para seleção de log.
        
        Args:
            event: Evento de seleção
        """
        # Obter índice selecionado
        selection = self.logs_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        if index >= len(self.logs):
            return
        
        # Obter caminho do log
        log_path = self.logs[index]
        
        # Carregar informações do log
        log_info = self.log_manager.get_log_info(log_path)
        
        # Atualizar campos de informação
        for field, label in self.info_labels.items():
            label.config(text=str(log_info.get(field, "")))
        
        # Carregar ações
        self.actions_tree.delete(*self.actions_tree.get_children())
        
        # Iniciar carregamento em thread separada
        threading.Thread(target=self._load_actions, args=(log_path,), daemon=True).start()
        
        # Armazenar log selecionado
        self.selected_log = log_path
    
    def _load_actions(self, log_path):
        """
        Carrega ações do log em uma thread separada.
        
        Args:
            log_path: Caminho para o arquivo de log
        """
        try:
            # Carregar log
            log_data = self.log_manager.load_log(log_path)
            actions = log_data.get("actions", [])
            
            # Atualizar tabela de ações
            for action in actions:
                action_type = action.get("type", "")
                timestamp = action.get("timestamp", "")
                elapsed_time = action.get("elapsed_time", "")
                url = action.get("url", "")
                
                # Formatar detalhes
                details = ""
                if action_type == "click":
                    element = action.get("element", {})
                    tag = element.get("tag", "")
                    text = element.get("text", "")
                    details = f"Clique em {tag}: {text}"
                elif action_type == "input":
                    element = action.get("element", {})
                    tag = element.get("tag", "")
                    value = action.get("value", "")
                    details = f"Input em {tag}: {value}"
                elif action_type == "navigation":
                    details = f"Navegação para: {url}"
                elif action_type == "error":
                    details = f"Erro: {action.get('error', '')}"
                
                # Adicionar à tabela
                self.actions_tree.insert("", tk.END, values=(action_type, timestamp, elapsed_time, url, details))
        
        except Exception as e:
            print(f"Erro ao carregar ações: {str(e)}")
    
    def select_log(self):
        """Seleciona o log atual e fecha a janela"""
        self.window.destroy()
    
    def export_log(self):
        """Exporta o log selecionado"""
        if not self.selected_log:
            return
        
        # Criar janela de exportação
        export_window = tk.Toplevel(self.window)
        export_window.title("Exportar Log")
        export_window.geometry("400x200")
        export_window.minsize(400, 200)
        export_window.transient(self.window)
        export_window.grab_set()
        
        # Aplicar tema escuro
        export_window.configure(bg="#1e1e1e")
        
        # Frame principal
        export_frame = ttk.Frame(export_window, padding=10)
        export_frame.pack(fill=tk.BOTH, expand=True)
        
        # Formato
        ttk.Label(export_frame, text="Formato:").grid(row=0, column=0, sticky="w", pady=5)
        format_var = tk.StringVar(value="json")
        ttk.Radiobutton(export_frame, text="JSON", variable=format_var, value="json").grid(row=0, column=1, sticky="w", pady=5)
        ttk.Radiobutton(export_frame, text="CSV", variable=format_var, value="csv").grid(row=1, column=1, sticky="w", pady=5)
        ttk.Radiobutton(export_frame, text="HTML", variable=format_var, value="html").grid(row=2, column=1, sticky="w", pady=5)
        
        # Botões
        buttons_frame = ttk.Frame(export_frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Exportar", style="primary.TButton", 
                  command=lambda: self._do_export(format_var.get(), export_window)).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Cancelar", style="secondary.TButton", 
                  command=export_window.destroy).pack(side=tk.LEFT, padx=5)
    
    def _do_export(self, format, export_window):
        """
        Realiza a exportação do log.
        
        Args:
            format: Formato de exportação
            export_window: Janela de exportação
        """
        # Determinar extensão
        extension = f".{format}"
        
        # Obter caminho de exportação
        from tkinter import filedialog
        export_path = filedialog.asksaveasfilename(
            defaultextension=extension,
            filetypes=[(f"{format.upper()} files", f"*{extension}"), ("All files", "*.*")],
            title="Exportar Log"
        )
        
        if not export_path:
            return
        
        # Exportar
        success = self.log_manager.export_log(self.selected_log, export_path, format)
        
        # Fechar janela de exportação
        export_window.destroy()
        
        # Mostrar mensagem
        if success:
            tk.messagebox.showinfo("Exportação", f"Log exportado com sucesso para {export_path}")
        else:
            tk.messagebox.showerror("Erro", "Erro ao exportar log")
    
    def delete_log(self):
        """Exclui o log selecionado"""
        if not self.selected_log:
            return
        
        # Confirmar exclusão
        confirm = tk.messagebox.askyesno("Confirmar Exclusão", "Tem certeza que deseja excluir este log?")
        if not confirm:
            return
        
        # Excluir log
        success = self.log_manager.delete_log(self.selected_log)
        
        if success:
            # Remover da lista
            index = self.logs.index(self.selected_log)
            self.logs.pop(index)
            self.logs_listbox.delete(index)
            
            # Limpar detalhes
            for field, label in self.info_labels.items():
                label.config(text="")
            
            self.actions_tree.delete(*self.actions_tree.get_children())
            
            # Selecionar próximo log
            if self.logs:
                next_index = min(index, len(self.logs) - 1)
                self.logs_listbox.selection_set(next_index)
                self.on_log_select(None)
            else:
                self.selected_log = None
            
            tk.messagebox.showinfo("Exclusão", "Log excluído com sucesso")
        else:
            tk.messagebox.showerror("Erro", "Erro ao excluir log")
    
    def get_selected_log(self):
        """
        Retorna o caminho do log selecionado.
        
        Returns:
            str: Caminho do log selecionado ou None
        """
        return self.selected_log

def show_log_viewer(parent, logs):
    """
    Mostra o visualizador de logs e retorna o log selecionado.
    
    Args:
        parent: Widget pai
        logs: Lista de caminhos para arquivos de log
        
    Returns:
        str: Caminho do log selecionado ou None
    """
    viewer = LogViewerWindow(parent, logs)
    parent.wait_window(viewer.window)
    return viewer.get_selected_log()
