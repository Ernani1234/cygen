"""
Módulo para exibir tooltips em widgets Tkinter.
Fornece uma classe ToolTip para criar tooltips personalizados.
"""

import tkinter as tk
import ttkbootstrap as ttk

class ToolTip:
    """
    Classe para criar tooltips personalizados para widgets Tkinter.
    """
    
    def __init__(self, widget, text, delay=500, wrap_length=300, background="#282a36", foreground="#f8f8f2"):
        """
        Inicializa um tooltip para um widget.
        
        Args:
            widget: Widget ao qual o tooltip será associado
            text: Texto do tooltip
            delay: Tempo em milissegundos antes de exibir o tooltip
            wrap_length: Comprimento máximo de linha para quebra de texto
            background: Cor de fundo do tooltip
            foreground: Cor do texto do tooltip
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wrap_length = wrap_length
        self.background = background
        self.foreground = foreground
        
        self.tooltip_window = None
        self.id = None
        
        # Vincular eventos
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)
    
    def schedule(self, event=None):
        """Agenda a exibição do tooltip após o delay"""
        self.hide()
        self.id = self.widget.after(self.delay, self.show)
    
    def show(self):
        """Exibe o tooltip"""
        # Obter posição do widget
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Criar janela do tooltip
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        # Criar frame e label
        frame = ttk.Frame(
            self.tooltip_window, 
            padding=5, 
            borderwidth=1, 
            relief="solid"
        )
        frame.pack(fill=tk.BOTH, expand=True)
        
        label = ttk.Label(
            frame, 
            text=self.text, 
            wraplength=self.wrap_length,
            justify=tk.LEFT,
            background=self.background,
            foreground=self.foreground
        )
        label.pack()
    
    def hide(self, event=None):
        """Oculta o tooltip"""
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def update_text(self, text):
        """Atualiza o texto do tooltip"""
        self.text = text
        # Se o tooltip estiver visível, atualizar o texto
        if self.tooltip_window:
            for child in self.tooltip_window.winfo_children():
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, ttk.Label):
                        grandchild.config(text=text)

def add_tooltip(widget, text, delay=500, wrap_length=300):
    """
    Função auxiliar para adicionar um tooltip a um widget.
    
    Args:
        widget: Widget ao qual o tooltip será associado
        text: Texto do tooltip
        delay: Tempo em milissegundos antes de exibir o tooltip
        wrap_length: Comprimento máximo de linha para quebra de texto
        
    Returns:
        ToolTip: Instância do tooltip criado
    """
    return ToolTip(widget, text, delay, wrap_length)
