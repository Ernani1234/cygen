# File Explorer and AI-Assisted System Documentation

## 1. Overview

This document describes the features of the integrated File Explorer, Automated Cypress Test Structure Generation, and the AI-Assisted Editing system. These tools are designed to streamline the process of setting up and managing Cypress test projects.

The primary Python modules involved are:
*   `modules/file_explorer_ui.py`: Provides the graphical user interface.
*   `modules/structure_generator.py`: Handles the creation of a standard Cypress project directory structure and sample files.
*   `modules/ai_file_api.py`: Offers a set of functions for file and directory manipulation, intended to be used by an AI system (currently simulated).

## 2. File Explorer UI (`modules/file_explorer_ui.py`)

The File Explorer UI provides a visual way to interact with a generated Cypress test structure and to trigger various generation and editing commands.

**Running the UI:**
To run the application, execute the following command from the root of the repository:
```bash
python -m modules.file_explorer_ui
```
*Note: Ensure your Python environment has Tkinter available, which is usually part of the standard library.*

**Main UI Components:**

*   **File Tree View:**
    *   Located on the left side of the application.
    *   Displays the directory structure of a predefined base directory. Currently, this is fixed to `./generated_test_structure/` relative to where the application is run.
    *   You can click on directories to (eventually, with further development) expand/collapse them and on files to view their content.
*   **File Content Display Area:**
    *   Located on the right side, this area shows the content of the file selected in the File Tree View.
    *   It's a read-only text area.
*   **"Generate Cypress Structure" Button:**
    *   Located in the top-right control area.
    *   Triggers the automated generation of a standard Cypress project structure and sample files into the `./generated_test_structure/` directory.
*   **"Refresh Explorer" Button:**
    *   Located next to the "Generate" button.
    *   Reloads the File Tree View to reflect any changes made to the `./generated_test_structure/` directory.
*   **AI Command Input Field:**
    *   Located at the bottom-right of the UI.
    *   A text field where users can type commands intended for the AI system.
*   **"Execute AI Command" Button:**
    *   Located next to the AI command input field.
    *   Submits the command from the input field to the (currently simulated) AI processing logic.

**Interacting with the UI:**
*   **Selecting Files/Directories:** Click on an item in the File Tree View. If it's a file, its content will appear in the File Content Display Area. If it's a directory, a message indicating it's a directory will be shown.
*   **Viewing Content:** Select a file in the tree to see its contents.
*   **Generating Structure:** Click the "Generate Cypress Structure" button. The UI will update the File Tree View automatically after generation.
*   **Refreshing View:** Click "Refresh Explorer" to manually update the File Tree View if external changes were made.

## 3. Automated Structure Generation

This feature automates the creation of a foundational Cypress test project.

**Triggering Generation:**
*   Click the "Generate Cypress Structure" button in the UI.

