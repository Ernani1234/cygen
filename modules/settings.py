"""
Módulo para gerenciamento de configurações do sistema.
"""

import os
import json

class SettingsManager:
    """
    Gerencia as configurações do sistema.
    """
    
    def __init__(self):
        """
        Inicializa o gerenciador de configurações.
        """
        self.config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
        self.config_file = os.path.join(self.config_dir, "settings.json")
        
        # Criar diretório de configurações se não existir
        os.makedirs(self.config_dir, exist_ok=True)
    
    def load_settings(self):
        """
        Carrega as configurações do arquivo.
        
        Returns:
            dict: Configurações carregadas
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                # Se houver erro ao carregar, retorna configurações padrão
                return self.get_default_settings()
        else:
            # Se o arquivo não existir, cria com configurações padrão
            default_settings = self.get_default_settings()
            self.save_settings(default_settings)
            return default_settings
    
    def save_settings(self, settings):
        """
        Salva as configurações no arquivo.
        
        Args:
            settings: Configurações a serem salvas
        
        Returns:
            bool: True se as configurações foram salvas com sucesso, False caso contrário
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            return True
        except Exception:
            return False
    
    def get_default_settings(self):
        """
        Retorna as configurações padrão.
        
        Returns:
            dict: Configurações padrão
        """
        return {
            # Configurações gerais
            "default_timeout": 5000,
            "use_conditional_waits": True,
            "verify_visibility": True,
            "capture_network": True,
            "network_capture_interval": 500,
            
            # Configurações de API
            "ai_edit_api_endpoint": "https://api.openai.com/v1/chat/completions",
            "ai_edit_model": "gpt-3.5-turbo",
            "api_key": "",
            "max_api_requests": 10,
            "cost_pattern": "1,385 requests(6,024,231 tokens) = $6.94(dollar)",
            
            # Configurações de seletores
            "selector_priority": [
                "data-cy", 
                "data-testid", 
                "id", 
                "name", 
                "role", 
                "aria-label", 
                "class", 
                "tag", 
                "type"
            ],
            "selector_enabled": {
                "data-cy": True,
                "data-testid": True,
                "id": True,
                "name": True,
                "role": True,
                "aria-label": True,
                "class": True,
                "tag": True,
                "type": True
            },
            
            # Configurações de aparência
            "theme": "darkly",
            "font_size": 12,
            "code_font": "Consolas",
            
            # Configurações de teste
            "test_template": "default",
            "auto_import_helpers": True,
            "auto_generate_fixtures": True,
            "use_typescript": False,
            
            # Configurações de captura
            "highlight_elements": True,
            "auto_scroll": True,
            "capture_screenshots": True,
            "screenshot_format": "png"
        }
