import os
from pathlib import Path
import json

class StructureGenerator:
    def __init__(self):
        pass

    def _ensure_dir_exists(self, dir_path: Path):
        """Helper method to ensure a directory exists."""
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"Created directory: {dir_path}")
        return dir_path

    def generate_cypress_structure(self, base_path: str):
        """
        Generates the Cypress directory structure under the given base_path.
        Creates directories only if they are missing.
        """
        base = Path(base_path)
        directories_to_create = [
            base / "cypress" / "config",
            base / "cypress" / "e2e" / "exemplos",
            base / "cypress" / "fixtures",
            base / "cypress" / "support",
            base / "helpers"
        ]

        created_paths = []
        errors = []

        for dir_path in directories_to_create:
            try:
                self._ensure_dir_exists(dir_path)
                created_paths.append(str(dir_path))
            except OSError as e:
                error_msg = f"Error creating directory {dir_path}: {e}"
                print(error_msg)
                errors.append(error_msg)
        
        if errors:
            return False, created_paths, errors
        
        return True, created_paths, []

    def create_fixture_file(self, base_path: str, fixture_name: str, content):
        """
        Creates a JSON file in base_path/cypress/fixtures/.
        Writes the given content (string or dictionary) to this file.
        Appends .json to fixture_name if not present.
        """
        base = Path(base_path)
        fixtures_dir = self._ensure_dir_exists(base / "cypress" / "fixtures")

        if not fixture_name.endswith(".json"):
            fixture_name += ".json"
        
        file_path = fixtures_dir / fixture_name
        try:
            with open(file_path, 'w') as f:
                if isinstance(content, (dict, list)):
                    json.dump(content, f, indent=2)
                else:
                    f.write(str(content))
            print(f"Successfully created fixture: {file_path}")
            return True, str(file_path), None
        except IOError as e:
            error_msg = f"Error writing fixture file {file_path}: {e}"
            print(error_msg)
            return False, str(file_path), error_msg

    def create_support_command(self, base_path: str, command_name: str, command_js_content: str):
        """
        Creates or appends to commands.js in base_path/cypress/support/.
        Adds the provided JavaScript code.
        """
        base = Path(base_path)
        support_dir = self._ensure_dir_exists(base / "cypress" / "support")
        commands_file = support_dir / "commands.js" # Defaulting to commands.js

        try:
            # For simplicity, we always append. A more robust solution might check if the command exists.
            with open(commands_file, 'a') as f:
                f.write(f"\n// Command: {command_name}\n")
                f.write(command_js_content)
                f.write("\n")
            print(f"Successfully added/appended command '{command_name}' to: {commands_file}")
            return True, str(commands_file), None
        except IOError as e:
            error_msg = f"Error writing support command to {commands_file}: {e}"
            print(error_msg)
            return False, str(commands_file), error_msg

    def create_helper_file(self, base_path: str, helper_name: str, helper_js_content: str):
        """
        Creates a JavaScript file in base_path/helpers/.
        Writes the helper_js_content to this file.
        Appends .js to helper_name if not present.
        """
        base = Path(base_path)
        helpers_dir = self._ensure_dir_exists(base / "helpers")

        if not helper_name.endswith(".js"):
            helper_name += ".js"
            
        file_path = helpers_dir / helper_name
        try:
            with open(file_path, 'w') as f:
                f.write(helper_js_content)
            print(f"Successfully created helper file: {file_path}")
            return True, str(file_path), None
        except IOError as e:
            error_msg = f"Error writing helper file {file_path}: {e}"
            print(error_msg)
            return False, str(file_path), error_msg

    def create_e2e_spec_file(self, base_path: str, spec_name: str, describe_block_name: str, test_content: str):
        """
        Creates a Cypress spec file in base_path/cypress/e2e/exemplos/.
        Writes a basic spec structure with describe_block_name and test_content.
        Appends .cy.js to spec_name if not present.
        """
        base = Path(base_path)
        e2e_exemplos_dir = self._ensure_dir_exists(base / "cypress" / "e2e" / "exemplos")

        if not spec_name.endswith(".cy.js"):
            if spec_name.endswith(".js"):
                spec_name = spec_name[:-3] + ".cy.js"
            else:
                spec_name += ".cy.js"

        file_path = e2e_exemplos_dir / spec_name
        
        # Basic Cypress spec structure
        spec_content = f"""\
describe('{describe_block_name}', () => {{
  // {test_content}
  it('should do something (placeholder test)', () => {{
    // Placeholder test
    expect(true).to.equal(true);
  }});
}});
"""
        try:
            with open(file_path, 'w') as f:
                f.write(spec_content)
            print(f"Successfully created E2E spec file: {file_path}")
            return True, str(file_path), None
        except IOError as e:
            error_msg = f"Error writing E2E spec file {file_path}: {e}"
            print(error_msg)
            return False, str(file_path), error_msg

if __name__ == '__main__':
    generator = StructureGenerator()
    test_base_path_str = "test_project_root_populated"
    test_base_path = Path(test_base_path_str)

    # 1. Generate base structure
    print(f"Generating Cypress structure in: {test_base_path.resolve()}")
    success, _, _ = generator.generate_cypress_structure(test_base_path_str)
    if not success:
        print("Failed to create base structure. Aborting further tests.")
    else:
        print("\nBase structure generated.")

        # 2. Create a fixture file
        print("\nTesting fixture creation...")
        fixture_data = {"name": "John Doe", "email": "john.doe@example.com"}
        generator.create_fixture_file(test_base_path_str, "exampleUser", fixture_data)
        generator.create_fixture_file(test_base_path_str, "anotherFixture.json", "Just a string content")

        # 3. Create a support command
        print("\nTesting support command creation...")
        custom_command_js = """
Cypress.Commands.add('customLogin', (username, password) => {
  cy.log(`Logging in as ${username}`);
  // Actual login commands would go here
});
"""
        generator.create_support_command(test_base_path_str, "customLogin", custom_command_js)
        generator.create_support_command(test_base_path_str, "anotherCommand", "cy.log('Another command');")


        # 4. Create a helper file
        print("\nTesting helper file creation...")
        helper_content_js = """
export const add = (a, b) => a + b;

export const subtract = (a, b) => a - b;
"""
        generator.create_helper_file(test_base_path_str, "mathUtils", helper_content_js)
        generator.create_helper_file(test_base_path_str, "stringUtils.js", "export const greet = (name) => `Hello, ${name}!`;")

        # 5. Create an E2E spec file
        print("\nTesting E2E spec file creation...")
        generator.create_e2e_spec_file(test_base_path_str, 
                                        "sampleTest", 
                                        "Sample Test Suite", 
                                        "This is a test for basic functionality.")
        generator.create_e2e_spec_file(test_base_path_str, 
                                        "anotherExample.cy.js", 
                                        "Another Example Suite", 
                                        "Test for another feature.")

        print(f"\nCheck the directory '{test_base_path.resolve()}' to see the populated structure.")
        print("Remember to manually clean it up if needed (e.g., by deleting the 'test_project_root_populated' directory).")