**Target Directory:**
*   The directory structure and files are generated within `./generated_test_structure/` (relative to the application's running location).

**Generated Directory Structure (`modules/structure_generator.py`):**
The following standard Cypress and helper directory structure is created:
```
./generated_test_structure/
├── cypress/
│   ├── config/
│   ├── e2e/
│   │   └── exemplos/
│   ├── fixtures/
│   └── support/
└── helpers/
```

**Generated Sample Files:**
*   **Fixture File:**
    *   Path: `cypress/fixtures/example_fixture.json`
    *   Content: A sample JSON object (e.g., `{"user": "test_user", "password": "password123"}`).
*   **E2E Spec File:**
    *   Path: `cypress/e2e/exemplos/example_spec.cy.js`
    *   Content: A basic Cypress spec structure with a `describe` block and a placeholder `it` test.
*   **Support Command File:**
    *   Path: `cypress/support/commands.js` (appended to or created)
    *   Content: An example custom Cypress command (e.g., `Cypress.Commands.add('login', (username, password) => { /* ... */ });`).
*   **Helper File:**
    *   Path: `helpers/example_helper.js`
    *   Content: An example JavaScript helper function (e.g., `export function greet(name) { return \`Hello, \${name}\`;} `).

## 4. AI-Assisted Editing Features

The UI includes components for interacting with an AI system for file editing, though the actual AI processing is currently a placeholder.

**Using the AI Command Interface:**
1.  Type your desired command into the "AI Command input" field (e.g., "create directory new_folder").
2.  Click the "Execute AI Command" button.
3.  The UI's status bar will show feedback based on the (simulated) command processing.

**Current AI Simulation:**
The system does not connect to a real AI. Instead, it performs very simple keyword matching on the input command to simulate what an AI might do. For example:
*   If the command is `create directory my_new_dir`, it will attempt to use the `create_directory_api` to create `my_new_dir` within the `./generated_test_structure/` folder and then refresh the explorer.
*   Other commands like "create file", "read file", "update file", "delete file", "delete directory" will print a simulation message indicating which API function would theoretically be called.

**AI File API (`modules/ai_file_api.py`):**
This module provides the underlying functions that an AI would use to interact with the file system. These functions are fully implemented and unit-tested:
*   `create_file_api(file_path: str, content: str)`: Creates a new file.
*   `read_file_api(file_path: str)`: Reads file content.
*   `update_file_api(file_path: str, new_content: str)`: Updates (overwrites) a file.
*   `delete_file_api(file_path: str)`: Deletes a file.
*   `create_directory_api(dir_path: str)`: Creates a directory.
*   `delete_directory_api(dir_path: str)`: Deletes an empty directory.
*   `list_directory_api(dir_path: str)`: Lists contents of a directory.

Each API function returns a dictionary indicating success or failure, along with data or an error message.

## 5. Integrating with Gerador de Testes

To directly incorporate the "Criar Estrutura Cypress" (Create Cypress Structure) functionality into the main "Gerador de Testes" application, particularly after its "Finalizar" (Finish) step, manual modifications to the "Gerador de Testes" source code will be necessary. These changes would likely occur in modules responsible for the UI and workflow management, such as `modules/test_generator.py`, `modules/settings_ui.py`, or similar.

The goal is to trigger the Cypress structure generation based on the test that was just configured and finalized in the "Gerador de Testes".

### Step 1: Import the Core Generation Function

The primary logic for generating the Cypress directory structure and sample files is encapsulated in the `initiate_cypress_structure_generation` function. Import this function into the relevant Python file within the "Gerador de Testes" codebase:

```python
from modules.structure_generator import initiate_cypress_structure_generation
```

### Step 2: Add a UI Element (Button)

A new UI element, typically a button, should be added to the "Gerador de Testes" interface. Consider the following:
*   **Label:** "Criar Estrutura Cypress", "Generate Cypress Files", or similar.
*   **Placement:** This button should ideally become active or visible after the "Gerador de Testes" has completed its "Finalizar" step (Step 5), meaning a test configuration is ready.
*   **Implementation:** The method for adding a button depends on the UI framework used by "Gerador de Testes" (e.g., Tkinter, PyQt, CustomTkinter). You'll need to add the button and link it to an action/command.

### Step 3: Define the Button's Action

The action associated with the new button will be to call the imported `initiate_cypress_structure_generation` function.

**Parameters for the function call:**

*   `base_output_path (str)`: This is the directory where the Cypress structure will be created.
    *   It can be a fixed path (e.g., `"./cypress_generated_tests/cypress_for_my_test"`).
    *   It could be dynamically derived, perhaps using a project name or the name of the test just generated by "Gerador de Testes" to create a unique subdirectory.
*   `test_name (str, optional)`: This name is used to customize the generated sample files (fixture, spec, command, helper).
    *   Ideally, this should be the name or a unique identifier of the test that was just finalized by the "Gerador de Testes". This provides context to the sample files.
    *   If a specific test name isn't readily available, a default like `"generated_test"` or the project name can be used.

**Example function call within the button's command/callback:**

```python
# Assume 'name_of_finalized_test' holds the name/ID from Gerador de Testes.
# Assume 'output_directory_for_cypress' is the chosen path for this structure.

# Example:
# name_of_finalized_test = "Login_Feature_Test" 
# output_directory_for_cypress = f"./generated_cypress_projects/{name_of_finalized_test}_cypress"

try:
    # Ensure the 'output_directory_for_cypress' exists or is created by the function
    # The initiate_cypress_structure_generation function handles creation of base_output_path
    
    output_location = initiate_cypress_structure_generation(
        base_output_path=output_directory_for_cypress,
        test_name=name_of_finalized_test 
    )
    
    # Provide feedback to the user within the "Gerador de Testes" UI
    print(f"Cypress structure for '{name_of_finalized_test}' successfully generated at: {output_location}")
    # e.g., update a status bar, show a success message dialog
    
except Exception as e:
    # Handle potential errors from the generation process
    print(f"Error generating Cypress structure for '{name_of_finalized_test}': {e}")
    # e.g., show an error message dialog to the user
```

### Important Considerations:

*   **User Feedback:** Ensure the "Gerador de Testes" UI provides feedback to the user during and after the Cypress structure generation (e.g., disabling the button during processing, showing success or error messages, indicating the output path).
*   **Error Handling:** Robustly handle potential exceptions during the generation process, as shown in the example.
*   **Path Management:** Decide on a clear strategy for the `base_output_path`. Will it be configurable by the user? Will it be relative to the current project of "Gerador de Testes"?
*   **State Management:** Manage the state of the "Criar Estrutura Cypress" button (e.g., enable it only when a test has been finalized).

By following these steps, the powerful Cypress structure generation can be seamlessly integrated into the "Gerador de Testes" workflow.

## 6. Developer Information

**Source Code:**
*   The main logic for these features is located in the `modules/` directory:
    *   `modules/file_explorer_ui.py`
    *   `modules/structure_generator.py`
    *   `modules/ai_file_api.py`

**Unit Tests:**
*   Unit tests are located in the `tests/` directory:
    *   `tests/test_ai_file_api.py`
    *   `tests/test_structure_generator.py`

**Running Unit Tests:**
To run all unit tests, execute the following command from the root of the repository:
```bash
python -m unittest discover tests -v
```

This command will discover and run all test cases in the `tests` directory and provide verbose output.
---
