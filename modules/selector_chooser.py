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

class SelectorChooserDialog:
    """
    Diálogo para escolha de seletores alternativos para um elemento.
    Permite visualizar e selecionar entre diferentes opções de seletores.
    """
    
    def __init__(self, parent, element_data, title="Escolher Seletor"):
        """
        Inicializa o diálogo de escolha de seletores.
        
        Args:
            parent: Widget pai
            element_data: Dicionário com dados do elemento
            title: Título da janela
        """
        self.parent = parent
        self.element_data = element_data
        self.result = None  # Armazenará o seletor escolhido
        
        # Criar janela de diálogo
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("700x500")
        self.dialog.minsize(600, 400)
        self.dialog.transient(parent)  # Torna modal
        self.dialog.grab_set()  # Bloqueia interação com janela principal
        
        # Centralizar na tela
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        # Configurar layout
        self.create_widgets()
        
        # Preencher dados
        self.populate_selectors()
        
        # Aguardar fechamento
        self.dialog.wait_window()
    
    def create_widgets(self):
        """Cria os widgets do diálogo"""
        # Frame principal com padding
        main_frame = ttk.Frame(self.dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título e descrição
        ttk.Label(
            main_frame, 
            text="Escolha o Seletor para o Elemento", 
            font=("Helvetica", 14, "bold")
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Informações do elemento
        element_info_frame = ttk.LabelFrame(main_frame, text="Informações do Elemento", padding=10)
        element_info_frame.pack(fill=tk.X, pady=10)
        
        # Tipo de elemento
        element_type = self.element_data.get("type", "desconhecido")
        ttk.Label(
            element_info_frame,
            text=f"Tipo: {element_type.capitalize()}",
            font=("Helvetica", 10, "bold")
        ).pack(anchor=tk.W)
        
        # Texto/descrição do elemento
        element_text = self._get_element_description()
        ttk.Label(
            element_info_frame,
            text=f"Descrição: {element_text}",
            wraplength=650
        ).pack(anchor=tk.W, pady=5)
        
        # Lista de seletores disponíveis
        selectors_frame = ttk.LabelFrame(main_frame, text="Seletores Disponíveis", padding=10)
        selectors_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Cabeçalho da lista
        headers_frame = ttk.Frame(selectors_frame)
        headers_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(headers_frame, text="Prioridade", width=10).pack(side=tk.LEFT)
        ttk.Label(headers_frame, text="Tipo", width=15).pack(side=tk.LEFT)
        ttk.Label(headers_frame, text="Seletor", width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(headers_frame, text="Confiabilidade", width=15).pack(side=tk.LEFT)
        
        # Separador
        ttk.Separator(selectors_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Lista de seletores
        self.selectors_listbox = tk.Listbox(
            selectors_frame,
            height=10,
            font=("Consolas", 10),
            selectmode=tk.SINGLE,
            activestyle="none",
            exportselection=False
        )
        scrollbar = ttk.Scrollbar(selectors_frame, orient=tk.VERTICAL, command=self.selectors_listbox.yview)
        self.selectors_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.selectors_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular evento de seleção
        self.selectors_listbox.bind("<<ListboxSelect>>", self.on_selector_select)
        self.selectors_listbox.bind("<Double-1>", self.on_selector_double_click)
        
        # Visualização do seletor
        preview_frame = ttk.LabelFrame(main_frame, text="Visualização do Seletor", padding=10)
        preview_frame.pack(fill=tk.X, pady=10)
        
        self.preview_text = tk.Text(
            preview_frame,
            height=3,
            width=60,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#282a36",
            fg="#f8f8f2"
        )
        preview_scrollbar = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scrollbar.set)
        
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Botões de ação
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=10)
        
        self.select_button = ttk.Button(
            buttons_frame,
            text="Selecionar",
            bootstyle="success",
            command=self.on_select,
            state="disabled"
        )
        self.select_button.pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            buttons_frame,
            text="Cancelar",
            bootstyle="secondary",
            command=self.on_cancel
        ).pack(side=tk.RIGHT, padx=5)
    
    def _get_element_description(self):
        """Obtém uma descrição legível do elemento"""
        element_type = self.element_data.get("type", "unknown")
        
        if element_type == "navigation":
            return self.element_data.get("url", "URL desconhecida")
        
        elif element_type == "click":
            element = self.element_data.get("element", {})
            text = element.get("text", "").strip()
            aria_label = element.get("aria-label", "")
            name = element.get("name", "")
            tag = element.get("tag", "")
            el_id = element.get("id", "")
            return text if text else aria_label if aria_label else name if name else el_id if el_id else f"<{tag}>"
        
        elif element_type == "input":
            element = self.element_data.get("element", {})
            value = element.get("value", "")
            name = element.get("name", "")
            aria_label = element.get("aria-label", "")
            el_id = element.get("id", "")
            placeholder = element.get("placeholder", "")
            description_base = name if name else el_id if el_id else aria_label if aria_label else placeholder
            return f"{description_base} = '{value[:30]}{'...' if len(value)>30 else ''}'"
        
        elif element_type == "select":
            element = self.element_data.get("element", {})
            value = element.get("value", "")
            selected_text = element.get("selected_text", "")
            name = element.get("name", "")
            aria_label = element.get("aria-label", "")
            el_id = element.get("id", "")
            description_base = name if name else el_id if el_id else aria_label
            option_text = selected_text if selected_text else value
            return f"{description_base} = '{option_text}'"
        
        elif element_type == "network":
            method = self.element_data.get("method", "?")
            url = self.element_data.get("url", "")
            return f"{method} {url}"
        
        return f"Elemento do tipo {element_type}"
    
    def populate_selectors(self):
        """Preenche a lista de seletores disponíveis"""
        element_type = self.element_data.get("type", "unknown")
        
        # Lista para armazenar os seletores disponíveis
        self.available_selectors = []
        
        if element_type in ["click", "input", "select"]:
            element = self.element_data.get("element", {})
            
            # Extrair todos os possíveis seletores do elemento
            selectors = []
            
            # 1. data-cy ou data-test (maior prioridade)
            data_cy = element.get("data-cy") or element.get("data-test") or element.get("data-testid")
            if data_cy:
                selectors.append({
                    "type": "data-cy",
                    "value": f"[data-cy='{data_cy}']",
                    "priority": 1,
                    "reliability": "Alta"
                })
            
            # 2. ID
            el_id = element.get("id")
            if el_id:
                selectors.append({
                    "type": "id",
                    "value": f"#{el_id}",
                    "priority": 2,
                    "reliability": "Alta"
                })
            
            # 3. Name
            name = element.get("name")
            if name:
                selectors.append({
                    "type": "name",
                    "value": f"[name='{name}']",
                    "priority": 3,
                    "reliability": "Média"
                })
            
            # 4. aria-label
            aria_label = element.get("aria-label")
            if aria_label:
                selectors.append({
                    "type": "aria-label",
                    "value": f"[aria-label='{aria_label}']",
                    "priority": 4,
                    "reliability": "Média"
                })
            
            # 5. Texto (para elementos com texto)
            text = element.get("text", "").strip()
            if text:
                selectors.append({
                    "type": "texto",
                    "value": f"contains('{text}')",
                    "priority": 5,
                    "reliability": "Média"
                })
            
            # 6. Placeholder (para inputs)
            placeholder = element.get("placeholder")
            if placeholder:
                selectors.append({
                    "type": "placeholder",
                    "value": f"[placeholder='{placeholder}']",
                    "priority": 6,
                    "reliability": "Média"
                })
            
            # 7. Classe CSS
            css_class = element.get("class")
            if css_class:
                # Limitar a classes que parecem ser identificadores únicos
                classes = css_class.split()
                for cls in classes:
                    if len(cls) > 3 and not cls.startswith("ng-") and not cls in ["active", "selected", "disabled", "hidden"]:
                        selectors.append({
                            "type": "classe",
                            "value": f".{cls}",
                            "priority": 7,
                            "reliability": "Baixa"
                        })
            
            # 8. XPath (como último recurso)
            xpath = self.element_data.get("xpath")
            if xpath:
                selectors.append({
                    "type": "xpath",
                    "value": xpath,
                    "priority": 8,
                    "reliability": "Baixa"
                })
            
            # 9. Seletor CSS completo (como último recurso)
            css_selector = self.element_data.get("selector")
            if css_selector and css_selector not in [s["value"] for s in selectors]:
                selectors.append({
                    "type": "css",
                    "value": css_selector,
                    "priority": 9,
                    "reliability": "Baixa"
                })
            
            # Armazenar seletores disponíveis
            self.available_selectors = selectors
            
            # Adicionar à listbox
            for i, selector in enumerate(selectors):
                self.selectors_listbox.insert(
                    tk.END, 
                    f"{selector['priority']:^10} {selector['type']:^15} {selector['value']:<50} {selector['reliability']:^15}"
                )
            
            # Selecionar o primeiro seletor por padrão
            if selectors:
                self.selectors_listbox.selection_set(0)
                self.selectors_listbox.event_generate("<<ListboxSelect>>")
        
        elif element_type == "navigation":
            # Para navegação, o seletor é a URL
            url = self.element_data.get("url", "")
            selectors = [{
                "type": "url",
                "value": url,
                "priority": 1,
                "reliability": "Alta"
            }]
            
            self.available_selectors = selectors
            self.selectors_listbox.insert(
                tk.END, 
                f"{1:^10} {'url':^15} {url:<50} {'Alta':^15}"
            )
            self.selectors_listbox.selection_set(0)
            self.selectors_listbox.event_generate("<<ListboxSelect>>")
        
        elif element_type == "network":
            # Para requisições de rede, o seletor é a URL da requisição
            url = self.element_data.get("url", "")
            method = self.element_data.get("method", "GET")
            
            # Tentar extrair o endpoint
            endpoint = url.split("?")[0]  # Remover query string
            endpoint = endpoint.split("#")[0]  # Remover fragmento
            parts = endpoint.rstrip("/").split("/")
            endpoint_name = parts[-1] if parts else "endpoint"
            
            selectors = [{
                "type": "intercept",
                "value": f"cy.intercept('{method}', '**/{endpoint_name}*')",
                "priority": 1,
                "reliability": "Média"
            }, {
                "type": "url completa",
                "value": f"cy.intercept('{method}', '{url}')",
                "priority": 2,
                "reliability": "Alta"
            }]
            
            self.available_selectors = selectors
            for i, selector in enumerate(selectors):
                self.selectors_listbox.insert(
                    tk.END, 
                    f"{selector['priority']:^10} {selector['type']:^15} {selector['value']:<50} {selector['reliability']:^15}"
                )
            
            self.selectors_listbox.selection_set(0)
            self.selectors_listbox.event_generate("<<ListboxSelect>>")
    
    def on_selector_select(self, event=None):
        """Manipula a seleção de um seletor na lista"""
        selected_indices = self.selectors_listbox.curselection()
        if not selected_indices:
            self.select_button.config(state="disabled")
            self.preview_text.delete("1.0", tk.END)
            return
        
        # Obter seletor selecionado
        index = selected_indices[0]
        if index < len(self.available_selectors):
            selector = self.available_selectors[index]
            
            # Atualizar visualização
            self.preview_text.delete("1.0", tk.END)
            
            element_type = self.element_data.get("type", "unknown")
            
            if element_type == "navigation":
                self.preview_text.insert(tk.END, f"cy.visit('{selector['value']}')")
            elif element_type == "network":
                self.preview_text.insert(tk.END, selector['value'])
            else:
                self.preview_text.insert(tk.END, f"cy.get('{selector['value']}')")
            
            # Habilitar botão de seleção
            self.select_button.config(state="normal")
    
    def on_selector_double_click(self, event=None):
        """Manipula o duplo clique em um seletor (seleciona e fecha)"""
        selected_indices = self.selectors_listbox.curselection()
        if selected_indices:
            self.on_select()
    
    def on_select(self):
        """Manipula a seleção do seletor"""
        selected_indices = self.selectors_listbox.curselection()
        if not selected_indices:
            return
        
        # Obter seletor selecionado
        index = selected_indices[0]
        if index < len(self.available_selectors):
            self.result = self.available_selectors[index]
            self.dialog.destroy()
    
    def on_cancel(self):
        """Manipula o cancelamento da seleção"""
        self.result = None
        self.dialog.destroy()
