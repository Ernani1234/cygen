import os
from pathlib import Path
import shutil

def create_file_api(file_path: str, content: str) -> dict:
    """Creates a new file with the given content."""
    try:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True) # Ensure parent directory exists
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "message": f"File '{file_path}' created successfully."}
    except Exception as e:
        return {"success": False, "error": f"Failed to create file '{file_path}': {e}"}

def read_file_api(file_path: str) -> dict:
    """Reads the content of the file."""
    try:
        p = Path(file_path)
        if not p.is_file():
            return {"success": False, "error": f"File not found: '{file_path}'"}
        content = p.read_text(encoding='utf-8')
        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": f"Failed to read file '{file_path}': {e}"}

def update_file_api(file_path: str, new_content: str) -> dict:
    """Updates the file with new content. Essentially overwrites it."""
    try:
        p = Path(file_path)
        if not p.is_file():
            return {"success": False, "error": f"File not found: '{file_path}'"}
        with open(p, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {"success": True, "message": f"File '{file_path}' updated successfully."}
    except Exception as e:
        return {"success": False, "error": f"Failed to update file '{file_path}': {e}"}

def delete_file_api(file_path: str) -> dict:
    """Deletes the file."""
    try:
        p = Path(file_path)
        if not p.is_file():
            return {"success": False, "error": f"File not found: '{file_path}'"}
        p.unlink()
        return {"success": True, "message": f"File '{file_path}' deleted successfully."}
    except Exception as e:
        return {"success": False, "error": f"Failed to delete file '{file_path}': {e}"}

def create_directory_api(dir_path: str) -> dict:
    """Creates a new directory."""
    try:
        p = Path(dir_path)
        p.mkdir(parents=True, exist_ok=True)
        # exist_ok=True means it won't raise an error if the directory already exists
        # however, if it exists but is a file, it will raise an error.
        if not p.is_dir(): # Double check it became a directory
             return {"success": False, "error": f"Path '{dir_path}' exists but is not a directory."}
        return {"success": True, "message": f"Directory '{dir_path}' created/ensured successfully."}
    except FileExistsError: # Specifically if the path exists and is a file
        return {"success": False, "error": f"Failed to create directory '{dir_path}': A file with this name already exists."}
    except Exception as e:
        return {"success": False, "error": f"Failed to create directory '{dir_path}': {e}"}

def delete_directory_api(dir_path: str) -> dict:
    """Deletes the directory. For safety, only deletes if empty."""
    try:
        p = Path(dir_path)
        if not p.exists():
            return {"success": False, "error": f"Directory not found: '{dir_path}'"}
        if not p.is_dir():
            return {"success": False, "error": f"Path is not a directory: '{dir_path}'"}
        
        # Check if directory is empty
        if any(p.iterdir()):
            # For a more destructive delete, one could use shutil.rmtree(p)
            # but the requirement was to be safe or handle non-empty.
            return {"success": False, "error": f"Directory '{dir_path}' is not empty. Please delete its contents first."}
        
        p.rmdir() # os.rmdir(p) also works
        return {"success": True, "message": f"Directory '{dir_path}' deleted successfully."}
    except Exception as e:
        # shutil.rmtree could be an alternative for non-empty deletion if desired later.
        return {"success": False, "error": f"Failed to delete directory '{dir_path}': {e}"}

if __name__ == '__main__':
    # Basic tests for the API functions
    test_dir = Path("_test_ai_api_dir")
    if test_dir.exists():
        shutil.rmtree(test_dir) # Clean up from previous runs
    test_dir.mkdir()

    print("Testing AI File API...")

    # Create directory
    print("\nCreate directory:")
    res_create_dir = create_directory_api(str(test_dir / "new_folder"))
    print(res_create_dir)
    res_create_dir_exists = create_directory_api(str(test_dir / "new_folder")) # Try again
    print(res_create_dir_exists)


    # Create file
    print("\nCreate file:")
    file1_path = str(test_dir / "new_folder" / "test_file1.txt")
    res_create = create_file_api(file1_path, "Hello from AI API!")
    print(res_create)
    
    # Create file in non-existent nested folder
    file_nested_path = str(test_dir / "level1" / "level2" / "nested.txt")
    res_create_nested = create_file_api(file_nested_path, "Nested hello!")
    print(res_create_nested)


    # Read file
    print("\nRead file:")
    res_read = read_file_api(file1_path)
    print(res_read)
    res_read_nonexistent = read_file_api(str(test_dir / "nonexistent.txt"))
    print(res_read_nonexistent)

    # Update file
    print("\nUpdate file:")
    res_update = update_file_api(file1_path, "Updated content.")
    print(res_update)
    print(read_file_api(file1_path)) # Verify update

    # Delete file
    print("\nDelete file:")
    res_delete = delete_file_api(file1_path)
    print(res_delete)
    print(read_file_api(file1_path)) # Verify delete

    # Delete directory
    print("\nDelete directory:")
    # Try deleting non-empty directory
    res_delete_dir_nonempty = delete_directory_api(str(test_dir / "new_folder")) # Contains nested.txt if previous test ran fully
    # Let's ensure it's non-empty for this test
    create_file_api(str(test_dir / "new_folder" / "another.txt"), "content")
    res_delete_dir_nonempty_after_add = delete_directory_api(str(test_dir / "new_folder"))
    print(f"Attempt to delete non-empty '{test_dir / 'new_folder'}': {res_delete_dir_nonempty_after_add}")


    # Delete empty directory
    empty_dir_path = test_dir / "empty_subdir"
    create_directory_api(str(empty_dir_path))
    res_delete_dir_empty = delete_directory_api(str(empty_dir_path))
    print(f"Attempt to delete empty '{empty_dir_path}': {res_delete_dir_empty}")
    
    # Delete non-existent directory
    res_delete_dir_nonexistent = delete_directory_api(str(test_dir / "ghost_folder"))
    print(f"Attempt to delete non-existent dir: {res_delete_dir_nonexistent}")

    # Clean up
    # print("\nCleaning up test directory...")
    # shutil.rmtree(test_dir)
    print(f"\nTest files and directories are in '{test_dir.resolve()}'. Manual cleanup might be needed.")


def list_directory_api(dir_path: str) -> dict:
    """Lists all files and subdirectories directly within dir_path."""
    try:
        p = Path(dir_path)
        if not p.is_dir():
            return {"success": False, "error": f"Path is not a directory or does not exist: '{dir_path}'"}

        items = []
        for item in p.iterdir():
            item_type = "directory" if item.is_dir() else "file"
            items.append({"name": item.name, "type": item_type, "path": str(item)})
        
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": f"Failed to list directory '{dir_path}': {e}"}

if __name__ == '__main__':
    # Basic tests for the API functions
    test_dir = Path("_test_ai_api_dir")
    if test_dir.exists():
        shutil.rmtree(test_dir) # Clean up from previous runs
    test_dir.mkdir()

    print("Testing AI File API...")

    # Create directory
    print("\nCreate directory:")
    new_folder_path = test_dir / "new_folder"
    res_create_dir = create_directory_api(str(new_folder_path))
    print(res_create_dir)
    res_create_dir_exists = create_directory_api(str(new_folder_path)) # Try again
    print(res_create_dir_exists)


    # Create file
    print("\nCreate file:")
    file1_path = str(new_folder_path / "test_file1.txt")
    res_create = create_file_api(file1_path, "Hello from AI API!")
    print(res_create)
    
    # Create file in non-existent nested folder
    file_nested_path = str(test_dir / "level1" / "level2" / "nested.txt")
    res_create_nested = create_file_api(file_nested_path, "Nested hello!")
    print(res_create_nested)


    # Read file
    print("\nRead file:")
    res_read = read_file_api(file1_path)
    print(res_read)
    res_read_nonexistent = read_file_api(str(test_dir / "nonexistent.txt"))
    print(res_read_nonexistent)

    # Update file
    print("\nUpdate file:")
    res_update = update_file_api(file1_path, "Updated content.")
    print(res_update)
    print(read_file_api(file1_path)) # Verify update

    # List directory
    print("\nList directory:")
    print(f"Listing {new_folder_path}:")
    print(list_directory_api(str(new_folder_path)))
    print(f"Listing {test_dir}:")
    print(list_directory_api(str(test_dir)))
    print(f"Listing non-existent dir:")
    print(list_directory_api(str(test_dir / "non_existent_folder")))


    # Delete file
    print("\nDelete file:")
    res_delete = delete_file_api(file1_path)
    print(res_delete)
    print(read_file_api(file1_path)) # Verify delete

    # Delete directory
    print("\nDelete directory:")
    # Try deleting non-empty directory
    # Ensure new_folder_path is non-empty for this test
    create_file_api(str(new_folder_path / "another.txt"), "content")
    res_delete_dir_nonempty_after_add = delete_directory_api(str(new_folder_path))
    print(f"Attempt to delete non-empty '{new_folder_path}': {res_delete_dir_nonempty_after_add}")


    # Delete empty directory
    empty_dir_path = test_dir / "empty_subdir"
    create_directory_api(str(empty_dir_path))
    res_delete_dir_empty = delete_directory_api(str(empty_dir_path))
    print(f"Attempt to delete empty '{empty_dir_path}': {res_delete_dir_empty}")
    
    # Delete non-existent directory
    res_delete_dir_nonexistent = delete_directory_api(str(test_dir / "ghost_folder"))
    print(f"Attempt to delete non-existent dir: {res_delete_dir_nonexistent}")
    
    # List again to see changes
    print(f"\nListing {test_dir} after deletions:")
    print(list_directory_api(str(test_dir)))

    # Clean up
    # print("\nCleaning up test directory...")
    # shutil.rmtree(test_dir)
    print(f"\nTest files and directories are in '{test_dir.resolve()}'. Manual cleanup might be needed.")
