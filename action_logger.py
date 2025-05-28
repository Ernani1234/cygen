"""
Módulo para captura de elementos e ações do usuário no navegador.
Implementa registro detalhado de todas as interações e requisições de rede.
"""

import os
import json
import time
import datetime
import threading
import queue
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

class EnhancedWebDriver:
    """
    Wrapper para o WebDriver do Selenium com funcionalidades adicionais
    de logging e captura de elementos.
    """
    
    def __init__(self, driver, flow_name):
        """
        Inicializa o driver aprimorado.
        
        Args:
            driver: Instância do WebDriver do Selenium
            flow_name: Nome do fluxo para identificação nos logs
        """
        self.driver = driver
        self.flow_name = flow_name
        self.start_time = time.time()
        self.actions = []
        self.network_requests = []
        self.elements_cache = {}
        self.logging_active = True
        self.log_path = None
        
        # Criar diretório de logs se não existir
        self.logs_dir = "logs"
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)
        
        # Iniciar captura de eventos
        self._setup_event_listeners()
        
        # Iniciar thread de captura de rede
        self.network_capture_thread = threading.Thread(target=self._capture_network_requests, daemon=True)
        self.network_capture_thread.start()
        
        # Registrar início da sessão
        self._log_action({
            "type": "session_start",
            "timestamp": self._get_timestamp(),
            "elapsed_time": 0,
            "details": {
                "flow_name": flow_name,
                "user_agent": self.driver.execute_script("return navigator.userAgent;"),
                "window_size": self.driver.get_window_size()
            }
        })
    
    def get_driver(self):
        """Retorna o driver Selenium original"""
        return self.driver
    
    def _setup_event_listeners(self):
        """Configura os listeners de eventos JavaScript para capturar interações do usuário"""
        # Injetar script para monitorar cliques
        click_script = """
        (function() {
            window.addEventListener('click', function(e) {
                var target = e.target;
                var data = {
                    type: 'click',
                    timestamp: new Date().getTime(),
                    element: {
                        tag: target.tagName,
                        id: target.id,
                        class: target.className,
                        text: target.textContent.trim().substring(0, 50),
                        attributes: {}
                    },
                    position: {
                        x: e.clientX,
                        y: e.clientY
                    }
                };
                
                // Capturar atributos relevantes
                ['data-cy', 'data-testid', 'name', 'type', 'role', 'aria-label'].forEach(function(attr) {
                    if (target.hasAttribute(attr)) {
                        data.element.attributes[attr] = target.getAttribute(attr);
                    }
                });
                
                // Enviar para o Selenium
                window.seleniumClickEvents = window.seleniumClickEvents || [];
                window.seleniumClickEvents.push(data);
            }, true);
        })();
        """
        self.driver.execute_script(click_script)
        
        # Injetar script para monitorar inputs
        input_script = """
        (function() {
            var inputElements = document.querySelectorAll('input, textarea, select');
            
            function handleInput(e) {
                var target = e.target;
                var data = {
                    type: 'input',
                    timestamp: new Date().getTime(),
                    element: {
                        tag: target.tagName,
                        id: target.id,
                        class: target.className,
                        attributes: {}
                    },
                    value: target.value
                };
                
                // Capturar atributos relevantes
                ['data-cy', 'data-testid', 'name', 'type', 'role', 'aria-label', 'placeholder'].forEach(function(attr) {
                    if (target.hasAttribute(attr)) {
                        data.element.attributes[attr] = target.getAttribute(attr);
                    }
                });
                
                // Enviar para o Selenium
                window.seleniumInputEvents = window.seleniumInputEvents || [];
                window.seleniumInputEvents.push(data);
            }
            
            // Adicionar listeners para todos os elementos de input
            inputElements.forEach(function(element) {
                element.addEventListener('change', handleInput);
                element.addEventListener('blur', handleInput);
            });
            
            // Observar novos elementos adicionados ao DOM
            var observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.addedNodes) {
                        mutation.addedNodes.forEach(function(node) {
                            if (node.nodeType === 1) { // Elemento
                                var newInputs = node.querySelectorAll('input, textarea, select');
                                newInputs.forEach(function(element) {
                                    element.addEventListener('change', handleInput);
                                    element.addEventListener('blur', handleInput);
                                });
                            }
                        });
                    }
                });
            });
            
            observer.observe(document.body, { childList: true, subtree: true });
        })();
        """
        self.driver.execute_script(input_script)
    
    def _capture_network_requests(self):
        """Thread para capturar requisições de rede"""
        while self.logging_active:
            try:
                # Capturar logs de performance
                logs = self.driver.get_log('performance')
                
                for entry in logs:
                    try:
                        # Converter string para objeto
                        log = json.loads(entry['message'])['message']
                        
                        # Filtrar apenas eventos de rede
                        if 'Network.responseReceived' in log['method'] or 'Network.requestWillBeSent' in log['method']:
                            request_id = log['params'].get('requestId')
                            request = log['params'].get('request', {})
                            response = log['params'].get('response', {})
                            
                            if request_id and (request or response):
                                # Registrar requisição
                                self.network_requests.append({
                                    'request_id': request_id,
                                    'url': request.get('url') or response.get('url'),
                                    'method': request.get('method'),
                                    'status': response.get('status'),
                                    'timestamp': self._get_timestamp(),
                                    'elapsed_time': self._get_elapsed_time(),
                                    'type': log['method']
                                })
                    except (json.JSONDecodeError, KeyError):
                        continue
            except Exception:
                # Ignorar erros na captura de logs
                pass
            
            # Aguardar antes da próxima captura
            time.sleep(0.5)
    
    def _collect_click_events(self):
        """Coleta eventos de clique registrados pelo JavaScript"""
        try:
            events = self.driver.execute_script("return window.seleniumClickEvents || [];")
            # Limpar eventos após coleta
            self.driver.execute_script("window.seleniumClickEvents = [];")
            return events
        except Exception:
            return []
    
    def _collect_input_events(self):
        """Coleta eventos de input registrados pelo JavaScript"""
        try:
            events = self.driver.execute_script("return window.seleniumInputEvents || [];")
            # Limpar eventos após coleta
            self.driver.execute_script("window.seleniumInputEvents = [];")
            return events
        except Exception:
            return []
    
    def _process_events(self):
        """Processa eventos coletados e os adiciona ao log"""
        # Processar eventos de clique
        click_events = self._collect_click_events()
        for event in click_events:
            self._log_action({
                "type": "click",
                "timestamp": self._get_timestamp(),
                "elapsed_time": self._get_elapsed_time(),
                "element": event.get("element", {}),
                "position": event.get("position", {})
            })
        
        # Processar eventos de input
        input_events = self._collect_input_events()
        for event in input_events:
            self._log_action({
                "type": "input",
                "timestamp": self._get_timestamp(),
                "elapsed_time": self._get_elapsed_time(),
                "element": event.get("element", {}),
                "value": event.get("value", "")
            })
    
    def _log_action(self, action_data):
        """Registra uma ação no log"""
        if not self.logging_active:
            return
        
        # Adicionar URL atual
        try:
            action_data["url"] = self.driver.current_url
        except:
            action_data["url"] = "unknown"
        
        # Adicionar título da página
        try:
            action_data["page_title"] = self.driver.title
        except:
            action_data["page_title"] = "unknown"
        
        # Adicionar à lista de ações
        self.actions.append(action_data)
    
    def _get_timestamp(self):
        """Retorna timestamp atual no formato ISO"""
        return datetime.datetime.now().isoformat()
    
    def _get_elapsed_time(self):
        """Retorna tempo decorrido desde o início da sessão em segundos"""
        return round(time.time() - self.start_time, 2)
    
    def _capture_page_state(self):
        """Captura o estado atual da página"""
        try:
            # Capturar HTML
            html = self.driver.page_source
            
            # Analisar com BeautifulSoup para identificar elementos interativos
            soup = BeautifulSoup(html, 'html.parser')
            
            # Encontrar elementos interativos
            interactive_elements = []
            
            # Botões
            for button in soup.find_all(['button', 'input']):
                if button.name == 'input' and button.get('type') not in ['submit', 'button', 'reset']:
                    continue
                
                element_data = {
                    'tag': button.name,
                    'text': button.text.strip() if button.text else '',
                    'attributes': {}
                }
                
                # Capturar atributos relevantes
                for attr in ['id', 'class', 'name', 'type', 'data-cy', 'data-testid', 'role', 'aria-label']:
                    if button.has_attr(attr):
                        element_data['attributes'][attr] = button[attr]
                
                interactive_elements.append({
                    'type': 'button',
                    'data': element_data
                })
            
            # Links
            for link in soup.find_all('a'):
                element_data = {
                    'tag': 'a',
                    'text': link.text.strip() if link.text else '',
                    'attributes': {
                        'href': link.get('href', '')
                    }
                }
                
                # Capturar atributos relevantes
                for attr in ['id', 'class', 'name', 'data-cy', 'data-testid', 'role', 'aria-label']:
                    if link.has_attr(attr):
                        element_data['attributes'][attr] = link[attr]
                
                interactive_elements.append({
                    'type': 'link',
                    'data': element_data
                })
            
            # Inputs
            for input_elem in soup.find_all(['input', 'textarea', 'select']):
                if input_elem.name == 'input' and input_elem.get('type') in ['submit', 'button', 'reset']:
                    continue
                
                element_data = {
                    'tag': input_elem.name,
                    'attributes': {}
                }
                
                # Capturar atributos relevantes
                for attr in ['id', 'class', 'name', 'type', 'placeholder', 'data-cy', 'data-testid', 'role', 'aria-label']:
                    if input_elem.has_attr(attr):
                        element_data['attributes'][attr] = input_elem[attr]
                
                interactive_elements.append({
                    'type': 'input',
                    'data': element_data
                })
            
            # Registrar estado da página
            self._log_action({
                "type": "page_state",
                "timestamp": self._get_timestamp(),
                "elapsed_time": self._get_elapsed_time(),
                "interactive_elements": interactive_elements
            })
            
        except Exception as e:
            # Registrar erro na captura
            self._log_action({
                "type": "error",
                "timestamp": self._get_timestamp(),
                "elapsed_time": self._get_elapsed_time(),
                "error": str(e),
                "context": "capture_page_state"
            })
    
    def stop_logging(self):
        """Para o logging e salva os dados coletados"""
        if not self.logging_active:
            return self.log_path
        
        # Processar eventos pendentes
        self._process_events()
        
        # Capturar estado final da página
        self._capture_page_state()
        
        # Registrar fim da sessão
        self._log_action({
            "type": "session_end",
            "timestamp": self._get_timestamp(),
            "elapsed_time": self._get_elapsed_time(),
            "details": {
                "total_actions": len(self.actions),
                "total_network_requests": len(self.network_requests)
            }
        })
        
        # Desativar logging
        self.logging_active = False
        
        # Preparar dados para salvar
        log_data = {
            "flow_name": self.flow_name,
            "start_time": self.actions[0]["timestamp"] if self.actions else self._get_timestamp(),
            "end_time": self._get_timestamp(),
            "total_duration": self._get_elapsed_time(),
            "actions": self.actions,
            "network_requests": self.network_requests
        }
        
        # Gerar nome de arquivo baseado no fluxo e timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.flow_name.replace(' ', '_')}_{timestamp}.json"
        self.log_path = os.path.join(self.logs_dir, filename)
        
        # Salvar arquivo de log
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        return self.log_path
    
    def get_actions_summary(self):
        """Retorna um resumo das ações registradas"""
        # Contar tipos de ações
        action_types = {}
        for action in self.actions:
            action_type = action.get("type", "unknown")
            action_types[action_type] = action_types.get(action_type, 0) + 1
        
        # Preparar resumo
        summary = {
            "total_actions": len(self.actions),
            "total_network_requests": len(self.network_requests),
            "clicks": action_types.get("click", 0),
            "inputs": action_types.get("input", 0),
            "navigations": action_types.get("navigation", 0),
            "errors": action_types.get("error", 0)
        }
        
        return summary

def create_enhanced_driver(driver, flow_name):
    """
    Cria e retorna uma instância do EnhancedWebDriver.
    
    Args:
        driver: Instância do WebDriver do Selenium
        flow_name: Nome do fluxo para identificação nos logs
    
    Returns:
        EnhancedWebDriver: Driver aprimorado com funcionalidades de logging
    """
    return EnhancedWebDriver(driver, flow_name)

def get_available_logs():
    """
    Retorna uma lista de arquivos de log disponíveis.
    
    Returns:
        list: Lista de caminhos para arquivos de log
    """
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        return []
    
    log_files = []
    for filename in os.listdir(logs_dir):
        if filename.endswith(".json"):
            log_files.append(os.path.join(logs_dir, filename))
    
    # Ordenar por data de modificação (mais recente primeiro)
    log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    return log_files
