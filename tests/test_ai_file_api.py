import unittest
import tempfile
import shutil
from pathlib import Path
import json

# Add project root to sys.path to allow importing modules
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.ai_file_api import (
    create_file_api,
    read_file_api,
    update_file_api,
    delete_file_api,
    create_directory_api,
    delete_directory_api,
    list_directory_api
)

class TestAiFileApi(unittest.TestCase):

    def setUp(self):
        # Create a new temporary directory for each test
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def test_create_file_api(self):
        file_path = self.test_dir / "test_file.txt"
        content = "Hello, world!"
        result = create_file_api(str(file_path), content)
        self.assertTrue(result["success"])
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), content)

        # Test creating a file in a non-existent subdirectory
        nested_file_path = self.test_dir / "subdir" / "nested_file.txt"
        nested_content = "Nested hello!"
        result_nested = create_file_api(str(nested_file_path), nested_content)
        self.assertTrue(result_nested["success"])
        self.assertTrue(nested_file_path.exists())
        self.assertEqual(nested_file_path.read_text(), nested_content)
        
        # It should overwrite if called again (as per current implementation which uses 'w')
        result_overwrite = create_file_api(str(file_path), "New content")
        self.assertTrue(result_overwrite["success"])
        self.assertEqual(file_path.read_text(), "New content")


    def test_read_file_api(self):
        file_path = self.test_dir / "read_test.txt"
        content = "Content to read."
        create_file_api(str(file_path), content)

        result = read_file_api(str(file_path))
        self.assertTrue(result["success"])
        self.assertEqual(result["content"], content)

        # Test reading non-existent file
        non_existent_path = self.test_dir / "non_existent.txt"
        result_non_existent = read_file_api(str(non_existent_path))
        self.assertFalse(result_non_existent["success"])
        self.assertIn("File not found", result_non_existent["error"])

    def test_update_file_api(self):
        file_path = self.test_dir / "update_test.txt"
        initial_content = "Initial content."
        create_file_api(str(file_path), initial_content)

        new_content = "Updated content."
        result = update_file_api(str(file_path), new_content)
        self.assertTrue(result["success"])
        self.assertEqual(file_path.read_text(), new_content)

        # Test updating non-existent file
        non_existent_path = self.test_dir / "non_existent_update.txt"
        result_non_existent = update_file_api(str(non_existent_path), "data")
        self.assertFalse(result_non_existent["success"])
        self.assertIn("File not found", result_non_existent["error"])

    def test_delete_file_api(self):
        file_path = self.test_dir / "delete_test.txt"
        create_file_api(str(file_path), "Content to delete.")
        self.assertTrue(file_path.exists())

        result = delete_file_api(str(file_path))
        self.assertTrue(result["success"])
        self.assertFalse(file_path.exists())

        # Test deleting non-existent file
        result_non_existent = delete_file_api(str(file_path)) # Already deleted
        self.assertFalse(result_non_existent["success"])
        self.assertIn("File not found", result_non_existent["error"])

    def test_create_directory_api(self):
        dir_path = self.test_dir / "new_dir"
        result = create_directory_api(str(dir_path))
        self.assertTrue(result["success"])
        self.assertTrue(dir_path.exists() and dir_path.is_dir())

        # Test creating an existing directory (should be success, idempotent)
        result_existing = create_directory_api(str(dir_path))
        self.assertTrue(result_existing["success"])
        
        # Test creating a directory where a file with the same name exists
        file_path_conflict = self.test_dir / "conflict_file_dir"
        create_file_api(str(file_path_conflict), "i am a file")
        result_conflict = create_directory_api(str(file_path_conflict))
        self.assertFalse(result_conflict["success"])
        self.assertIn("file with this name already exists", result_conflict["error"].lower())


    def test_delete_directory_api(self):
        # Test deleting an empty directory
        empty_dir_path = self.test_dir / "empty_dir"
        create_directory_api(str(empty_dir_path))
        self.assertTrue(empty_dir_path.exists())
        result_empty = delete_directory_api(str(empty_dir_path))
        self.assertTrue(result_empty["success"])
        self.assertFalse(empty_dir_path.exists())

        # Test deleting a non-empty directory
        non_empty_dir_path = self.test_dir / "non_empty_dir"
        create_directory_api(str(non_empty_dir_path))
        create_file_api(str(non_empty_dir_path / "some_file.txt"), "content")
        result_non_empty = delete_directory_api(str(non_empty_dir_path))
        self.assertFalse(result_non_empty["success"])
        self.assertIn("not empty", result_non_empty["error"])
        self.assertTrue(non_empty_dir_path.exists()) # Should still exist

        # Test deleting a non-existent directory
        non_existent_dir_path = self.test_dir / "ghost_dir"
        result_non_existent = delete_directory_api(str(non_existent_dir_path))
        self.assertFalse(result_non_existent["success"])
        self.assertIn("Directory not found", result_non_existent["error"])

    def test_list_directory_api(self):
        list_test_dir = self.test_dir / "list_test"
        create_directory_api(str(list_test_dir))

        # Create some items
        create_file_api(str(list_test_dir / "file1.txt"), "f1")
        create_file_api(str(list_test_dir / "file2.txt"), "f2")
        create_directory_api(str(list_test_dir / "subdir1"))

        result = list_directory_api(str(list_test_dir))
        self.assertTrue(result["success"])
        items = result["items"]
        self.assertEqual(len(items), 3)

        expected_items = {
            ("file1.txt", "file"),
            ("file2.txt", "file"),
            ("subdir1", "directory")
        }
        
        found_items = set()
        for item in items:
            self.assertIn("name", item)
            self.assertIn("type", item)
            self.assertIn("path", item)
            found_items.add((item["name"], item["type"]))
            # Check if path is correct
            self.assertEqual(Path(item["path"]), list_test_dir / item["name"])


        self.assertEqual(expected_items, found_items)

        # Test listing an empty directory
        empty_dir_for_list = self.test_dir / "empty_list_dir"
        create_directory_api(str(empty_dir_for_list))
        result_empty = list_directory_api(str(empty_dir_for_list))
        self.assertTrue(result_empty["success"])
        self.assertEqual(len(result_empty["items"]), 0)

        # Test listing a non-existent directory
        result_non_existent = list_directory_api(str(self.test_dir / "no_such_dir_for_list"))
        self.assertFalse(result_non_existent["success"])
        self.assertIn("not a directory or does not exist", result_non_existent["error"])
        
        # Test listing a file path
        file_path_for_list = self.test_dir / "a_file.txt"
        create_file_api(str(file_path_for_list), "content")
        result_file_list = list_directory_api(str(file_path_for_list))
        self.assertFalse(result_file_list["success"])
        self.assertIn("not a directory or does not exist", result_file_list["error"])


if __name__ == '__main__':
    unittest.main()
