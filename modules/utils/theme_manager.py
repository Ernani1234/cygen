"""
Módulo para gerenciamento de temas da aplicação.
"""

import ttkbootstrap as ttk

class ThemeManager:
    """
    Gerencia os temas da aplicação.
    """
    
    def __init__(self, style):
        """
        Inicializa o gerenciador de temas.
        
        Args:
            style: Objeto de estilo do ttkbootstrap
        """
        self.style = style
        self.current_theme = style.theme.name
    
    def get_available_themes(self):
        """
        Retorna a lista de temas disponíveis.
        
        Returns:
            list: Lista de temas disponíveis
        """
        # Corrigido: Chamando o método na instância, não na classe
        return self.style.theme_names()
    
    def set_theme(self, theme_name):
        """
        Define o tema atual.
        
        Args:
            theme_name: Nome do tema a ser definido
        
        Returns:
            bool: True se o tema foi definido com sucesso, False caso contrário
        """
        try:
            self.style.theme_use(theme_name)
            self.current_theme = theme_name
            return True
        except Exception:
            return False
    
    def get_current_theme(self):
        """
        Retorna o tema atual.
        
        Returns:
            str: Nome do tema atual
        """
        return self.current_theme
    
    def get_theme_colors(self):
        """
        Retorna as cores do tema atual.
        
        Returns:
            dict: Dicionário com as cores do tema
        """
        colors = {
            "background": self.style.colors.bg,
            "foreground": self.style.colors.fg,
            "primary": self.style.colors.primary,
            "secondary": self.style.colors.secondary,
            "success": self.style.colors.success,
            "info": self.style.colors.info,
            "warning": self.style.colors.warning,
            "danger": self.style.colors.danger,
            "light": self.style.colors.light,
            "dark": self.style.colors.dark
        }
        
        return colors
