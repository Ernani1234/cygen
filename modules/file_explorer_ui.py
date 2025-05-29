import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog
from pathlib import Path
from modules.structure_generator import StructureGenerator
from modules.ai_file_api import list_directory_api, read_file_api, create_directory_api # Import specific functions

class FileExplorerUI:
    def __init__(self, master):
        self.master = master
        master.title("Cypress Test Generator & File Explorer")
        self.base_display_path = Path("./generated_test_structure")
        self.base_display_path.mkdir(parents=True, exist_ok=True) # Ensure it exists on startup

        # Main PanedWindow for resizable sections
        main_paned_window = ttk.PanedWindow(master, orient=tk.HORIZONTAL)
        main_paned_window.pack(fill=tk.BOTH, expand=True)

        # Left Pane: File Explorer Tree
        explorer_frame = ttk.LabelFrame(main_paned_window, text="File Explorer", padding=(5,5))
        main_paned_window.add(explorer_frame, weight=1)

        self.tree = ttk.Treeview(explorer_frame, selectmode="browse") # browse selectmode
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        explorer_scrollbar = ttk.Scrollbar(explorer_frame, orient="vertical", command=self.tree.yview)
        explorer_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.tree.configure(yscrollcommand=explorer_scrollbar.set)

        # Right Pane: File Content Viewer / Controls
        right_pane_frame = ttk.Frame(main_paned_window)
        main_paned_window.add(right_pane_frame, weight=2)
        
        # Control Buttons Frame (Generate, Refresh)
        controls_frame = ttk.Frame(right_pane_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)

        self.generate_button = ttk.Button(controls_frame,
                                          text="Generate Cypress Structure",
                                          command=self.handle_generate_structure)
        self.generate_button.pack(pady=2, side=tk.LEFT)

        self.refresh_button = ttk.Button(controls_frame,
                                         text="Refresh Explorer",
                                         command=self.refresh_file_explorer_view)
        self.refresh_button.pack(pady=2, side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(controls_frame, text="Status: Ready")
        self.status_label.pack(pady=2, side=tk.LEFT, padx=5)

        # File Content Display Area
        content_frame = ttk.LabelFrame(right_pane_frame, text="File Content", padding=(5,5))
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.file_content_text = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.file_content_text.pack(fill=tk.BOTH, expand=True)

        # AI Command Section (moved to bottom of right pane)
        ai_frame = ttk.LabelFrame(right_pane_frame, text="AI Command Interface", padding=(10, 5))
        ai_frame.pack(fill=tk.X, padx=5, pady=5, side=tk.BOTTOM)

        self.ai_command_input = ttk.Entry(ai_frame, width=50) # Adjusted width
        self.ai_command_input.pack(side=tk.LEFT, padx=(0, 5), expand=True, fill=tk.X)
        
        self.execute_ai_button = ttk.Button(ai_frame, 
                                             text="Execute AI Cmd", # Shortened text
                                             command=self.handle_ai_command)
        self.execute_ai_button.pack(side=tk.LEFT)

        self.refresh_file_explorer_view() # Initial population of file explorer

    def on_tree_select(self, event=None):
        selected_item_id = self.tree.focus() # Get selected item
        if not selected_item_id:
            return

        item_data = self.tree.item(selected_item_id)
        tags = item_data.get("tags", [])
        
        self.file_content_text.config(state=tk.NORMAL)
        self.file_content_text.delete(1.0, tk.END)

        if "file" in tags:
            file_path = item_data.get("values")[0] # Assuming path is stored in values
            if file_path:
                self.status_label.config(text=f"Status: Reading {Path(file_path).name}...")
                result = read_file_api(str(file_path))
                if result["success"]:
                    self.file_content_text.insert(tk.END, result["content"])
                    self.status_label.config(text=f"Status: Displaying {Path(file_path).name}")
                else:
                    self.file_content_text.insert(tk.END, f"Error reading file:\n{result['error']}")
                    self.status_label.config(text=f"Status: Error reading {Path(file_path).name}")
            else:
                self.file_content_text.insert(tk.END, "No path associated with this file item.")
        elif "directory" in tags:
            self.file_content_text.insert(tk.END, f"Selected directory: {item_data['text']}\n\n(Select a file to view its content)")
        
        self.file_content_text.config(state=tk.DISABLED)


    def handle_ai_command(self):
        command_text = self.ai_command_input.get().strip()
        if not command_text:
            self.status_label.config(text="Status: AI command is empty.")
            print("AI Command input: [EMPTY]")
            return

        self.status_label.config(text=f"Status: AI Command Received: '{command_text[:30]}...'")
        print(f"AI Command input: '{command_text}'")

        # Placeholder for AI parsing and execution
        # For now, just simulate based on keywords
        if "create file" in command_text.lower():
            feedback = "Simulation: Would call `create_file_api` with parsed parameters."
            # Example: ai_file_api.create_file_api("path/to/file.txt", "content")
        elif "read file" in command_text.lower():
            feedback = "Simulation: Would call `read_file_api` with parsed parameters."
            # Example: ai_file_api.read_file_api("path/to/file.txt")
        elif "update file" in command_text.lower():
            feedback = "Simulation: Would call `update_file_api` with parsed parameters."
        elif "delete file" in command_text.lower():
            feedback = "Simulation: Would call `delete_file_api` with parsed parameters."
        elif "create directory" in command_text.lower():
            feedback = "Simulation: Would call `create_directory_api` with parsed parameters."
        elif "delete directory" in command_text.lower():
            feedback = "Simulation: Would call `delete_directory_api` with parsed parameters."
        else:
            feedback = "Simulation: AI command not recognized by simple keyword matching."
        
        print(feedback)
        self.status_label.config(text=f"Status: {feedback}")
        self.ai_command_input.delete(0, tk.END) # Clear the input field

    def handle_generate_structure(self):
        self.status_label.config(text="Status: Generating structure...")
        generator = StructureGenerator()
        base_path_str = "./generated_test_structure" 
        # Ensure base_path itself exists for the generator to build upon
        Path(base_path_str).mkdir(parents=True, exist_ok=True)

        print(f"Attempting to generate structure in: {Path(base_path_str).resolve()}")

        # 1. Generate base directory structure
        success, _, errors = generator.generate_cypress_structure(base_path_str)
        if not success:
            message = f"Failed to generate base structure. Errors: {errors}"
            print(message)
            self.status_label.config(text=f"Status: Error - {message}")
            return

        # 2. Create a fixture file
        fixture_content = {"user": "test_user", "password": "password123"}
        generator.create_fixture_file(base_path_str, "example_fixture", fixture_content)

        # 3. Create an E2E spec file
        spec_content = "it('should demonstrate a basic test', () => { cy.visit('/'); });"
        generator.create_e2e_spec_file(base_path_str, "example_spec", "Example Test Suite", spec_content)

        # 4. Create a support command
        command_content = "// Example custom command\nCypress.Commands.add('login', (username, password) => { /* ... */ });"
        generator.create_support_command(base_path_str, "example_command", command_content)
        
        # 5. Create a helper file
        helper_content = "// Example helper function\nexport function greet(name) { return `Hello, ${name}`;} "
        generator.create_helper_file(base_path_str, "example_helper", helper_content)
        
        completion_message = f"Structure and sample files generated in '{Path(base_path_str).resolve()}'"
        print(completion_message)
        self.status_label.config(text=f"Status: {completion_message}")
        # For now, we don't auto-refresh the treeview. User would need to restart or manually check.
        # Future enhancement: self.refresh_treeview(base_path_str)


    def populate_treeview(self):
        # Clear existing items (if any)
        for i in self.tree.get_children():
            self.tree.delete(i)
            
        # Placeholder data representing a file structure
        file_structure = {
            "Dir1": {
                "file1.txt": None,
                "file2.txt": None,
                "SubDir1": {
                    "file3.txt": None
                }
            },
            "Dir2": {
                "file4.txt": None
            },
            "file5.txt": None
        }

        self.insert_items("", file_structure)

    def insert_items(self, parent_node, structure):
        for name, content in structure.items():
            if content is None:  # It's a file
                self.tree.insert(parent_node, "end", text=name, open=False, values=("file",))
            else:  # It's a directory
                node = self.tree.insert(parent_node, "end", text=name, open=False, values=("directory",))
                self.insert_items(node, content)

    def run(self):
        self.master.mainloop()

if __name__ == '__main__':
    root = tk.Tk()
    app = FileExplorerUI(root)
    app.run()
