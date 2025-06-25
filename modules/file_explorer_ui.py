import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog
from pathlib import Path
# Update import: remove StructureGenerator, add initiate_cypress_structure_generation
from modules.structure_generator import initiate_cypress_structure_generation 
from modules.ai_file_api import list_directory_api, read_file_api, create_directory_api

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
            # Check if it's the "go up" directory ("..")
            if "parent_dir" in tags:
                parent_dir_path = item_data.get("values")[0]
                self.refresh_file_explorer_view(directory_to_list=parent_dir_path)
            else: # It's a normal directory, try to navigate into it
                directory_path_tuple = item_data.get("values")
                if directory_path_tuple:
                    actual_directory_path = directory_path_tuple[0]
                    self.refresh_file_explorer_view(directory_to_list=actual_directory_path)
                else:
                    # Fallback if path is not in values (should ideally not happen)
                    directory_name = item_data['text']
                    self.file_content_text.insert(tk.END, f"Cannot navigate to directory: {directory_name}\nPath not available.")
        
        self.file_content_text.config(state=tk.DISABLED)


    def handle_ai_command(self):
        command_text = self.ai_command_input.get().strip()
        if not command_text:
            self.status_label.config(text="Status: AI command is empty.")
            print("AI Command input: [EMPTY]")
            return

        self.status_label.config(text=f"Status: AI Cmd: '{command_text[:30]}...'") # Changed from "AI Command Received"
        print(f"AI Command input: '{command_text}'")

        # Keyword-based dispatch (very basic)
        feedback = f"AI command '{command_text}' received. "
        processed = False
        api_result = None # Initialize api_result to avoid NameError
        
        # Example: "create directory /path/to/new_dir"
        if command_text.lower().startswith("create directory "):
            try:
                path_to_create = command_text.split(" ", 2)[2]
                # All AI API calls should ideally operate relative to base_display_path or be absolute
                # For "create directory", let's make it relative to base_display_path for now
                api_result = create_directory_api(str(self.base_display_path / path_to_create))
                feedback += f"Attempted dir creation: {api_result.get('message') or api_result.get('error')}"
                if api_result["success"]: 
                    self.refresh_file_explorer_view()
                processed = True
            except IndexError:
                feedback += "Error: Path for 'create directory' not specified correctly."
            except Exception as e:
                feedback += f"Error processing 'create directory': {e}"
            
            if api_result and not api_result["success"]:
                 self.status_label.config(text=f"Status: Error - {api_result.get('error', 'Unknown error')}")
            elif api_result and api_result["success"]:
                 self.status_label.config(text=f"Status: {api_result.get('message', 'Success')}")
            else: # if api_result is None or other issues
                self.status_label.config(text=f"Status: {feedback}")


        elif "create file" in command_text.lower(): 
            feedback += "Simulation: Would call `create_file_api` (needs path & content)."
            processed = True
            self.status_label.config(text=f"Status: {feedback}")
        elif "read file" in command_text.lower(): 
            feedback += "Simulation: Would call `read_file_api` (needs path)."
            processed = True
            self.status_label.config(text=f"Status: {feedback}")
        elif "update file" in command_text.lower():
            feedback += "Simulation: Would call `update_file_api` (needs path & content)."
            processed = True
            self.status_label.config(text=f"Status: {feedback}")
        elif "delete file" in command_text.lower():
            feedback += "Simulation: Would call `delete_file_api` (needs path)."
            processed = True
            self.status_label.config(text=f"Status: {feedback}")
        elif "delete directory" in command_text.lower():
            feedback += "Simulation: Would call `delete_directory_api` (needs path)."
            processed = True
            self.status_label.config(text=f"Status: {feedback}")
        
        if not processed: # If no specific keywords matched
            feedback += "No specific action recognized by keyword parser."
            self.status_label.config(text=f"Status: {feedback}")
        
        print(feedback)
        self.ai_command_input.delete(0, tk.END)

    def handle_generate_structure(self):
        self.status_label.config(text="Status: Generating structure...")
        
        # Ensure base_path itself exists
        self.base_display_path.mkdir(parents=True, exist_ok=True)
        
        ui_test_name = "ui_generated_test" # Default test name for UI initiated generation
        print(f"Attempting to generate structure for '{ui_test_name}' in: {self.base_display_path.resolve()}")

        try:
            # Call the new centralized function from structure_generator module
            generated_path_str = initiate_cypress_structure_generation(
                base_output_path=str(self.base_display_path), 
                test_name=ui_test_name
            )
            # The initiate_cypress_structure_generation function prints its own completion message.
            completion_message = f"Structure for '{ui_test_name}' generated in: {generated_path_str}"
            print(f"UI: {completion_message}") # Console log from UI
            self.status_label.config(text=f"Status: {completion_message}")
        except Exception as e:
            # Catching potential errors from the generation process
            error_message = f"Error during structure generation: {e}"
            print(error_message) # Log detailed error to console
            self.status_label.config(text=f"Status: Generation Error! Check console.")

        self.refresh_file_explorer_view() # Refresh explorer view to show newly created files

    def refresh_file_explorer_view(self, directory_to_list=None): # This method should exist from previous steps
        self.status_label.config(text="Status: Refreshing file explorer...")
        # Clear existing items from the tree
        for i in self.tree.get_children():
            self.tree.delete(i)
        
        current_path = directory_to_list if directory_to_list else self.base_display_path
        
        if not Path(current_path).is_dir():
            self.tree.insert("", "end", text=f"Directory not found: {current_path}", open=False)
            self.status_label.config(text=f"Status: Error - Directory not found: {current_path}")
            return

        result = list_directory_api(str(current_path))

        if result["success"]:
            # Display ".." (parent directory) if current_path is not the filesystem root
            current_resolved_path = Path(current_path).resolve()
            if current_resolved_path.parent != current_resolved_path: # Checks if it's not the root
                parent_path = current_resolved_path.parent
                self.tree.insert("", "end", text="..", open=False, 
                                 tags=("directory", "parent_dir"), 
                                 values=(str(parent_path),))

            for item in result["items"]:
                item_path = item["path"] 
                if item["type"] == "directory":
                    node = self.tree.insert("", "end", text=item["name"], open=False, 
                                            tags=("directory",), values=(item_path,))
                else: 
                    self.tree.insert("", "end", text=item["name"], open=False, 
                                     tags=("file",), values=(item_path,))
            self.status_label.config(text=f"Status: Explorer refreshed for {current_path}")
        else:
            self.tree.insert("", "end", text=f"Error: {result['error']}", open=False)
            self.status_label.config(text=f"Status: Error listing directory - {result['error']}")
        
        self.file_content_text.config(state=tk.NORMAL)
        self.file_content_text.delete(1.0, tk.END)
        self.file_content_text.config(state=tk.DISABLED)

    # Removed populate_treeview and insert_items as refresh_file_explorer_view replaces them.
    # Removed run method as master.mainloop() is called in __main__

if __name__ == '__main__':
    root = tk.Tk()
    root.geometry("900x600") # Set a larger default window size
    app = FileExplorerUI(root)
    # app.run() # master.mainloop() is called by Tkinter internally for the root window
    root.mainloop()
