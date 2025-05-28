# Corrigido: Garantido que captured_actions seja usado na exportação

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import queue
import time
import json
import os
import datetime
import re
import base64
from io import BytesIO
from PIL import Image, ImageTk
from bs4 import BeautifulSoup
from tkinter import messagebox # Importar messagebox

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, JavascriptException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

class ElementCapture:
    """
    Módulo para captura de elementos e ações do usuário no navegador.
    """
    
    def __init__(self, parent, app):
        """
        Inicializa o módulo de captura de elementos.
        
        Args:
            parent: Frame pai onde o módulo será exibido
            app: Referência à aplicação principal
        """
        self.parent = parent
        self.app = app
        self.config = app.config
        
        # Variáveis de estado
        self.driver = None
        self.capturing = False
        self.start_time = None
        self.captured_elements = [] # Este parece não ser usado para exportação, verificar uso.
        self.captured_actions = [] # Este é usado para exportação
        self.captured_network = []
        self.current_url = ""
        self.current_title = ""
        self.screenshot = None
        
        # Fila para comunicação thread-safe
        self.capture_queue = queue.Queue()
        
        # Criar componentes da interface
        self.create_widgets()
        
        # Configurar prioridade de seletores
        self.selector_priority = self.config.get("selector_priority", [
            "data-cy", "data-testid", "id", "name", "role", "aria-label", "class", "tag", "type"
        ])
        
        # Configurar seletores habilitados
        self.selector_enabled = self.config.get("selector_enabled", {})
        
        # Inicializar monitoramento de eventos
        self.event_listeners = []
        self.last_action_time = 0
        self.action_throttle = 0.1  # segundos
        self.last_html = ""
        self.last_elements_map = {}
    
    def create_widgets(self):
        """Cria os widgets da interface de captura"""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=tk.BOTH, expand=True)  # Garantir que o frame seja empacotado
        
        # Título
        ttk.Label(
            self.frame, 
            text="Captura de Elementos", 
            font=("Helvetica", 24, "bold")
        ).pack(anchor=tk.W, pady=(0, 20), padx=20)
        
        # Frame principal dividido
        self.main_paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Painel de navegação
        self.nav_frame = ttk.LabelFrame(self.main_paned, text="Navegador", padding=10)
        self.main_paned.add(self.nav_frame, weight=2)
        
        # Painel de elementos capturados
        self.elements_frame = ttk.LabelFrame(self.main_paned, text="Elementos Capturados", padding=10)
        self.main_paned.add(self.elements_frame, weight=1)
        
        # Configurar painel de navegação
        self.setup_nav_panel()
        
        # Configurar painel de elementos
        self.setup_elements_panel()
        
        # Barra de botões inferior
        self.button_frame = ttk.Frame(self.frame, padding=10)
        self.button_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=10)
        
        # Botões de ação
        self.start_button = ttk.Button(
            self.button_frame,
            text="Iniciar Captura",
            bootstyle="success",
            command=self.start_capture
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(
            self.button_frame,
            text="Parar Captura",
            bootstyle="danger",
            state="disabled",
            command=self.stop_capture
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.export_button = ttk.Button(
            self.button_frame,
            text="Exportar Captura",
            bootstyle="primary",
            state="disabled",
            command=self.export_capture
        )
        self.export_button.pack(side=tk.RIGHT, padx=5)
        
        # Iniciar thread de processamento da fila
        self.queue_running = True
        self.queue_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.queue_thread.start()
    
    def setup_nav_panel(self):
        """Configura o painel de navegação"""
        # Barra de navegação
        nav_bar = ttk.Frame(self.nav_frame)
        nav_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Botões de navegação
        self.back_button = ttk.Button(
            nav_bar,
            text="←",
            width=3,
            state="disabled",
            command=self._browser_back
        )
        self.back_button.pack(side=tk.LEFT, padx=2)
        
        self.forward_button = ttk.Button(
            nav_bar,
            text="→",
            width=3,
            state="disabled",
            command=self._browser_forward
        )
        self.forward_button.pack(side=tk.LEFT, padx=2)
        
        self.refresh_button = ttk.Button(
            nav_bar,
            text="↻",
            width=3,
            state="disabled",
            command=self._browser_refresh
        )
        self.refresh_button.pack(side=tk.LEFT, padx=2)
        
        # Barra de URL
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(
            nav_bar,
            textvariable=self.url_var
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.url_entry.bind("<Return>", self._navigate_to_url)
        
        self.go_button = ttk.Button(
            nav_bar,
            text="Ir",
            width=5,
            state="disabled",
            command=self._navigate_to_url
        )
        self.go_button.pack(side=tk.LEFT)
        
        # Área de visualização
        self.browser_frame = ttk.Frame(self.nav_frame, relief="sunken", borderwidth=1)
        self.browser_frame.pack(fill=tk.BOTH, expand=True)
        
        # Placeholder para screenshot
        self.screenshot_label = ttk.Label(self.browser_frame)
        self.screenshot_label.pack(fill=tk.BOTH, expand=True)
        
        # Status da navegação
        self.nav_status = ttk.Label(
            self.nav_frame,
            text="Navegador não iniciado",
            bootstyle="secondary"
        )
        self.nav_status.pack(anchor=tk.W, pady=(5, 0))
    
    def setup_elements_panel(self):
        """Configura o painel de elementos capturados"""
        # Filtro de elementos
        filter_frame = ttk.Frame(self.elements_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(filter_frame, text="Filtrar:").pack(side=tk.LEFT)
        
        self.filter_var = tk.StringVar(value="Todos")
        filter_combo = ttk.Combobox(
            filter_frame, 
            textvariable=self.filter_var,
            values=["Todos", "Navegação", "Clique", "Input", "Select", "Rede"],
            state="readonly",
            width=10
        )
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind("<<ComboboxSelected>>", self.filter_elements)
        
        # Árvore de elementos
        tree_frame = ttk.Frame(self.elements_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.elements_tree = ttk.Treeview(
            tree_frame,
            columns=("Tipo", "Valor"),
            show="tree headings",
            selectmode="browse"
        )
        
        self.elements_tree.heading("#0", text="Elemento")
        self.elements_tree.heading("Tipo", text="Tipo")
        self.elements_tree.heading("Valor", text="Valor")
        
        self.elements_tree.column("#0", width=150)
        self.elements_tree.column("Tipo", width=80)
        self.elements_tree.column("Valor", width=150)
        
        elements_scrollbar = ttk.Scrollbar(
            tree_frame, 
            orient="vertical", 
            command=self.elements_tree.yview
        )
        
        self.elements_tree.configure(yscrollcommand=elements_scrollbar.set)
        
        self.elements_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        elements_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Vincular evento de seleção
        self.elements_tree.bind("<<TreeviewSelect>>", self.show_element_details)
        
        # Detalhes do elemento
        details_frame = ttk.LabelFrame(self.elements_frame, text="Detalhes", padding=5)
        details_frame.pack(fill=tk.X, pady=5)
        
        self.details_text = tk.Text(
            details_frame,
            height=8,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#282a36",
            fg="#f8f8f2"
        )
        
        details_scrollbar = ttk.Scrollbar(
            details_frame, 
            orient="vertical", 
            command=self.details_text.yview
        )
        
        self.details_text.configure(yscrollcommand=details_scrollbar.set, state="disabled")
        
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        details_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def show(self):
        """Exibe o módulo de captura de elementos"""
        self.frame.pack(fill=tk.BOTH, expand=True)
    
    def hide(self):
        """Oculta o módulo de captura de elementos"""
        self.frame.pack_forget()
    
    def start_capture(self):
        """Inicia a captura de elementos"""
        if self.capturing:
            return
        
        # Atualizar interface
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.export_button.config(state="disabled")
        self.nav_status.config(text="Iniciando navegador...", bootstyle="warning")
        
        # Limpar elementos capturados
        self.captured_elements = []
        self.captured_actions = []
        self.captured_network = []
        self.elements_tree.delete(*self.elements_tree.get_children())
        
        # Iniciar thread de captura
        self.capturing = True
        threading.Thread(target=self._capture_thread, daemon=True).start()
    
    def stop_capture(self):
        """Para a captura de elementos"""
        if not self.capturing:
            return
        
        # Atualizar interface
        self.nav_status.config(text="Finalizando captura...", bootstyle="warning")
        
        # Parar captura
        self.capturing = False
    
    def export_capture(self):
        """Exporta os elementos capturados para um arquivo JSON"""
        if not self.captured_actions and not self.captured_network:
            messagebox.showwarning("Aviso", "Não há elementos para exportar.")
            return
        
        # Criar nome de arquivo baseado na data e hora
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"captura_{timestamp}.json"
        
        # Solicitar nome da sessão
        session_name = self.app.ask_input("Nome da Sessão", "Digite um nome para esta sessão de captura:")
        if not session_name:
            session_name = f"Sessão {timestamp}"
        
        # Criar diretório de logs se não existir
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Caminho completo do arquivo
        filepath = os.path.join(logs_dir, default_filename)
        
        # Criar dados para exportação
        export_data = {
            "session": {
                "name": session_name,
                "timestamp": timestamp,
                "duration": round((time.time() - self.start_time) if self.start_time else 0),
                "browser": "Chrome"
            },
            "actions": self.captured_actions,
            "network": self.captured_network
        }
        
        # Salvar arquivo
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.app.update_status(f"Captura exportada para {filepath}", "success")
            self.current_log_path = filepath
            
            # Perguntar se deseja gerar teste
            if messagebox.askyesno("Exportação Concluída", "Deseja gerar um teste Cypress a partir desta captura?"):
                self.app.show_module("generator")
                self.app.modules["generator"].load_capture(filepath)
            
        except Exception as e:
            messagebox.showerror("Erro de Exportação", f"Não foi possível exportar a captura:\n{e}")
    
    def _capture_thread(self):
        """Thread para captura de elementos"""
        try:
            # Inicializar driver
            self._init_driver()
            
            # Registrar tempo de início
            self.start_time = time.time()
            
            # Loop principal de captura
            while self.capturing:
                # Verificar URL atual
                self._check_url_change()
                
                # Verificar eventos do navegador
                self._check_browser_events()
                
                # Capturar screenshot
                self._capture_screenshot()
                
                # Pequena pausa para não sobrecarregar a CPU
                time.sleep(0.1)
            
            # Finalizar driver
            self._quit_driver()
            
            # Atualizar interface
            self.capture_queue.put(("update_status", "Captura finalizada", "success"))
            self.capture_queue.put(("update_buttons", "stopped"))
            
        except Exception as e:
            # Registrar erro
            self.capture_queue.put(("update_status", f"Erro: {str(e)}", "danger"))
            self.capture_queue.put(("update_buttons", "error"))
            self.capturing = False
            
            # Tentar finalizar driver
            try:
                if self.driver:
                    self.driver.quit()
            except:
                pass
    
    def _init_driver(self):
        """Inicializa o driver do Selenium"""
        # Atualizar status
        self.capture_queue.put(("update_status", "Configurando navegador...", "warning"))
        
        # Configurar opções do Chrome
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        
        # Adicionar argumentos para performance
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        
        # Configurar preferências
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Inicializar driver
        driver_path = self._get_driver_path()
        service = Service(driver_path)
        
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Configurar timeouts
        self.driver.set_page_load_timeout(30)
        self.driver.set_script_timeout(30)
        
        # Navegar para página inicial
        self.driver.get("about:blank")
        
        # Injetar scripts de monitoramento
        self._inject_monitoring_scripts()
        
        # Atualizar status
        self.capture_queue.put(("update_status", "Navegador iniciado", "success"))
        self.capture_queue.put(("update_nav_buttons", "enabled"))
    
    def _get_driver_path(self):
        """Obtém o caminho para o driver do Chrome"""
        # Verificar sistema operacional
        import platform
        system = platform.system().lower()
        
        # Diretório base
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # Caminho para o driver
        if system == "windows":
            driver_path = os.path.join(base_dir, "webdrivers","chromedriver", "chromedriver.exe")
        elif system == "darwin":  # macOS
            driver_path = os.path.join(base_dir, "webdrivers", "chromedriver_mac")
        else:  # Linux
            driver_path = os.path.join(base_dir, "webdrivers", "chromedriver_linux")
        
        # Verificar se o driver existe
        if not os.path.exists(driver_path):
            raise FileNotFoundError(f"Driver do Chrome não encontrado em {driver_path}")
        
        return driver_path
    
    def _inject_monitoring_scripts(self):
        """Injeta scripts para monitorar eventos do navegador"""
        try:
            # Script para monitorar cliques
            click_script = """
            if (typeof window._clickEvents === 'undefined') {
                window._clickEvents = [];
                
                document.addEventListener('click', function(e) {
                    if (e.target) {
                        var element = e.target;
                        var data = {
                            tagName: element.tagName,
                            id: element.id || '',
                            name: element.name || '',
                            className: element.className || '',
                            type: element.type || '',
                            value: element.value || '',
                            innerText: element.innerText || '',
                            timestamp: new Date().getTime(),
                            xpath: getXPath(element),
                            attributes: {}
                        };
                        
                        // Coletar atributos
                        for (var i = 0; i < element.attributes.length; i++) {
                            var attr = element.attributes[i];
                            data.attributes[attr.name] = attr.value;
                        }
                        
                        window._clickEvents.push(data);
                    }
                }, true);
                
                // Função para obter XPath
                function getXPath(element) {
                    if (element.id !== '') {
                        return '//*[@id="' + element.id + '"]';
                    }
                    if (element === document.body) {
                        return '/html/body';
                    }
                    var ix = 0;
                    var siblings = element.parentNode.childNodes;
                    for (var i = 0; i < siblings.length; i++) {
                        var sibling = siblings[i];
                        if (sibling === element) {
                            return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        }
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                            ix++;
                        }
                    }
                }
            }
            """
            
            # Script para monitorar inputs
            input_script = """
            if (typeof window._inputEvents === 'undefined') {
                window._inputEvents = [];
                
                document.addEventListener('change', function(e) {
                    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
                        var element = e.target;
                        var data = {
                            tagName: element.tagName,
                            id: element.id || '',
                            name: element.name || '',
                            className: element.className || '',
                            type: element.type || '',
                            value: element.value || '',
                            timestamp: new Date().getTime(),
                            xpath: getXPath(element),
                            attributes: {}
                        };
                        
                        // Coletar atributos
                        for (var i = 0; i < element.attributes.length; i++) {
                            var attr = element.attributes[i];
                            data.attributes[attr.name] = attr.value;
                        }
                        
                        window._inputEvents.push(data);
                    }
                }, true);
                
                // Função para obter XPath
                function getXPath(element) {
                    if (element.id !== '') {
                        return '//*[@id="' + element.id + '"]';
                    }
                    if (element === document.body) {
                        return '/html/body';
                    }
                    var ix = 0;
                    var siblings = element.parentNode.childNodes;
                    for (var i = 0; i < siblings.length; i++) {
                        var sibling = siblings[i];
                        if (sibling === element) {
                            return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        }
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                            ix++;
                        }
                    }
                }
            }
            """
            
            # Script para monitorar selects
            select_script = """
            if (typeof window._selectEvents === 'undefined') {
                window._selectEvents = [];
                
                document.addEventListener('change', function(e) {
                    if (e.target && e.target.tagName === 'SELECT') {
                        var element = e.target;
                        var selectedOption = element.options[element.selectedIndex];
                        var data = {
                            tagName: element.tagName,
                            id: element.id || '',
                            name: element.name || '',
                            className: element.className || '',
                            value: element.value || '',
                            selectedText: selectedOption ? selectedOption.text : '',
                            selectedIndex: element.selectedIndex,
                            timestamp: new Date().getTime(),
                            xpath: getXPath(element),
                            attributes: {}
                        };
                        
                        // Coletar atributos
                        for (var i = 0; i < element.attributes.length; i++) {
                            var attr = element.attributes[i];
                            data.attributes[attr.name] = attr.value;
                        }
                        
                        window._selectEvents.push(data);
                    }
                }, true);
                
                // Função para obter XPath
                function getXPath(element) {
                    if (element.id !== '') {
                        return '//*[@id="' + element.id + '"]';
                    }
                    if (element === document.body) {
                        return '/html/body';
                    }
                    var ix = 0;
                    var siblings = element.parentNode.childNodes;
                    for (var i = 0; i < siblings.length; i++) {
                        var sibling = siblings[i];
                        if (sibling === element) {
                            return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        }
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                            ix++;
                        }
                    }
                }
            }
            """
            
            # Injetar scripts
            self.driver.execute_script(click_script)
            self.driver.execute_script(input_script)
            self.driver.execute_script(select_script)
            
            # Registrar evento de injeção
            self.capture_queue.put(("log_debug", "Scripts de monitoramento injetados"))
            
        except Exception as e:
            self.capture_queue.put(("log_error", f"Erro ao injetar scripts: {str(e)}"))
    
    def _quit_driver(self):
        """Finaliza o driver do Selenium"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            finally:
                self.driver = None
    
    def _browser_back(self):
        """Navega para a página anterior"""
        if not self.driver:
            return
        
        try:
            self.driver.back()
        except:
            pass
    
    def _browser_forward(self):
        """Navega para a página seguinte"""
        if not self.driver:
            return
        
        try:
            self.driver.forward()
        except:
            pass
    
    def _browser_refresh(self):
        """Atualiza a página atual"""
        if not self.driver:
            return
        
        try:
            self.driver.refresh()
        except:
            pass
    
    def _navigate_to_url(self, event=None):
        """Navega para a URL especificada"""
        if not self.driver:
            return
        
        # Obter URL
        url = self.url_var.get().strip()
        if not url:
            return
        
        # Adicionar protocolo se necessário
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # Atualizar interface
        self.nav_status.config(text="Navegando...", bootstyle="warning")
        
        # Navegar em thread separada
        threading.Thread(target=self._navigate_thread, args=(url,), daemon=True).start()
    
    def _navigate_thread(self, url):
        """Thread para navegação"""
        try:
            # Navegar para URL
            self.driver.get(url)
            
            # Reinjetar scripts de monitoramento
            self._inject_monitoring_scripts()
            
            # Atualizar status
            self.capture_queue.put(("update_status", "Navegação concluída", "success"))
            
        except Exception as e:
            # Registrar erro
            self.capture_queue.put(("update_status", f"Erro: {str(e)}", "danger"))
    
    def _check_url_change(self):
        """Verifica se a URL atual mudou"""
        if not self.driver:
            return
        
        try:
            # Obter URL e título atuais
            current_url = self.driver.current_url
            current_title = self.driver.title
            
            # Verificar se mudou
            if current_url != self.current_url:
                # Atualizar variáveis
                old_url = self.current_url
                self.current_url = current_url
                self.current_title = current_title
                
                # Atualizar interface
                self.capture_queue.put(("update_url", current_url))
                
                # Registrar navegação
                self._add_navigation_event(old_url, current_url, current_title)
                
                # Reinjetar scripts de monitoramento
                self._inject_monitoring_scripts()
                
        except:
            pass
    
    def _check_browser_events(self):
        """Verifica eventos capturados pelo navegador"""
        if not self.driver:
            return
        
        try:
            # Verificar eventos de clique
            click_events = self.driver.execute_script("return window._clickEvents || [];")
            if click_events:
                # Limpar eventos no navegador
                self.driver.execute_script("window._clickEvents = [];")
                
                # Processar eventos
                for event in click_events:
                    self._add_click_event(event)
            
            # Verificar eventos de input
            input_events = self.driver.execute_script("return window._inputEvents || [];")
            if input_events:
                # Limpar eventos no navegador
                self.driver.execute_script("window._inputEvents = [];")
                
                # Processar eventos
                for event in input_events:
                    self._add_input_event(event)
            
            # Verificar eventos de select
            select_events = self.driver.execute_script("return window._selectEvents || [];")
            if select_events:
                # Limpar eventos no navegador
                self.driver.execute_script("window._selectEvents = [];")
                
                # Processar eventos
                for event in select_events:
                    self._add_select_event(event)
            
        except Exception as e:
            self.capture_queue.put(("log_error", f"Erro ao verificar eventos: {str(e)}"))
    
    def _add_navigation_event(self, from_url, to_url, title):
        """Adiciona um evento de navegação"""
        # Criar dados do evento
        event_data = {
            "type": "navigation",
            "from": from_url,
            "to": to_url,
            "title": title,
            "timestamp": int(time.time() * 1000)
        }
        
        # Adicionar à lista de ações
        self.captured_actions.append(event_data)
        
        # Adicionar à árvore de elementos
        self.capture_queue.put(("add_element", {
            "id": f"nav_{len(self.captured_actions)}",
            "text": to_url,
            "type": "Navegação",
            "value": title,
            "data": event_data
        }))
        
        # Log de depuração
        self.capture_queue.put(("log_debug", f"Navegação: {to_url}"))
    
    def _add_click_event(self, event_data):
        """Adiciona um evento de clique"""
        # Adicionar tipo
        event_data["type"] = "click"
        
        # Adicionar à lista de ações
        self.captured_actions.append(event_data)
        
        # Determinar texto para exibição
        display_text = event_data.get("innerText", "").strip()
        if not display_text and "value" in event_data and event_data["value"]:
            display_text = event_data["value"]
        if not display_text:
            display_text = event_data.get("tagName", "ELEMENT").lower()
        
        # Limitar tamanho do texto
        if len(display_text) > 30:
            display_text = display_text[:27] + "..."
        
        # Adicionar à árvore de elementos
        self.capture_queue.put(("add_element", {
            "id": f"click_{len(self.captured_actions)}",
            "text": display_text,
            "type": "Clique",
            "value": event_data.get("tagName", ""),
            "data": event_data
        }))
        
        # Log de depuração
        self.capture_queue.put(("log_debug", f"Clique: {display_text}"))
    
    def _add_input_event(self, event_data):
        """Adiciona um evento de input"""
        # Adicionar tipo
        event_data["type"] = "input"
        
        # Adicionar à lista de ações
        self.captured_actions.append(event_data)
        
        # Determinar texto para exibição
        display_text = event_data.get("name", "") or event_data.get("id", "")
        if not display_text:
            display_text = "Input"
        
        # Limitar tamanho do valor
        value = event_data.get("value", "")
        if len(value) > 30:
            value = value[:27] + "..."
        
        # Adicionar à árvore de elementos
        self.capture_queue.put(("add_element", {
            "id": f"input_{len(self.captured_actions)}",
            "text": display_text,
            "type": "Input",
            "value": value,
            "data": event_data
        }))
        
        # Log de depuração
        self.capture_queue.put(("log_debug", f"Input: {display_text} = {value}"))
    
    def _add_select_event(self, event_data):
        """Adiciona um evento de select"""
        # Adicionar tipo
        event_data["type"] = "select"
        
        # Adicionar à lista de ações
        self.captured_actions.append(event_data)
        
        # Determinar texto para exibição
        display_text = event_data.get("name", "") or event_data.get("id", "")
        if not display_text:
            display_text = "Select"
        
        # Adicionar à árvore de elementos
        self.capture_queue.put(("add_element", {
            "id": f"select_{len(self.captured_actions)}",
            "text": display_text,
            "type": "Select",
            "value": event_data.get("selectedText", ""),
            "data": event_data
        }))
        
        # Log de depuração
        self.capture_queue.put(("log_debug", f"Select: {display_text} = {event_data.get('selectedText', '')}"))
    
    def _capture_screenshot(self):
        """Captura screenshot da página atual"""
        if not self.driver:
            return
        
        try:
            # Capturar screenshot
            screenshot = self.driver.get_screenshot_as_png()
            
            # Converter para imagem
            image = Image.open(BytesIO(screenshot))
            
            # Redimensionar para caber na interface
            width, height = self.browser_frame.winfo_width(), self.browser_frame.winfo_height()
            if width > 1 and height > 1:  # Verificar se o frame já tem tamanho
                image = image.resize((width, height), Image.LANCZOS)
            
            # Converter para PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Atualizar interface
            self.capture_queue.put(("update_screenshot", photo))
            
            # Armazenar screenshot
            self.screenshot = screenshot
            
        except:
            pass
    
    def _process_queue(self):
        """Processa a fila de eventos da interface"""
        while self.queue_running:
            try:
                # Obter próximo evento (com timeout para não bloquear)
                event = self.capture_queue.get(timeout=0.1)
                
                # Processar evento
                if event[0] == "update_status":
                    self.nav_status.config(text=event[1], bootstyle=event[2])
                
                elif event[0] == "update_url":
                    self.url_var.set(event[1])
                
                elif event[0] == "update_screenshot":
                    self.screenshot_label.config(image=event[1])
                    self.screenshot_label.image = event[1]  # Manter referência
                
                elif event[0] == "update_buttons":
                    if event[1] == "stopped":
                        self.start_button.config(state="normal")
                        self.stop_button.config(state="disabled")
                        self.export_button.config(state="normal")
                    elif event[1] == "error":
                        self.start_button.config(state="normal")
                        self.stop_button.config(state="disabled")
                        if self.captured_actions:
                            self.export_button.config(state="normal")
                
                elif event[0] == "update_nav_buttons":
                    if event[1] == "enabled":
                        self.back_button.config(state="normal")
                        self.forward_button.config(state="normal")
                        self.refresh_button.config(state="normal")
                        self.go_button.config(state="normal")
                    else:
                        self.back_button.config(state="disabled")
                        self.forward_button.config(state="disabled")
                        self.refresh_button.config(state="disabled")
                        self.go_button.config(state="disabled")
                
                elif event[0] == "add_element":
                    self._add_element_to_tree(event[1])
                
                elif event[0] == "log_debug":
                    print(f"[DEBUG] {event[1]}")
                
                elif event[0] == "log_error":
                    print(f"[ERROR] {event[1]}")
                
                # Marcar evento como processado
                self.capture_queue.task_done()
                
            except queue.Empty:
                # Timeout, continuar loop
                pass
            except Exception as e:
                print(f"Erro ao processar fila: {str(e)}")
    
    def _add_element_to_tree(self, element):
        """Adiciona um elemento à árvore de elementos"""
        # Verificar filtro atual
        filter_value = self.filter_var.get()
        if filter_value != "Todos" and element["type"] != filter_value:
            return
        
        # Adicionar à árvore
        self.elements_tree.insert(
            "",
            "end",
            iid=element["id"],
            text=element["text"],
            values=(element["type"], element["value"]),
            tags=(element["type"].lower(),)
        )
        
        # Configurar cores
        self.elements_tree.tag_configure("navegação", foreground="#4caf50")
        self.elements_tree.tag_configure("clique", foreground="#2196f3")
        self.elements_tree.tag_configure("input", foreground="#ff9800")
        self.elements_tree.tag_configure("select", foreground="#9c27b0")
        self.elements_tree.tag_configure("rede", foreground="#f44336")
    
    def filter_elements(self, event=None):
        """Filtra os elementos exibidos na árvore"""
        # Obter filtro
        filter_value = self.filter_var.get()
        
        # Limpar árvore
        self.elements_tree.delete(*self.elements_tree.get_children())
        
        # Adicionar elementos filtrados
        for action in self.captured_actions:
            action_type = action.get("type", "").capitalize()
            
            # Verificar filtro
            if filter_value != "Todos" and action_type != filter_value:
                continue
            
            # Determinar texto e valor para exibição
            if action_type == "Navigation":
                text = action.get("to", "")
                value = action.get("title", "")
            elif action_type == "Click":
                text = action.get("innerText", "").strip() or action.get("value", "") or action.get("tagName", "").lower()
                value = action.get("tagName", "")
            elif action_type == "Input":
                text = action.get("name", "") or action.get("id", "") or "Input"
                value = action.get("value", "")
            elif action_type == "Select":
                text = action.get("name", "") or action.get("id", "") or "Select"
                value = action.get("selectedText", "")
            else:
                text = action_type
                value = ""
            
            # Limitar tamanho do texto
            if len(text) > 30:
                text = text[:27] + "..."
            if len(value) > 30:
                value = value[:27] + "..."
            
            # Adicionar à árvore
            self.elements_tree.insert(
                "",
                "end",
                text=text,
                values=(action_type, value),
                tags=(action_type.lower(),)
            )
    
    def show_element_details(self, event=None):
        """Exibe os detalhes do elemento selecionado"""
        # Obter item selecionado
        selected = self.elements_tree.selection()
        if not selected:
            return
        
        # Obter ID do item
        item_id = selected[0]
        
        # Encontrar dados do elemento
        element_data = None
        for action in self.captured_actions:
            if f"{action.get('type', '')}_{self.captured_actions.index(action) + 1}" == item_id:
                element_data = action
                break
        
        if not element_data:
            return
        
        # Formatar JSON
        json_str = json.dumps(element_data, indent=2)
        
        # Atualizar texto de detalhes
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", json_str)
        self.details_text.config(state="disabled")
