import pytest

from devsecops_agent.tools import ToolError


def test_read_file(workspace):
    assert workspace.read_file("src/app.py") == "print('hello')\n"


def test_read_missing_file(workspace):
    with pytest.raises(ToolError, match="File not found"):
        workspace.read_file("nope.py")


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "src/../../x"])
def test_paths_outside_workspace_are_rejected(workspace, path):
    with pytest.raises(ToolError, match="outside the workspace"):
        workspace.read_file(path)


def test_symlink_escape_is_rejected(workspace, tmp_path_factory):
    secret = tmp_path_factory.mktemp("elsewhere") / "secret.txt"
    secret.write_text("top secret")
    (workspace.root / "link.txt").symlink_to(secret)
    with pytest.raises(ToolError, match="outside the workspace"):
        workspace.read_file("link.txt")


def test_list_files_defaults_to_root_and_puts_dirs_first(workspace):
    out = workspace.list_files()
    lines = out.splitlines()[1:]
    assert lines == ["[dir]  src/", "[file] README.md"]


def test_list_missing_dir(workspace):
    with pytest.raises(ToolError, match="Directory not found"):
        workspace.list_files("missing")


def test_create_file_including_parent_dirs(workspace):
    assert workspace.edit_file("new/dir/file.txt", new_text="hi") == "Created new/dir/file.txt"
    assert (workspace.root / "new/dir/file.txt").read_text() == "hi"


def test_edit_replaces_unique_match(workspace):
    workspace.edit_file("src/app.py", old_text="hello", new_text="world")
    assert workspace.read_file("src/app.py") == "print('world')\n"


def test_edit_refuses_ambiguous_match(workspace):
    workspace.edit_file("dup.txt", new_text="a a")
    with pytest.raises(ToolError, match="matches 2 places"):
        workspace.edit_file("dup.txt", old_text="a", new_text="b")


def test_edit_refuses_to_overwrite_existing_file_without_old_text(workspace):
    with pytest.raises(ToolError, match="already exists"):
        workspace.edit_file("src/app.py", new_text="overwritten")


def test_edit_missing_text(workspace):
    with pytest.raises(ToolError, match="not found"):
        workspace.edit_file("src/app.py", old_text="absent", new_text="x")
