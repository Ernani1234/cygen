import unittest
import tempfile
import shutil
from pathlib import Path
import json

# Add project root to sys.path to allow importing modules
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.structure_generator import StructureGenerator

class TestStructureGenerator(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.base_path = str(self.test_dir)
        self.generator = StructureGenerator()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_generate_cypress_structure(self):
        success, created_paths, errors = self.generator.generate_cypress_structure(self.base_path)
        self.assertTrue(success)
        self.assertEqual(len(errors), 0)

        expected_dirs = [
            Path(self.base_path) / "cypress" / "config",
            Path(self.base_path) / "cypress" / "e2e" / "exemplos",
            Path(self.base_path) / "cypress" / "fixtures",
            Path(self.base_path) / "cypress" / "support",
            Path(self.base_path) / "helpers"
        ]
        for dir_path in expected_dirs:
            self.assertTrue(dir_path.exists(), f"{dir_path} was not created.")
            self.assertTrue(dir_path.is_dir(), f"{dir_path} is not a directory.")
        
        # Check if all created_paths are indeed created
        for p_str in created_paths:
            self.assertTrue(Path(p_str).exists())

        # Test idempotency: running again should not fail
        success_again, _, errors_again = self.generator.generate_cypress_structure(self.base_path)
        self.assertTrue(success_again)
        self.assertEqual(len(errors_again), 0)


    def test_create_fixture_file(self):
        # First, ensure the base structure (especially cypress/fixtures) exists
        self.generator.generate_cypress_structure(self.base_path)
        
        fixture_name = "my_fixture"
        content_dict = {"key": "value", "number": 123}
        
        success, file_path_str, error = self.generator.create_fixture_file(self.base_path, fixture_name, content_dict)
        self.assertTrue(success)
        self.assertIsNone(error)
        
        expected_file_path = Path(self.base_path) / "cypress" / "fixtures" / (fixture_name + ".json")
        self.assertEqual(Path(file_path_str), expected_file_path)
        self.assertTrue(expected_file_path.exists())
        
        with open(expected_file_path, 'r') as f:
            loaded_content = json.load(f)
        self.assertEqual(loaded_content, content_dict)

        # Test with name already having .json
        fixture_name_with_ext = "another.json"
        content_string = "just a string" # Test with string content too
        success, file_path_str_ext, error = self.generator.create_fixture_file(self.base_path, fixture_name_with_ext, content_string)
        self.assertTrue(success)
        expected_file_path_ext = Path(self.base_path) / "cypress" / "fixtures" / fixture_name_with_ext
        self.assertEqual(Path(file_path_str_ext), expected_file_path_ext)
        self.assertTrue(expected_file_path_ext.exists())
        with open(expected_file_path_ext, 'r') as f:
            # For string content, it's not dumped as JSON, but written directly
            self.assertEqual(f.read(), content_string)


    def test_create_support_command(self):
        self.generator.generate_cypress_structure(self.base_path)
        
        command_name = "customLogin"
        command_js_content = "Cypress.Commands.add('customLogin', () => { cy.log('Logged in'); });"
        
        success, file_path_str, error = self.generator.create_support_command(self.base_path, command_name, command_js_content)
        self.assertTrue(success)
        self.assertIsNone(error)
        
        expected_file_path = Path(self.base_path) / "cypress" / "support" / "commands.js"
        self.assertEqual(Path(file_path_str), expected_file_path)
        self.assertTrue(expected_file_path.exists())
        
        content = expected_file_path.read_text()
        self.assertIn(f"// Command: {command_name}", content)
        self.assertIn(command_js_content, content)

        # Test appending another command
        command_name_2 = "anotherCmd"
        command_js_content_2 = "Cypress.Commands.add('anotherCmd', () => { cy.log('Another'); });"
        success, _, _ = self.generator.create_support_command(self.base_path, command_name_2, command_js_content_2)
        self.assertTrue(success)
        
        content_after_append = expected_file_path.read_text()
        self.assertIn(command_js_content, content_after_append) # Original should still be there
        self.assertIn(command_js_content_2, content_after_append)


    def test_create_helper_file(self):
        self.generator.generate_cypress_structure(self.base_path)
        
        helper_name = "mathUtils"
        helper_js_content = "export const add = (a, b) => a + b;"
        
        success, file_path_str, error = self.generator.create_helper_file(self.base_path, helper_name, helper_js_content)
        self.assertTrue(success)
        self.assertIsNone(error)
        
        expected_file_path = Path(self.base_path) / "helpers" / (helper_name + ".js")
        self.assertEqual(Path(file_path_str), expected_file_path)
        self.assertTrue(expected_file_path.exists())
        self.assertEqual(expected_file_path.read_text(), helper_js_content)

        # Test with .js in name
        helper_name_with_ext = "stringUtils.js"
        helper_js_content_2 = "export const upper = (s) => s.toUpperCase();"
        success, file_path_str_ext, _ = self.generator.create_helper_file(self.base_path, helper_name_with_ext, helper_js_content_2)
        self.assertTrue(success)
        expected_file_path_ext = Path(self.base_path) / "helpers" / helper_name_with_ext
        self.assertEqual(Path(file_path_str_ext), expected_file_path_ext)
        self.assertEqual(expected_file_path_ext.read_text(), helper_js_content_2)


    def test_create_e2e_spec_file(self):
        self.generator.generate_cypress_structure(self.base_path)
        
        spec_name = "myFirstTest"
        describe_block_name = "My Test Suite"
        test_content_placeholder = "This is a placeholder for test steps."
        
        success, file_path_str, error = self.generator.create_e2e_spec_file(
            self.base_path, spec_name, describe_block_name, test_content_placeholder
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        
        expected_file_path = Path(self.base_path) / "cypress" / "e2e" / "exemplos" / (spec_name + ".cy.js")
        self.assertEqual(Path(file_path_str), expected_file_path)
        self.assertTrue(expected_file_path.exists())
        
        file_content = expected_file_path.read_text()
        self.assertIn(f"describe('{describe_block_name}', () => {{", file_content)
        self.assertIn(f"// {test_content_placeholder}", file_content)
        self.assertIn("it('should do something (placeholder test)', () => {", file_content)
        self.assertIn("expect(true).to.equal(true);", file_content)

        # Test with .cy.js in name
        spec_name_with_ext = "anotherTest.cy.js"
        success, file_path_str_ext, _ = self.generator.create_e2e_spec_file(
            self.base_path, spec_name_with_ext, "Another Suite", "More tests"
        )
        self.assertTrue(success)
        expected_file_path_ext = Path(self.base_path) / "cypress" / "e2e" / "exemplos" / spec_name_with_ext
        self.assertEqual(Path(file_path_str_ext), expected_file_path_ext)


if __name__ == '__main__':
    unittest.main()
